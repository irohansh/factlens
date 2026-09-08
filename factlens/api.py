import os
import uuid
import shutil
import logging
from pathlib import Path
from typing import List, Optional, Dict, Any
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Query, Request, status
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

from factlens.config import settings
from factlens.schemas import (
    DocumentMetadata,
    DocumentPage,
    Fact,
    FactComparison,
    ExtractionFailure,
    ShowcaseCase,
    JobRecord,
    JobStatus,
    UploadResponseItem,
    ScanStatus,
)
from factlens.security import (
    sanitize_filename,
    validate_pdf_bytes,
    compute_sha256,
    SecurityError
)
from factlens.pdf_parser import extract_pdf_pages
from factlens.extractor import fact_extractor
from factlens.reconciler import cross_doc_reconciler
from factlens.showcase import get_starter_showcase_cases
from factlens.cache import get_cache
from factlens.scanner import get_scanner, ScannerUnavailableError
from factlens.queue import get_queue
from factlens import db

logger = logging.getLogger("factlens.api")

from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize background queue consumers on startup, clean up on shutdown."""
    try:
        if not settings.IS_VERCEL:
            get_queue().start()
    except Exception as e:
        logger.warning(f"Failed to start background queue consumers: {e}")
    yield
    try:
        if not settings.IS_VERCEL:
            get_queue().stop()
    except Exception:
        pass


app = FastAPI(
    title="FactLens API",
    description="Evidence-Grounded Fact Knowledge Layer for Multi-PDF Analysis",
    version="1.0.0",
    lifespan=lifespan
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Security Headers Middleware
class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        return response

app.add_middleware(SecurityHeadersMiddleware)

# Initialize database
db.init_db()

# --- Health & Config Endpoints ---
@app.get("/api/health")
def health_check():
    cache = get_cache()
    scanner = get_scanner()
    return {
        "status": "healthy",
        "llm_mode": "gemini_enabled" if bool(settings.GEMINI_API_KEY) else "deterministic_offline",
        "has_gemini_key": bool(settings.GEMINI_API_KEY),
        "max_file_size_mb": settings.MAX_FILE_SIZE_MB,
        "max_page_count": settings.MAX_PAGE_COUNT,
        "db_path": str(settings.DB_PATH),
        "redis_connected": cache.is_available(),
        "malware_scan_mode": scanner.mode,
        "queue_mode": settings.QUEUE_MODE,
    }

@app.post("/api/settings/api_key")
def update_api_key(payload: Dict[str, str]):
    new_key = payload.get("api_key", "").strip()
    settings.GEMINI_API_KEY = new_key
    # Reinitialize LLM client in extractor
    from factlens.extractor import LLMExtractor
    fact_extractor.llm = LLMExtractor(api_key=new_key) if new_key else None
    return {
        "status": "success",
        "has_gemini_key": bool(new_key),
        "llm_mode": "gemini_enabled" if bool(new_key) else "deterministic_offline"
    }

# --- PDF Upload Endpoint ---
@app.post("/api/upload", response_model=List[UploadResponseItem], status_code=status.HTTP_202_ACCEPTED)
async def upload_pdfs(files: List[UploadFile] = File(...)):
    if not files:
        raise HTTPException(status_code=400, detail="No files provided for upload.")

    uploaded_responses: List[UploadResponseItem] = []
    scanner = get_scanner()
    queue = get_queue()

    for file in files:
        try:
            content = await file.read()

            # 1. Security validation on bytes (magic bytes and size limit)
            is_valid, err = validate_pdf_bytes(content)
            if not is_valid:
                raise SecurityError(err)

            # 2. Filename sanitization
            safe_name = sanitize_filename(file.filename or "upload.pdf")

            # 3. Malware scanning before storing or parsing
            try:
                scan_status, scan_detail = scanner.scan_bytes(content, filename=safe_name)
            except ScannerUnavailableError as sue:
                logger.error("Malware scanner unavailable (fail-closed): %s", sue)
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail=f"Malware scanner unavailable (fail-closed policy enforced): {sue}"
                )

            if scan_status == ScanStatus.INFECTED:
                logger.warning("Rejected malicious upload '%s': %s", safe_name, scan_detail)
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Security violation: Malware signature detected in file ({scan_detail})."
                )

            # 4. SHA-256 hash calculation for duplicate detection
            sha256 = compute_sha256(content)

            # 5. Check if document already exists by content hash
            existing_doc = db.get_document_by_hash(sha256)
            if existing_doc:
                active_job = db.get_active_job_by_doc_id(existing_doc.id)
                uploaded_responses.append(UploadResponseItem(
                    document=existing_doc,
                    job_id=active_job.id if active_job else None,
                    is_duplicate=True,
                    message=f"Duplicate detected via SHA-256 ({sha256[:12]}...). Reusing existing document '{existing_doc.filename}'."
                ))
                continue

            # 6. Fresh document setup
            doc_id = f"doc_{uuid.uuid4().hex[:12]}"
            doc_dir = settings.UPLOAD_DIR / doc_id
            doc_dir.mkdir(parents=True, exist_ok=True)
            saved_path = doc_dir / safe_name

            with open(saved_path, "wb") as f_out:
                f_out.write(content)

            doc_entity = fact_extractor.deterministic.infer_document_entity(file.filename or safe_name, "")
            doc_meta = DocumentMetadata(
                id=doc_id,
                filename=safe_name,
                original_name=file.filename or safe_name,
                file_size_bytes=len(content),
                page_count=0,
                sha256_hash=sha256,
                status="queued",
                scan_status=scan_status.value,
                scan_result=scan_detail,
                entity=doc_entity
            )

            # Atomically insert into DB enforcing sha256 uniqueness constraint
            inserted, current_doc = db.create_document_atomic(doc_meta)
            if not inserted:
                # Concurrent duplicate upload intercepted by database constraint
                active_job = db.get_active_job_by_doc_id(current_doc.id)
                uploaded_responses.append(UploadResponseItem(
                    document=current_doc,
                    job_id=active_job.id if active_job else None,
                    is_duplicate=True,
                    message=f"Duplicate document detected during concurrent insert. Reusing '{current_doc.filename}'."
                ))
                continue

            # 7. Create background job record
            job = JobRecord(
                document_id=current_doc.id,
                status=JobStatus.QUEUED,
                progress=0.0
            )
            db.create_job(job)

            # 8. Enqueue to background worker queue
            queue.enqueue(job.id, current_doc.id)

            uploaded_responses.append(UploadResponseItem(
                document=current_doc,
                job_id=job.id,
                is_duplicate=False,
                message="Document uploaded and queued for background processing."
            ))

        except SecurityError as se:
            raise HTTPException(status_code=400, detail=str(se))
        except HTTPException:
            raise
        except Exception as e:
            logger.exception("Unexpected error during upload of %s: %s", getattr(file, 'filename', 'unknown'), e)
            raise HTTPException(status_code=500, detail=f"Error processing {file.filename}: {e}")

    return uploaded_responses

# --- Background Jobs Endpoints ---
@app.get("/api/jobs/{job_id}", response_model=JobRecord)
def get_job_status(job_id: str):
    job = db.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found.")
    return job

@app.get("/api/jobs", response_model=List[JobRecord])
def list_all_jobs():
    return db.list_jobs()

# --- Document Inspection Endpoints ---
@app.get("/api/documents", response_model=List[DocumentMetadata])
def list_documents():
    return db.list_documents()

@app.get("/api/documents/{doc_id}")
def get_document_details(doc_id: str):
    doc = db.get_document(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail=f"Document {doc_id} not found.")
    pages = db.get_pages(doc_id)
    return {
        "metadata": doc,
        "page_count": len(pages),
        "pages": [{"page_number": p.page_number, "char_count": p.char_count, "text_snippet": p.text[:300]} for p in pages]
    }

# --- Fact Extraction & Reconciliation Pipeline ---
@app.post("/api/process")
def process_pipeline(
    doc_ids: Optional[List[str]] = None,
    force_deterministic: bool = False
):
    docs = db.list_documents()
    if doc_ids:
        docs = [d for d in docs if d.id in doc_ids]

    if not docs:
        raise HTTPException(status_code=400, detail="No documents available to process.")

    total_facts_extracted = 0
    total_failures_recorded = 0

    for doc in docs:
        db.update_document_status(doc.id, "processing")
        pages = db.get_pages(doc.id)
        if not pages:
            doc_dir = settings.UPLOAD_DIR / doc.id
            pdf_files = list(doc_dir.glob("*.pdf"))
            if pdf_files:
                pages = extract_pdf_pages(pdf_files[0], doc.id)
                db.save_pages(pages)

        facts, failures = fact_extractor.extract_document(pages, doc.filename, force_deterministic)
        
        sample_text = pages[0].text if pages else ""
        doc_entity = fact_extractor.deterministic.infer_document_entity(doc.filename, sample_text)
        db.update_document_entity(doc.id, doc_entity)
        db.clear_document_facts_and_failures(doc.id)
        db.save_facts(facts)
        db.save_failures(failures)
        db.update_document_status(doc.id, "processed", page_count=len(pages))

        total_facts_extracted += len(facts)
        total_failures_recorded += len(failures)

    all_facts = db.get_facts()
    comparisons = cross_doc_reconciler.reconcile_facts(all_facts)
    db.save_comparisons(comparisons)

    # Invalidate cached comparisons and api responses
    cache = get_cache()
    cache.invalidate_comparisons()
    cache.delete(cache.api_response_key("cases"))

    return {
        "status": "success",
        "processed_documents": len(docs),
        "facts_extracted": total_facts_extracted,
        "comparisons_found": len(comparisons),
        "failures_recorded": total_failures_recorded
    }

# --- Fact Query Endpoint ---
@app.get("/api/facts", response_model=List[Fact])
def get_facts(
    document_id: Optional[str] = None,
    entity: Optional[str] = None,
    metric: Optional[str] = None,
    search: Optional[str] = None
):
    return db.get_facts(document_id, entity, metric, search)

# --- Cross-Document Comparisons Endpoint ---
@app.get("/api/comparisons", response_model=List[FactComparison])
def get_comparisons(relationship: Optional[str] = None):
    cache = get_cache()
    cache_key = cache.comparisons_key(relationship or "all")
    cached = cache.get(cache_key)
    if cached and isinstance(cached, list):
        return [FactComparison(**c) for c in cached]

    cmps = db.get_comparisons(relationship)
    cache.set(cache_key, [c.model_dump() for c in cmps], ttl=settings.CACHE_TTL_DEFAULT)
    return cmps

# --- Extraction Failures Audit Endpoint ---
@app.get("/api/failures", response_model=List[ExtractionFailure])
def get_failures(document_id: Optional[str] = None):
    return db.get_failures(document_id)

# --- Showcase Cases Endpoint (Starter Datasets) ---
@app.get("/api/cases", response_model=List[ShowcaseCase])
def get_showcase_cases():
    cache = get_cache()
    cache_key = cache.api_response_key("cases")
    cached = cache.get(cache_key)
    if cached and isinstance(cached, list):
        return [ShowcaseCase(**c) for c in cached]

    cases = get_starter_showcase_cases()
    cache.set(cache_key, [c.model_dump() for c in cases], ttl=settings.CACHE_TTL_DEFAULT)
    return cases

@app.post("/api/seed_starter_cases")
def seed_starter_cases():
    """Seeds the starter cases into the live database so they populate all queries."""
    cases = get_starter_showcase_cases()
    facts_to_save: List[Fact] = []
    cmps_to_save: List[FactComparison] = []
    fails_to_save: List[ExtractionFailure] = []

    for c in cases:
        if c.facts:
            facts_to_save.extend(c.facts)
        if c.comparison:
            cmps_to_save.append(c.comparison)
        if c.failure:
            fails_to_save.append(c.failure)

    if facts_to_save:
        db.save_facts(facts_to_save)
    if cmps_to_save:
        db.save_comparisons(cmps_to_save)
    if fails_to_save:
        db.save_failures(fails_to_save)

    cache = get_cache()
    cache.invalidate_comparisons()
    cache.delete(cache.api_response_key("cases"))

    return {
        "status": "success",
        "seeded_cases": len(cases),
        "seeded_facts": len(facts_to_save),
        "seeded_comparisons": len(cmps_to_save),
        "seeded_failures": len(fails_to_save)
    }

# Serve static frontend assets
static_dir = settings.BASE_DIR / "static"
try:
    static_dir.mkdir(parents=True, exist_ok=True)
except OSError:
    pass
if static_dir.exists():
    app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="static")

