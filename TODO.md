# FactLens: Prioritized Task List (TODO)

## Phase 1: Environment & Foundational Architecture
- [x] Inspect starter datasets (`delhivery/`, `india-macroeconomy/`) and assignment requirements
- [x] Identify verified test cases across both datasets (corroborations, contradictions, contextual nuances, failures)
- [x] Initialize Git repository, configure `.gitignore`
- [x] Create `PROJECT_STATE.md`, `TODO.md`, `DECISIONS.md`
- [x] Install core backend dependencies (`fastapi`, `uvicorn`, `pydantic`, `pypdf`, `pdfplumber`, `google-genai`, `pytest`, `fonttools`) in `.venv`
- [x] Create `.env.example` and configuration manager

## Phase 2: Core Data Models & Security Validation
- [x] Implement Pydantic data schemas:
  - Document models (`DocumentMetadata`, `DocumentPage`)
  - Fact models (`Fact`, `FactEntity`, `FactMetric`, `EvidenceSpan`, `TemporalScope`)
  - Cross-document relationship models (`FactComparison`, `RelationshipType`, `DifferenceExplanation`)
  - Failure audit models (`ExtractionFailure`, `FailureType`)
- [x] Implement Security Module:
  - MIME type and magic-bytes validator (`%PDF-`)
  - File size (50MB) and page limit (120 pages) enforcement
  - Filename sanitizer (`secure_filename`)
  - Safe storage abstraction under `data/uploads/`
  - Untrusted text sanitizer

## Phase 3: Text & Fact Extraction Engines
- [x] Implement high-fidelity PDF extraction engine:
  - Multi-column layout awareness
  - Page-by-page text chunking with exact character offsets
  - Table parsing support
- [x] Implement Normalization Layer:
  - Currency & numerical magnitude standardizer (Cr, Mn, Bn, Lakh, %, units)
  - Date & fiscal period interval normalizer (FY24, Q1-Q4, as-of dates, 9-month ranges)
  - Entity & metric alias mapper
- [x] Implement Dual-Mode Fact Extraction:
  - Mode A: Deterministic heuristic & regex fact extractor (runs completely offline without API key)
  - Mode B: LLM structured extractor using `google-genai` / Gemini 2.5 with structured output schema
- [x] Implement Grounding Verification:
  - Strict substring evidence verification against source PDF text
  - Failure logger: record `ExtractionFailure` when parsing fails or confidence is below threshold

## Phase 4: Cross-Document Reconciliation Engine
- [x] Implement Fact Comparison Pipeline:
  - Group facts across distinct documents by normalized entity and metric family
  - Compare values taking into account normalized units, temporal periods, and scopes
  - Classify relationship: `CORROBORATION`, `GENUINE_CONTRADICTION`, `CONTEXTUAL_DIFFERENCE`, `UNCERTAIN`
  - Generate precise human-readable explanation of the relationship
  - Provide confidence score and difference breakdown (Time, Scope, Unit, Revision)
- [x] Seed showcase cases for instant verification of the 4 required cases from Delhivery & India Macro datasets

## Phase 5: Storage & Database Layer
- [x] Implement SQLite repository layer:
  - Parameterized queries / ORM
  - Tables: `documents`, `pages`, `facts`, `comparisons`, `failures`
  - Automatic database schema initialization and migrations

## Phase 6: API Layer (FastAPI)
- [x] Build REST endpoints:
  - `POST /api/upload`: multi-file secure upload
  - `GET /api/documents`: document list & processing state
  - `GET /api/documents/{id}`: document pages & details
  - `POST /api/process`: trigger extraction and cross-document reconciliation
  - `GET /api/facts`: filterable fact queries
  - `GET /api/comparisons`: cross-document relationships & explanations
  - `GET /api/failures`: extraction & reasoning failures
  - `GET /api/cases`: showcase demo cases
  - `GET /api/health`: system health & LLM status
- [x] Add CORS middleware, security headers, and rate limiting

## Phase 7: Modern Interactive UI
- [x] Build high-aesthetic frontend (dark mode, glassmorphism, responsive):
  - Document Uploader with drag-and-drop & progress bar
  - Fact Knowledge Matrix & Search/Filter
  - Cross-Document Comparison Cards with color-coded badges
  - Interactive Evidence Inspector (side-by-side snippet view with exact document & page links)
  - Showcase Case Explorer (one-click access to the 4 required cases)
  - Extraction Failure & Audit Log Viewer
  - Settings Modal for API Key / Engine toggling

## Phase 8: Testing, Verification & Documentation
- [x] Write unit & integration tests (`pytest`):
  - File validation & security tests
  - Normalization engine tests (units, currencies, periods)
  - Extraction & grounding tests
  - Reconciliation & classification tests
  - API endpoint tests
- [x] Complete `README.md` according to assignment guidelines
- [x] Update `PROJECT_STATE.md`, `TODO.md`, `DECISIONS.md`

## Phase 9: Production-Oriented Enhancements
- [x] Redis Caching Layer:
  - Cache document facts, extraction results, comparisons, and frequent API responses
  - Structured key namespacing with content versioning
  - Safe zero-crash in-memory fallback when Redis is unreachable
- [x] Content-Based Duplicate PDF Detection:
  - SHA-256 fingerprinting across filenames
  - Database-level `UNIQUE INDEX idx_documents_sha256`
  - Atomic insertion (`create_document_atomic`) preventing race conditions
  - Immediate reuse of existing extractions without duplicate worker tasks
- [x] Background Processing / Job Queue:
  - Decoupled `202 Accepted` upload flow with `job_id`
  - Lifecycle state tracking: `queued`, `processing`, `completed`, `failed`
  - Exponential backoff retries and worker error isolation
  - Polling endpoint `GET /api/jobs/{job_id}` with progress tracking
- [x] Malware Scanning & Antivirus Integration:
  - Integration with ClamAV daemon (`clamd` TCP/socket)
  - Fail-closed security posture (HTTP 503 on scanner outage)
  - Transparent `dev_mock` mode catching EICAR test signatures with clear log warnings
- [x] Production Test Suite:
  - 10 automated test scenarios in `tests/test_production_features.py` (all 36 tests passing)

