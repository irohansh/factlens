import sqlite3
import json
from pathlib import Path
from typing import List, Optional, Dict, Any
from contextlib import contextmanager

from factlens.config import settings
from factlens.schemas import (
    DocumentMetadata,
    DocumentPage,
    Fact,
    FactComparison,
    ExtractionFailure,
    RelationshipType,
    DifferenceType,
    FailureType,
    JobRecord,
    JobStatus,
    ScanStatus,
    utc_now_iso
)

def get_db_path() -> Path:
    try:
        settings.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    except (OSError, PermissionError):
        pass
    return settings.DB_PATH


@contextmanager
def get_db_cursor():
    conn = sqlite3.connect(str(get_db_path()), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    try:
        yield cursor
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def init_db() -> None:
    """Initializes SQLite tables with parameterized DDL and migration checks."""
    with get_db_cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS documents (
                id TEXT PRIMARY KEY,
                filename TEXT NOT NULL,
                original_name TEXT NOT NULL,
                file_size_bytes INTEGER NOT NULL,
                page_count INTEGER NOT NULL,
                sha256_hash TEXT NOT NULL,
                upload_timestamp TEXT NOT NULL,
                status TEXT NOT NULL,
                scan_status TEXT DEFAULT 'pending',
                scan_result TEXT,
                scan_timestamp TEXT,
                error_message TEXT
            )
        """)
        
        # Enforce unique index at database level for content-based duplicate detection
        cur.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_documents_sha256 ON documents(sha256_hash);
        """)

        # Migration helper for documents table if created under older schema
        cur.execute("PRAGMA table_info(documents)")
        existing_cols = {row["name"] for row in cur.fetchall()}
        if "scan_status" not in existing_cols:
            cur.execute("ALTER TABLE documents ADD COLUMN scan_status TEXT DEFAULT 'pending'")
        if "scan_result" not in existing_cols:
            cur.execute("ALTER TABLE documents ADD COLUMN scan_result TEXT")
        if "scan_timestamp" not in existing_cols:
            cur.execute("ALTER TABLE documents ADD COLUMN scan_timestamp TEXT")
        if "entity" not in existing_cols:
            cur.execute("ALTER TABLE documents ADD COLUMN entity TEXT")

        cur.execute("""
            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY,
                document_id TEXT NOT NULL,
                status TEXT NOT NULL,
                progress REAL DEFAULT 0.0,
                retry_count INTEGER DEFAULT 0,
                max_retries INTEGER DEFAULT 3,
                error_message TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE
            );
        """)
        cur.execute("CREATE INDEX IF NOT EXISTS idx_jobs_document_id ON jobs(document_id);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);")

        
        cur.execute("""
            CREATE TABLE IF NOT EXISTS document_pages (
                id TEXT PRIMARY KEY,
                document_id TEXT NOT NULL,
                page_number INTEGER NOT NULL,
                text TEXT NOT NULL,
                char_count INTEGER NOT NULL,
                FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE
            )
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS facts (
                id TEXT PRIMARY KEY,
                document_id TEXT NOT NULL,
                document_name TEXT NOT NULL,
                page_number INTEGER NOT NULL,
                entity TEXT NOT NULL,
                metric TEXT NOT NULL,
                value_raw TEXT NOT NULL,
                value_numeric REAL,
                unit TEXT,
                period TEXT,
                period_start TEXT,
                period_end TEXT,
                as_of_date TEXT,
                scope TEXT,
                evidence_text TEXT NOT NULL,
                evidence_context TEXT,
                confidence REAL NOT NULL,
                extraction_method TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE
            )
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS fact_comparisons (
                id TEXT PRIMARY KEY,
                fact_a_id TEXT NOT NULL,
                fact_b_id TEXT NOT NULL,
                relationship TEXT NOT NULL,
                difference_type TEXT NOT NULL,
                confidence REAL NOT NULL,
                explanation TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (fact_a_id) REFERENCES facts(id) ON DELETE CASCADE,
                FOREIGN KEY (fact_b_id) REFERENCES facts(id) ON DELETE CASCADE
            )
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS extraction_failures (
                id TEXT PRIMARY KEY,
                document_id TEXT NOT NULL,
                document_name TEXT NOT NULL,
                page_number INTEGER NOT NULL,
                failure_type TEXT NOT NULL,
                raw_snippet TEXT NOT NULL,
                explanation TEXT NOT NULL,
                attempted_fact_json TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE
            )
        """)

# Repository Methods
def save_document(doc: DocumentMetadata) -> None:
    with get_db_cursor() as cur:
        cur.execute("""
            INSERT OR REPLACE INTO documents 
            (id, filename, original_name, file_size_bytes, page_count, sha256_hash, upload_timestamp, status, scan_status, scan_result, scan_timestamp, error_message, entity)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            doc.id, doc.filename, doc.original_name, doc.file_size_bytes,
            doc.page_count, doc.sha256_hash, doc.upload_timestamp, doc.status,
            doc.scan_status, doc.scan_result, doc.scan_timestamp, doc.error_message,
            doc.entity
        ))

def get_document(doc_id: str) -> Optional[DocumentMetadata]:
    with get_db_cursor() as cur:
        cur.execute("""
            SELECT d.*, 
                   COALESCE((SELECT COUNT(*) FROM facts f WHERE f.document_id = d.id), 0) AS fact_count
            FROM documents d 
            WHERE d.id = ?
        """, (doc_id,))
        row = cur.fetchone()
        if not row:
            return None
        return DocumentMetadata(**dict(row))

def get_document_by_hash(sha256_hash: str) -> Optional[DocumentMetadata]:
    """Retrieves document by its content SHA256 hash across all filenames."""
    with get_db_cursor() as cur:
        cur.execute("""
            SELECT d.*, 
                   COALESCE((SELECT COUNT(*) FROM facts f WHERE f.document_id = d.id), 0) AS fact_count
            FROM documents d 
            WHERE d.sha256_hash = ?
        """, (sha256_hash,))
        row = cur.fetchone()
        if not row:
            return None
        return DocumentMetadata(**dict(row))

def create_document_atomic(doc: DocumentMetadata) -> tuple[bool, DocumentMetadata]:
    """
    Atomically inserts document enforcing database-level uniqueness on sha256_hash.
    Returns:
        (True, doc) if inserted cleanly as new document.
        (False, existing_doc) if duplicate hash was detected (handles race conditions safely).
    """
    try:
        with get_db_cursor() as cur:
            cur.execute("""
                INSERT INTO documents 
                (id, filename, original_name, file_size_bytes, page_count, sha256_hash, upload_timestamp, status, scan_status, scan_result, scan_timestamp, error_message, entity)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                doc.id, doc.filename, doc.original_name, doc.file_size_bytes,
                doc.page_count, doc.sha256_hash, doc.upload_timestamp, doc.status,
                doc.scan_status, doc.scan_result, doc.scan_timestamp, doc.error_message,
                doc.entity
            ))
        return True, doc
    except sqlite3.IntegrityError:
        # Unique constraint on sha256_hash fired
        existing = get_document_by_hash(doc.sha256_hash)
        if existing:
            return False, existing
        raise

def update_document_scan(
    doc_id: str,
    scan_status: str,
    scan_result: Optional[str] = None,
    scan_timestamp: Optional[str] = None
) -> None:
    ts = scan_timestamp or utc_now_iso()
    with get_db_cursor() as cur:
        cur.execute("""
            UPDATE documents 
            SET scan_status = ?, scan_result = ?, scan_timestamp = ? 
            WHERE id = ?
        """, (scan_status, scan_result, ts, doc_id))

def update_document_entity(doc_id: str, entity: str) -> None:
    with get_db_cursor() as cur:
        cur.execute("UPDATE documents SET entity = ? WHERE id = ?", (entity, doc_id))

def list_documents() -> List[DocumentMetadata]:
    with get_db_cursor() as cur:
        cur.execute("""
            SELECT d.*, 
                   COALESCE((SELECT COUNT(*) FROM facts f WHERE f.document_id = d.id), 0) AS fact_count
            FROM documents d 
            ORDER BY d.upload_timestamp DESC
        """)
        rows = cur.fetchall()
        return [DocumentMetadata(**dict(r)) for r in rows]

def update_document_status(doc_id: str, status: str, page_count: Optional[int] = None, error: Optional[str] = None) -> None:
    with get_db_cursor() as cur:
        if page_count is not None:
            cur.execute("""
                UPDATE documents SET status = ?, page_count = ?, error_message = ? WHERE id = ?
            """, (status, page_count, error, doc_id))
        else:
            cur.execute("""
                UPDATE documents SET status = ?, error_message = ? WHERE id = ?
            """, (status, error, doc_id))

# Job Queue Methods
def create_job(job: JobRecord) -> JobRecord:
    with get_db_cursor() as cur:
        cur.execute("""
            INSERT OR REPLACE INTO jobs 
            (id, document_id, status, progress, retry_count, max_retries, error_message, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            job.id, job.document_id, job.status.value if isinstance(job.status, JobStatus) else job.status,
            job.progress, job.retry_count, job.max_retries, job.error_message,
            job.created_at, job.updated_at
        ))
    return job

def get_job(job_id: str) -> Optional[JobRecord]:
    with get_db_cursor() as cur:
        cur.execute("SELECT * FROM jobs WHERE id = ?", (job_id,))
        row = cur.fetchone()
        if not row:
            return None
        return JobRecord(**dict(row))

def get_active_job_by_doc_id(doc_id: str) -> Optional[JobRecord]:
    """Finds active job ('queued' or 'processing') for a document to prevent duplicate jobs."""
    with get_db_cursor() as cur:
        cur.execute("""
            SELECT * FROM jobs 
            WHERE document_id = ? AND status IN ('queued', 'processing')
            ORDER BY created_at DESC LIMIT 1
        """, (doc_id,))
        row = cur.fetchone()
        if not row:
            return None
        return JobRecord(**dict(row))

def update_job_status(
    job_id: str,
    status: JobStatus | str,
    progress: Optional[float] = None,
    error_message: Optional[str] = None,
    retry_count: Optional[int] = None
) -> None:
    status_val = status.value if isinstance(status, JobStatus) else status
    now = utc_now_iso()
    with get_db_cursor() as cur:
        updates = ["status = ?", "updated_at = ?"]
        params: List[Any] = [status_val, now]
        if progress is not None:
            updates.append("progress = ?")
            params.append(progress)
        if error_message is not None:
            updates.append("error_message = ?")
            params.append(error_message)
        if retry_count is not None:
            updates.append("retry_count = ?")
            params.append(retry_count)
        params.append(job_id)

        cur.execute(f"UPDATE jobs SET {', '.join(updates)} WHERE id = ?", params)

def list_jobs(status: Optional[str] = None) -> List[JobRecord]:
    query = "SELECT * FROM jobs"
    params = []
    if status:
        query += " WHERE status = ?"
        params.append(status)
    query += " ORDER BY created_at DESC"
    with get_db_cursor() as cur:
        cur.execute(query, params)
        rows = cur.fetchall()
        return [JobRecord(**dict(r)) for r in rows]


def save_pages(pages: List[DocumentPage]) -> None:
    with get_db_cursor() as cur:
        cur.executemany("""
            INSERT OR REPLACE INTO document_pages (id, document_id, page_number, text, char_count)
            VALUES (?, ?, ?, ?, ?)
        """, [
            (p.id, p.document_id, p.page_number, p.text, p.char_count)
            for p in pages
        ])

def get_pages(doc_id: str) -> List[DocumentPage]:
    with get_db_cursor() as cur:
        cur.execute("SELECT * FROM document_pages WHERE document_id = ? ORDER BY page_number ASC", (doc_id,))
        rows = cur.fetchall()
        return [DocumentPage(**dict(r)) for r in rows]

def clear_document_facts_and_failures(doc_id: str) -> None:
    with get_db_cursor() as cur:
        cur.execute("DELETE FROM facts WHERE document_id = ?", (doc_id,))
        cur.execute("DELETE FROM extraction_failures WHERE document_id = ?", (doc_id,))

def save_facts(facts: List[Fact]) -> None:
    with get_db_cursor() as cur:
        cur.executemany("""
            INSERT OR REPLACE INTO facts 
            (id, document_id, document_name, page_number, entity, metric, value_raw, value_numeric, unit,
             period, period_start, period_end, as_of_date, scope, evidence_text, evidence_context,
             confidence, extraction_method, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, [
            (
                f.id, f.document_id, f.document_name, f.page_number, f.entity, f.metric,
                f.value_raw, f.value_numeric, f.unit, f.period, f.period_start, f.period_end,
                f.as_of_date, f.scope, f.evidence_text, f.evidence_context, f.confidence,
                f.extraction_method, f.created_at
            )
            for f in facts
        ])

def get_fact(fact_id: str) -> Optional[Fact]:
    with get_db_cursor() as cur:
        cur.execute("SELECT * FROM facts WHERE id = ?", (fact_id,))
        row = cur.fetchone()
        if not row:
            return None
        return Fact(**dict(row))

def get_facts(
    document_id: Optional[str] = None,
    entity: Optional[str] = None,
    metric: Optional[str] = None,
    search: Optional[str] = None
) -> List[Fact]:
    query = "SELECT * FROM facts WHERE 1=1"
    params: List[Any] = []
    
    if document_id:
        query += " AND document_id = ?"
        params.append(document_id)
    if entity:
        query += " AND entity LIKE ?"
        params.append(f"%{entity}%")
    if metric:
        query += " AND metric LIKE ?"
        params.append(f"%{metric}%")
    if search:
        query += " AND (metric LIKE ? OR value_raw LIKE ? OR evidence_text LIKE ? OR entity LIKE ?)"
        params.extend([f"%{search}%", f"%{search}%", f"%{search}%", f"%{search}%"])
        
    query += " ORDER BY page_number ASC"
    
    with get_db_cursor() as cur:
        cur.execute(query, params)
        rows = cur.fetchall()
        return [Fact(**dict(r)) for r in rows]

def save_comparisons(comparisons: List[FactComparison]) -> None:
    with get_db_cursor() as cur:
        cur.executemany("""
            INSERT OR REPLACE INTO fact_comparisons
            (id, fact_a_id, fact_b_id, relationship, difference_type, confidence, explanation, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, [
            (
                c.id, c.fact_a_id, c.fact_b_id, c.relationship.value,
                c.difference_type.value, c.confidence, c.explanation, c.created_at
            )
            for c in comparisons
        ])

def get_comparisons(relationship: Optional[str] = None) -> List[FactComparison]:
    query = "SELECT * FROM fact_comparisons WHERE 1=1"
    params = []
    if relationship:
        query += " AND relationship = ?"
        params.append(relationship)
        
    with get_db_cursor() as cur:
        cur.execute(query, params)
        rows = cur.fetchall()
        results: List[FactComparison] = []
        for r in rows:
            data = dict(r)
            f_a = get_fact(data["fact_a_id"])
            f_b = get_fact(data["fact_b_id"])
            if f_a and f_b:
                results.append(
                    FactComparison(
                        id=data["id"],
                        fact_a_id=data["fact_a_id"],
                        fact_b_id=data["fact_b_id"],
                        fact_a=f_a,
                        fact_b=f_b,
                        relationship=RelationshipType(data["relationship"]),
                        difference_type=DifferenceType(data["difference_type"]),
                        confidence=data["confidence"],
                        explanation=data["explanation"],
                        created_at=data["created_at"]
                    )
                )
        return results

def save_failures(failures: List[ExtractionFailure]) -> None:
    with get_db_cursor() as cur:
        cur.executemany("""
            INSERT OR REPLACE INTO extraction_failures
            (id, document_id, document_name, page_number, failure_type, raw_snippet, explanation, attempted_fact_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, [
            (
                f.id, f.document_id, f.document_name, f.page_number, f.failure_type.value,
                f.raw_snippet, f.explanation, json.dumps(f.attempted_fact) if f.attempted_fact else None,
                f.created_at
            )
            for f in failures
        ])

def get_failures(document_id: Optional[str] = None) -> List[ExtractionFailure]:
    query = "SELECT * FROM extraction_failures WHERE 1=1"
    params = []
    if document_id:
        query += " AND document_id = ?"
        params.append(document_id)
    query += " ORDER BY created_at DESC"
    
    with get_db_cursor() as cur:
        cur.execute(query, params)
        rows = cur.fetchall()
        results: List[ExtractionFailure] = []
        for r in rows:
            d = dict(r)
            attempted = json.loads(d["attempted_fact_json"]) if d.get("attempted_fact_json") else None
            results.append(
                ExtractionFailure(
                    id=d["id"],
                    document_id=d["document_id"],
                    document_name=d["document_name"],
                    page_number=d["page_number"],
                    failure_type=FailureType(d["failure_type"]),
                    raw_snippet=d["raw_snippet"],
                    explanation=d["explanation"],
                    attempted_fact=attempted,
                    created_at=d["created_at"]
                )
            )
        return results

# Initialize DB on load safely
try:
    init_db()
except Exception as e:
    import logging
    logging.getLogger("factlens.db").warning(f"Database auto-init deferred: {e}")

