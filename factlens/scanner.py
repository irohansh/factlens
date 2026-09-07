"""
Malware scanning service for FactLens.
Supports ClamAV clamd daemon (via TCP or Unix socket) and a transparent development mock mode (dev_mock).
Fail-closed behavior is enforced when ClamAV is configured but unavailable.
"""

import socket
import struct
import logging
from pathlib import Path
from typing import Tuple, Optional

from factlens.config import settings
from factlens.schemas import ScanStatus

logger = logging.getLogger("factlens.scanner")

# Standard EICAR antivirus test signature
EICAR_SIGNATURE = b"X5O!P%@AP[4\\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*"


class ScannerError(Exception):
    """Base exception for scanner issues."""
    pass


class ScannerUnavailableError(ScannerError):
    """Raised when the configured malware scanner is unavailable (fail-closed)."""
    pass


class MalwareDetectedError(ScannerError):
    """Raised when malware is detected in scanned content."""
    def __init__(self, filename: str, virus_name: str):
        super().__init__(f"Malware '{virus_name}' detected in file: {filename}")
        self.filename = filename
        self.virus_name = virus_name


class MalwareScanner:
    """
    Malware scanner supporting ClamAV clamd protocol and dev_mock mode.
    """

    def __init__(
        self,
        mode: Optional[str] = None,
        host: Optional[str] = None,
        port: Optional[int] = None,
        socket_path: Optional[str] = None,
        timeout: Optional[int] = None,
    ):
        self.mode = (mode or settings.MALWARE_SCAN_MODE).lower()
        self.host = host or settings.CLAMAV_HOST
        self.port = port or settings.CLAMAV_PORT
        self.socket_path = socket_path or settings.CLAMAV_SOCKET
        self.timeout = timeout or settings.CLAMAV_TIMEOUT_SECONDS

    def scan_bytes(self, content: bytes, filename: str = "unknown") -> Tuple[ScanStatus, str]:
        """
        Scan in-memory file bytes for malware.
        Returns (ScanStatus, details_string).
        Raises ScannerUnavailableError when ClamAV/fail_closed fails.
        """
        if self.mode == "dev_mock":
            return self._scan_mock(content, filename)
        elif self.mode == "clamav":
            return self._scan_clamav(content, filename)
        elif self.mode == "fail_closed":
            logger.error("Malware scan mode is set to 'fail_closed'. Rejecting upload for safety: %s", filename)
            raise ScannerUnavailableError("Malware scanner is configured in fail-closed mode; upload rejected.")
        else:
            logger.warning("Unknown MALWARE_SCAN_MODE '%s', enforcing fail-closed.", self.mode)
            raise ScannerUnavailableError(f"Unknown malware scanner mode: {self.mode}")

    def scan_file(self, file_path: Path) -> Tuple[ScanStatus, str]:
        """Read file from disk and scan its contents."""
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"File not found for scanning: {file_path}")
        content = path.read_bytes()
        return self.scan_bytes(content, filename=path.name)

    def _scan_mock(self, content: bytes, filename: str) -> Tuple[ScanStatus, str]:
        """
        Development mock scan.
        Explicitly warns that real AV was not used.
        Rejects EICAR signature for testing.
        """
        if EICAR_SIGNATURE in content:
            virus_name = "EICAR-Test-Signature"
            logger.warning("[DEV_MOCK] Virus signature matched in %s: %s", filename, virus_name)
            return ScanStatus.INFECTED, f"Infected: {virus_name} detected"

        # Explicit warning in logs that real AV was bypassed
        logger.warning(
            "MALWARE SCANNING IS IN DEV_MOCK MODE. File '%s' was NOT scanned by a real antivirus engine.",
            filename,
        )
        return ScanStatus.MOCK_SCANNED, "Clean (Dev mock scan - no real AV engine)"

    def _connect_clamd(self) -> socket.socket:
        """Establish a TCP or Unix socket connection to clamd."""
        # Try Unix socket first if path exists
        if self.socket_path and Path(self.socket_path).exists():
            try:
                s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                s.settimeout(self.timeout)
                s.connect(self.socket_path)
                return s
            except Exception as e:
                logger.debug("ClamAV Unix socket failed (%s), trying TCP fallback: %s", self.socket_path, e)

        # Connect via TCP
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(self.timeout)
            s.connect((self.host, self.port))
            return s
        except Exception as e:
            raise ScannerUnavailableError(
                f"Cannot connect to ClamAV daemon at {self.host}:{self.port} (or socket {self.socket_path}): {e}"
            ) from e

    def _scan_clamav(self, content: bytes, filename: str) -> Tuple[ScanStatus, str]:
        """
        Stream bytes to clamd using the zINSTREAM protocol.
        Format:
          Command: zINSTREAM\0
          Chunks: <length: 4 bytes big endian><data>
          Terminator: <0: 4 bytes big endian>
        Response:
          stream: OK\0 OR stream: <virusname> FOUND\0
        """
        sock = None
        try:
            sock = self._connect_clamd()
            # Send zINSTREAM command
            sock.sendall(b"zINSTREAM\0")

            chunk_size = 32768
            offset = 0
            total_len = len(content)

            while offset < total_len:
                chunk = content[offset : offset + chunk_size]
                chunk_len = len(chunk)
                sock.sendall(struct.pack(">I", chunk_len))
                sock.sendall(chunk)
                offset += chunk_len

            # Send EOF (0 length chunk)
            sock.sendall(struct.pack(">I", 0))

            # Read response
            response_chunks = []
            while True:
                data = sock.recv(4096)
                if not data:
                    break
                response_chunks.append(data)
                if b"\0" in data or b"\n" in data:
                    break

            raw_resp = b"".join(response_chunks).decode("utf-8", errors="replace").strip("\0\n\r ")
            logger.info("ClamAV response for '%s': %s", filename, raw_resp)

            # Analyze response: "stream: OK" or "stream: Win.Test.EICAR_HDB-1 FOUND"
            if "OK" in raw_resp:
                return ScanStatus.CLEAN, "Clean (ClamAV verified)"
            elif "FOUND" in raw_resp:
                parts = raw_resp.split()
                virus_name = parts[1] if len(parts) > 1 else "Unknown-Malware"
                logger.warning("ClamAV detected malware in %s: %s", filename, virus_name)
                return ScanStatus.INFECTED, f"Infected: {virus_name}"
            else:
                logger.error("ClamAV returned unexpected response for %s: %s", filename, raw_resp)
                raise ScannerUnavailableError(f"Unexpected ClamAV response: {raw_resp}")

        except ScannerUnavailableError:
            raise
        except Exception as e:
            logger.error("Error communicating with ClamAV: %s", e)
            raise ScannerUnavailableError(f"ClamAV communication failure: {e}") from e
        finally:
            if sock:
                try:
                    sock.close()
                except Exception:
                    pass


# Singleton scanner instance
_scanner_instance: Optional[MalwareScanner] = None

def get_scanner() -> MalwareScanner:
    global _scanner_instance
    if _scanner_instance is None:
        _scanner_instance = MalwareScanner()
    return _scanner_instance
