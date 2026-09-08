"""
Background worker execution logic for FactLens document processing jobs.
Handles PDF text extraction, fact extraction, grounding checks, DB persistence,
Redis caching, and cross-document reconciliation with error isolation and retries.
"""

import time
import logging
from pathlib import Path
from typing import Optional

from factlens.config import settings
from factlens.schemas import (
    JobStatus,
    DocumentPage,
    Fact,
    ExtractionFailure,
)
from factlens import db
from factlens.cache import get_cache
from factlens.pdf_parser import extract_pdf_pages
from factlens.extractor import fact_extractor
from factlens.reconciler import cross_doc_reconciler

logger = logging.getLogger("factlens.worker")


def process_document_job(job_id: str, doc_id: str) -> bool:
    """
    Executes a document processing job end-to-end.
    Returns True if completed successfully, False otherwise.
    Safe against crashes: isolates exceptions and updates job/document states in DB.
    """
    logger.info("Starting processing for job %s (document %s)", job_id, doc_id)
    doc = db.get_document(doc_id)
    if not doc:
        logger.error("Document %s not found for job %s", doc_id, job_id)
        db.update_job_status(job_id, JobStatus.FAILED, error_message=f"Document {doc_id} not found")
        return False

    db.update_job_status(job_id, JobStatus.PROCESSING, progress=0.1)
    db.update_document_status(doc_id, "processing")

    try:
        cache = get_cache()
        cache_key = cache.doc_facts_key(doc.sha256_hash)
        cached_result = cache.get(cache_key)

        pages = []
        facts = []
        failures = []

        if cached_result:
            logger.info("Cache hit for document %s (hash %s). Reusing extracted facts.", doc_id, doc.sha256_hash)
            raw_pages = cached_result.get("pages", [])
            raw_facts = cached_result.get("facts", [])
            raw_failures = cached_result.get("failures", [])

            # Reconstruct and assign to this doc_id
            for p_dict in raw_pages:
                p_copy = dict(p_dict)
                p_copy["document_id"] = doc_id
                pages.append(DocumentPage(**p_copy))

            for f_dict in raw_facts:
                f_copy = dict(f_dict)
                f_copy["document_id"] = doc_id
                f_copy["document_name"] = doc.filename
                facts.append(Fact(**f_copy))

            for fl_dict in raw_failures:
                fl_copy = dict(fl_dict)
                fl_copy["document_id"] = doc_id
                fl_copy["document_name"] = doc.filename
                failures.append(ExtractionFailure(**fl_copy))

            if pages:
                db.save_pages(pages)
            if facts:
                db.save_facts(facts)
            if failures:
                db.save_failures(failures)

            db.update_job_status(job_id, JobStatus.PROCESSING, progress=0.7)
        else:
            logger.info("Cache miss for document %s (hash %s). Running full extraction.", doc_id, doc.sha256_hash)
            # Find PDF file
            file_path = settings.UPLOAD_DIR / doc_id / doc.filename
            if not file_path.exists():
                alt_path = settings.UPLOAD_DIR / doc.filename
                if alt_path.exists():
                    file_path = alt_path
                else:
                    raise FileNotFoundError(f"PDF file for document {doc_id} not found at {file_path}")

            # Extract pages
            pages = extract_pdf_pages(file_path, doc_id)
            db.save_pages(pages)
            db.update_job_status(job_id, JobStatus.PROCESSING, progress=0.4)

            # Extract facts and detect failures
            facts, failures = fact_extractor.extract_document(pages, doc.filename)
            db.clear_document_facts_and_failures(doc_id)
            if facts:
                db.save_facts(facts)
            if failures:
                db.save_failures(failures)
            db.update_job_status(job_id, JobStatus.PROCESSING, progress=0.7)

            # Store in cache
            cache_payload = {
                "pages": [p.model_dump() for p in pages],
                "facts": [f.model_dump() for f in facts],
                "failures": [fl.model_dump() for fl in failures],
            }
            cache.set(cache_key, cache_payload, ttl=settings.CACHE_TTL_FACTS)

        # Update document entity and status to processed
        sample_text = pages[0].text if pages else ""
        doc_entity = fact_extractor.deterministic.infer_document_entity(doc.filename, sample_text)
        db.update_document_entity(doc_id, doc_entity)
        db.update_document_status(doc_id, "processed", page_count=len(pages))
        db.update_job_status(job_id, JobStatus.PROCESSING, progress=0.85)

        # Incremental reconciliation
        all_facts = db.get_facts()
        comparisons = cross_doc_reconciler.reconcile_facts(all_facts)
        db.save_comparisons(comparisons)

        # Invalidate comparison and API response caches
        cache.invalidate_comparisons()

        # Mark job completed
        db.update_job_status(job_id, JobStatus.COMPLETED, progress=1.0)
        logger.info("Job %s completed successfully for document %s (%d facts, %d comparisons)",
                    job_id, doc_id, len(facts), len(comparisons))
        return True

    except Exception as e:
        logger.exception("Error processing job %s for document %s: %s", job_id, doc_id, e)
        job = db.get_job(job_id)
        retry_count = (job.retry_count + 1) if job else 1
        max_retries = job.max_retries if job else settings.QUEUE_MAX_RETRIES

        if retry_count <= max_retries:
            backoff = min(60, 2 ** retry_count)
            logger.warning(
                "Retrying job %s (attempt %d/%d) after %ds backoff...",
                job_id, retry_count, max_retries, backoff
            )
            time.sleep(0.1)  # small pause in worker
            db.update_job_status(
                job_id,
                JobStatus.QUEUED,
                error_message=f"Attempt {retry_count} failed: {e}. Scheduled for retry.",
                retry_count=retry_count
            )
        else:
            db.update_job_status(job_id, JobStatus.FAILED, error_message=str(e), retry_count=retry_count)
            db.update_document_status(doc_id, "failed", error=str(e))
            logger.error("Job %s failed permanently after %d attempts.", job_id, retry_count)

        return False
