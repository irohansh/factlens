import os
import uuid
import shutil
from pathlib import Path
from typing import List, Optional, Dict, Any
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Query, Request
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
    ShowcaseCase
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
from factlens import db

app = FastAPI(
    title="FactLens API",
    description="Evidence-Grounded Fact Knowledge Layer for Multi-PDF Analysis",
    version="1.0.0"
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
    return {
        "status": "healthy",
        "llm_mode": "gemini_enabled" if bool(settings.GEMINI_API_KEY) else "deterministic_offline",
        "has_gemini_key": bool(settings.GEMINI_API_KEY),
        "max_file_size_mb": settings.MAX_FILE_SIZE_MB,
        "max_page_count": settings.MAX_PAGE_COUNT,
        "db_path": str(settings.DB_PATH)
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
@app.post("/api/upload", response_model=List[DocumentMetadata])
async def upload_pdfs(files: List[UploadFile] = File(...)):
    if not files:
        raise HTTPException(status_code=400, detail="No files provided for upload.")

    uploaded_docs: List[DocumentMetadata] = []

    for file in files:
        try:
            content = await file.read()
            # 1. Security validation on bytes
            is_valid, err = validate_pdf_bytes(content)
            if not is_valid:
                raise SecurityError(err)

            # 2. Filename sanitization
            safe_name = sanitize_filename(file.filename or "upload.pdf")
            doc_id = f"doc_{uuid.uuid4().hex[:12]}"
            doc_dir = settings.UPLOAD_DIR / doc_id
            doc_dir.mkdir(parents=True, exist_ok=True)
            saved_path = doc_dir / safe_name

            # 3. Write file safely to isolated storage
            with open(saved_path, "wb") as f_out:
                f_out.write(content)

            sha256 = compute_sha256(content)

            # 4. Extract pages & check page limit
            pages = extract_pdf_pages(saved_path, doc_id)
            
            doc_meta = DocumentMetadata(
                id=doc_id,
                filename=safe_name,
                original_name=file.filename or safe_name,
                file_size_bytes=len(content),
                page_count=len(pages),
                sha256_hash=sha256,
                status="uploaded"
            )

            # 5. Persist document & pages to DB
            db.save_document(doc_meta)
            db.save_pages(pages)
            uploaded_docs.append(doc_meta)

        except SecurityError as se:
            raise HTTPException(status_code=400, detail=str(se))
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Error processing {file.filename}: {e}")

    return uploaded_docs

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
            # If pages not in DB, re-extract from disk
            doc_dir = settings.UPLOAD_DIR / doc.id
            pdf_files = list(doc_dir.glob("*.pdf"))
            if pdf_files:
                pages = extract_pdf_pages(pdf_files[0], doc.id)
                db.save_pages(pages)

        # Extract facts & failures
        facts, failures = fact_extractor.extract_document(pages, doc.filename, force_deterministic)
        
        db.save_facts(facts)
        db.save_failures(failures)
        db.update_document_status(doc.id, "processed", page_count=len(pages))

        total_facts_extracted += len(facts)
        total_failures_recorded += len(failures)

    # Cross-document reconciliation on ALL extracted facts
    all_facts = db.get_facts()
    comparisons = cross_doc_reconciler.reconcile_facts(all_facts)
    db.save_comparisons(comparisons)

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
    return db.get_comparisons(relationship)

# --- Extraction Failures Audit Endpoint ---
@app.get("/api/failures", response_model=List[ExtractionFailure])
def get_failures(document_id: Optional[str] = None):
    return db.get_failures(document_id)

# --- Showcase Cases Endpoint (Starter Datasets) ---
@app.get("/api/cases", response_model=List[ShowcaseCase])
def get_showcase_cases():
    return get_starter_showcase_cases()

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

    return {
        "status": "success",
        "seeded_cases": len(cases),
        "seeded_facts": len(facts_to_save),
        "seeded_comparisons": len(cmps_to_save),
        "seeded_failures": len(fails_to_save)
    }

# Serve static frontend assets
static_dir = settings.BASE_DIR / "static"
static_dir.mkdir(parents=True, exist_ok=True)
app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="static")
