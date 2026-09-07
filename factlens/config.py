from pathlib import Path
import os

BASE_DIR = Path(__file__).resolve().parent.parent

class Settings:
    BASE_DIR: Path = BASE_DIR
    HOST: str = os.getenv("FACTLENS_HOST", "0.0.0.0")
    PORT: int = int(os.getenv("FACTLENS_PORT", "8000"))
    DEBUG: bool = os.getenv("FACTLENS_DEBUG", "true").lower() in ("true", "1", "yes")
    
    DB_PATH: Path = BASE_DIR / os.getenv("FACTLENS_DB_PATH", "data/factlens.db")
    UPLOAD_DIR: Path = BASE_DIR / os.getenv("UPLOAD_DIR", "data/uploads")
    
    MAX_FILE_SIZE_MB: int = int(os.getenv("MAX_FILE_SIZE_MB", "50"))
    MAX_PAGE_COUNT: int = int(os.getenv("MAX_PAGE_COUNT", "120"))
    ALLOWED_EXTENSIONS: set = {"pdf"}
    
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "").strip()
    API_SECRET_KEY: str = os.getenv("API_SECRET_KEY", "").strip()

    # Redis & Caching
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0")
    REDIS_CACHE_ENABLED: bool = os.getenv("REDIS_CACHE_ENABLED", "true").lower() in ("true", "1", "yes")
    CACHE_TTL_DEFAULT: int = int(os.getenv("CACHE_TTL_DEFAULT", "3600"))
    CACHE_TTL_FACTS: int = int(os.getenv("CACHE_TTL_FACTS", "86400"))

    # Malware Scanning (ClamAV)
    MALWARE_SCAN_MODE: str = os.getenv("MALWARE_SCAN_MODE", "dev_mock").lower()  # clamav, dev_mock, fail_closed
    CLAMAV_HOST: str = os.getenv("CLAMAV_HOST", "127.0.0.1")
    CLAMAV_PORT: int = int(os.getenv("CLAMAV_PORT", "3310"))
    CLAMAV_SOCKET: str = os.getenv("CLAMAV_SOCKET", "/var/run/clamav/clamd.ctl")
    CLAMAV_TIMEOUT_SECONDS: int = int(os.getenv("CLAMAV_TIMEOUT_SECONDS", "10"))

    # Background Job Queue
    QUEUE_MODE: str = os.getenv("QUEUE_MODE", "redis").lower()  # redis, thread
    QUEUE_MAX_RETRIES: int = int(os.getenv("QUEUE_MAX_RETRIES", "3"))
    JOB_TIMEOUT_SECONDS: int = int(os.getenv("JOB_TIMEOUT_SECONDS", "120"))

    @classmethod
    def init_dirs(cls) -> None:
        cls.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        cls.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

settings = Settings()

settings.init_dirs()
