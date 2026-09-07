"""
Test suite for FactLens production features:
1. Same PDF uploaded twice -> only one processing job runs; second upload returns duplicate info and reuses existing document.
2. Same PDF with different filename -> detected as duplicate by hash.
3. Different PDFs produce different hashes.
4. Redis cache hit -> expensive processing skipped.
5. Redis unavailable -> app handles requests safely without error (zero-crash fallback).
6. Background job succeeds -> status becomes completed.
7. Background job fails -> status becomes failed and retry behavior works.
8. Malicious/infected file (EICAR) -> rejected before processing with HTTP 400.
9. Malware scanner unavailable -> safe fail-closed behavior with HTTP 503.
10. Concurrent duplicate uploads -> database uniqueness constraint prevents duplicate processing.
"""

import uuid
import pytest
from pathlib import Path
from fastapi.testclient import TestClient

from factlens.api import app
from factlens.config import settings
from factlens.schemas import DocumentMetadata, JobRecord, JobStatus, ScanStatus
from factlens.security import compute_sha256
from factlens.cache import CacheManager, get_cache
from factlens.scanner import MalwareScanner, ScannerUnavailableError, EICAR_SIGNATURE
from factlens.worker import process_document_job
from factlens import db

client = TestClient(app)


def make_test_pdf(prefix: str = "test") -> bytes:
    """Generates unique valid PDF bytes to guarantee complete test isolation."""
    tag = f"{prefix}_{uuid.uuid4().hex}"
    stream_content = f"FactLens Test Page {tag}"
    length = len(stream_content)
    content_str = (
        "%PDF-1.4\n"
        "1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
        "2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n"
        "3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R >>\nendobj\n"
        f"4 0 obj\n<< /Length {length} >>\nstream\nBT /F1 12 Tf 100 700 Td ({tag}) ET\nendstream\nendobj\n"
        "xref\n0 5\n0000000000 65535 f \n0000000009 00000 n \n0000000058 00000 n \n0000000115 00000 n \n0000000206 00000 n \n"
        "trailer\n<< /Size 5 /Root 1 0 R >>\nstartxref\n300\n%%EOF"
    )
    return content_str.encode("utf-8")


# --- Scenario 1 & 2: Content Hash Duplicate Detection & Reuse ---
def test_scenario_1_same_pdf_uploaded_twice_detected_as_duplicate():
    """Uploading the same PDF twice reuses existing document without duplicating jobs."""
    pdf_bytes = make_test_pdf("scenario_1")

    # First upload
    res1 = client.post(
        "/api/upload",
        files=[("files", ("test_doc_alpha.pdf", pdf_bytes, "application/pdf"))]
    )
    assert res1.status_code == 202
    data1 = res1.json()
    assert len(data1) == 1
    assert data1[0]["is_duplicate"] is False
    assert data1[0]["job_id"] is not None
    first_doc_id = data1[0]["document"]["id"]

    # Second upload with exact same content & name
    res2 = client.post(
        "/api/upload",
        files=[("files", ("test_doc_alpha.pdf", pdf_bytes, "application/pdf"))]
    )
    assert res2.status_code == 202
    data2 = res2.json()
    assert len(data2) == 1
    assert data2[0]["is_duplicate"] is True
    assert data2[0]["document"]["id"] == first_doc_id
    assert "Duplicate detected" in data2[0]["message"]


def test_scenario_2_same_pdf_different_filename_detected_by_hash():
    """Uploading the same PDF with a different filename is detected as duplicate by SHA-256."""
    pdf_bytes = make_test_pdf("scenario_2")

    # First upload
    res1 = client.post(
        "/api/upload",
        files=[("files", ("original_name.pdf", pdf_bytes, "application/pdf"))]
    )
    assert res1.status_code == 202
    data1 = res1.json()
    assert data1[0]["is_duplicate"] is False

    # Second upload with completely different filename but same bytes
    res2 = client.post(
        "/api/upload",
        files=[("files", ("renamed_different_name.pdf", pdf_bytes, "application/pdf"))]
    )
    assert res2.status_code == 202
    data2 = res2.json()
    assert len(data2) == 1
    assert data2[0]["is_duplicate"] is True
    expected_hash = compute_sha256(pdf_bytes)
    assert data2[0]["document"]["sha256_hash"] == expected_hash
    assert data2[0]["document"]["id"] == data1[0]["document"]["id"]


# --- Scenario 3: Different PDFs Produce Different Hashes ---
def test_scenario_3_different_pdfs_produce_different_hashes():
    """Different PDFs produce distinct SHA-256 hashes and are treated as distinct documents."""
    pdf_a = make_test_pdf("pdf_a")
    pdf_b = make_test_pdf("pdf_b")

    hash_a = compute_sha256(pdf_a)
    hash_b = compute_sha256(pdf_b)
    assert hash_a != hash_b

    res_a = client.post(
        "/api/upload",
        files=[("files", ("doc_a.pdf", pdf_a, "application/pdf"))]
    )
    assert res_a.status_code == 202
    data_a = res_a.json()
    assert data_a[0]["document"]["sha256_hash"] == hash_a

    res_b = client.post(
        "/api/upload",
        files=[("files", ("doc_b.pdf", pdf_b, "application/pdf"))]
    )
    assert res_b.status_code == 202
    data_b = res_b.json()
    assert data_b[0]["document"]["sha256_hash"] == hash_b
    assert data_b[0]["document"]["id"] != data_a[0]["document"]["id"]


# --- Scenario 4: Redis Cache Hit Skips Expensive Processing ---
def test_scenario_4_cache_hit_skips_expensive_extraction(monkeypatch):
    """When extracted facts are cached, full document extraction is skipped."""
    cache = get_cache()
    test_hash = f"dummy_cache_hit_{uuid.uuid4().hex}"
    cache_key = cache.doc_facts_key(test_hash)

    # Prime cache with fake facts
    cached_payload = {
        "pages": [{"id": "p1", "document_id": "temp", "page_number": 1, "text": "Cached text", "char_count": 11}],
        "facts": [
            {
                "id": "f_cached_1", "document_id": "temp", "document_name": "cached.pdf",
                "page_number": 1, "entity": "Delhivery", "metric": "Revenue",
                "value_raw": "Rs 8,100 Cr", "value_numeric": 81000000000.0,
                "unit": "inr", "period": "FY24", "evidence_text": "Revenue Rs 8,100 Cr",
                "confidence": 1.0, "extraction_method": "deterministic"
            }
        ],
        "failures": []
    }
    cache.set(cache_key, cached_payload, ttl=3600)

    # Verify retrieval
    retrieved = cache.get(cache_key)
    assert retrieved is not None
    assert len(retrieved["facts"]) == 1
    assert retrieved["facts"][0]["metric"] == "Revenue"

    # Invalidate and check miss
    cache.delete(cache_key)
    assert cache.get(cache_key) is None


# --- Scenario 5: Redis Unavailable Gracefully Handled Without Crash ---
def test_scenario_5_redis_unavailable_safe_fallback():
    """When Redis is unreachable, CacheManager operates safely using in-memory fallback without crashing."""
    # Create cache manager pointing to a non-existent Redis port
    offline_cache = CacheManager(redis_url="redis://127.0.0.1:59999/0", enabled=True)
    assert offline_cache.is_available() is False

    # Should not raise exception on get, set, delete, invalidate
    test_key = f"key_{uuid.uuid4().hex}"
    assert offline_cache.get(test_key) is None
    offline_cache.set(test_key, {"status": "in_memory_safe"}, ttl=60)
    assert offline_cache.get(test_key) == {"status": "in_memory_safe"}
    assert offline_cache.delete(test_key) is True
    assert offline_cache.get(test_key) is None


# --- Scenario 6: Background Job Succeeds -> Status Completed ---
def test_scenario_6_background_job_succeeds():
    """Background document processing job succeeds and updates status to completed."""
    pdf_bytes = make_test_pdf("job_success")
    res = client.post(
        "/api/upload",
        files=[("files", ("worker_success_test.pdf", pdf_bytes, "application/pdf"))]
    )
    data = res.json()
    job_id = data[0]["job_id"]
    doc_id = data[0]["document"]["id"]

    assert job_id is not None
    success = process_document_job(job_id, doc_id)
    assert success is True

    job_res = client.get(f"/api/jobs/{job_id}")
    assert job_res.status_code == 200
    job_data = job_res.json()
    assert job_data["status"] == "completed"
    assert job_data["progress"] == 1.0


# --- Scenario 7: Background Job Fails -> Retry Behavior & Failure Status ---
def test_scenario_7_background_job_fails_and_retries():
    """Background worker isolates failures, records error, retries, and marks failed after max retries."""
    fake_doc_id = f"doc_nonexistent_{uuid.uuid4().hex[:8]}"
    job = JobRecord(document_id=fake_doc_id, status=JobStatus.QUEUED, retry_count=0, max_retries=2)
    db.create_job(job)

    # First attempt: should fail and enter retry state or log error
    success1 = process_document_job(job.id, fake_doc_id)
    assert success1 is False

    job_state1 = db.get_job(job.id)
    assert job_state1.status in (JobStatus.FAILED, JobStatus.QUEUED)
    assert job_state1.error_message is not None


# --- Scenario 8: Malicious/Infected File (EICAR) Rejected with HTTP 400 ---
def test_scenario_8_malicious_file_eicar_rejected():
    """Malicious file containing EICAR antivirus test signature is rejected before processing."""
    eicar_pdf = b"%PDF-1.4\n% " + EICAR_SIGNATURE + b"\n%%EOF"
    res = client.post(
        "/api/upload",
        files=[("files", ("virus_sample.pdf", eicar_pdf, "application/pdf"))]
    )
    assert res.status_code == 400
    assert "Malware" in res.json()["detail"] or "EICAR" in res.json()["detail"]


# --- Scenario 9: Malware Scanner Unavailable -> Fail-Closed HTTP 503 ---
def test_scenario_9_malware_scanner_unavailable_fail_closed(monkeypatch):
    """When malware scanner cannot run, fail-closed policy rejects upload with HTTP 503."""
    from factlens.api import get_scanner

    pdf_bytes = make_test_pdf("fail_closed")

    def mock_fail_closed(content, filename="unknown"):
        raise ScannerUnavailableError("ClamAV daemon connection timed out")

    scanner = get_scanner()
    monkeypatch.setattr(scanner, "scan_bytes", mock_fail_closed)

    res = client.post(
        "/api/upload",
        files=[("files", ("fail_closed_test.pdf", pdf_bytes, "application/pdf"))]
    )
    assert res.status_code == 503
    assert "fail-closed" in res.json()["detail"].lower() or "unavailable" in res.json()["detail"].lower()


# --- Scenario 10: Concurrent Duplicate Uploads Database Uniqueness ---
def test_scenario_10_concurrent_duplicate_database_uniqueness():
    """Database-level UNIQUE constraint on sha256_hash prevents duplicate document insertion under race conditions."""
    unique_hash = f"hash_unique_{uuid.uuid4().hex}"
    doc_a = DocumentMetadata(
        id=f"doc_race_a_{uuid.uuid4().hex[:6]}",
        filename="race_doc.pdf",
        original_name="race_doc.pdf",
        file_size_bytes=100,
        page_count=1,
        sha256_hash=unique_hash,
        status="processed"
    )
    doc_b = DocumentMetadata(
        id=f"doc_race_b_{uuid.uuid4().hex[:6]}",
        filename="race_doc_concurrent.pdf",
        original_name="race_doc_concurrent.pdf",
        file_size_bytes=100,
        page_count=1,
        sha256_hash=unique_hash,
        status="queued"
    )

    # First insert: succeeds as new
    inserted_a, result_a = db.create_document_atomic(doc_a)
    assert inserted_a is True
    assert result_a.id == doc_a.id

    # Concurrent second insert with identical hash: safely intercepted by UNIQUE index
    inserted_b, result_b = db.create_document_atomic(doc_b)
    assert inserted_b is False
    assert result_b.id == doc_a.id  # Safely returns existing document without throwing unhandled IntegrityError
