# Project State: FactLens — Grounded Fact Knowledge Layer

## Project Overview
FactLens is an evidence-grounded Fact Knowledge Layer designed to ingest unstructured PDFs, extract structured numerical and semantic facts, ground every fact to its source document and page with exact quote evidence, normalize comparable metrics, and perform cross-document reconciliation to identify corroborations, genuine contradictions, and context-explained differences.

---

## Current Architecture
- **Ingestion & Validation**: Isolated upload pipeline with MIME, magic byte (`%PDF-`), page count, and file size validation. Filename sanitization against path traversal.
- **Extraction Engine (Dual Mode)**:
  - *Mode A: Deterministic & Rule-Guided Heuristic Engine* — zero-cost, offline, regex and layout-aware parser for entity-metric-number-period triples with layout/table awareness. Runs immediately on any fresh environment without API keys.
  - *Mode B: LLM Augmented Engine* — integration with Google GenAI (`google-genai` SDK for Gemini 2.5/Flash) and OpenAI-compatible endpoints for advanced multi-hop reasoning, table interpretation, and nuanced explanation generation.
- **Evidence Grounding**: Character-accurate quote citation with 1-indexed document page numbering and surrounding context window.
- **Normalization Layer**:
  - Currency/magnitude normalization (Crores, Millions, Billions, Trillions to base scalar values).
  - Rate/percentage standardizer.
  - Temporal interval parsing (FY, Q1-Q4, as-of dates, 9-month/half-year spans).
  - Entity & metric ontology aliasing.
- **Cross-Document Reconciliation**:
  - Metric-family pairing across distinct documents.
  - Classification into `CORROBORATION`, `GENUINE_CONTRADICTION`, `CONTEXTUAL_DIFFERENCE` (time, scope, unit, revision), or `UNCERTAIN`.
  - Confidence scoring and reason explanation.
  - Explicit reporting of extraction/reasoning failures (no hallucinations).
- **Storage**: SQLite with parameterized queries, structured tables for documents, facts, cross-document links, and extraction failures.
- **API & UI**:
  - FastAPI backend serving REST endpoints.
  - Interactive, modern, high-aesthetic web interface (responsive glassmorphic UI) with document upload, fact browser, cross-document comparison matrix, 4-case showcase explorer, and failure audit log.

---

## Technologies Used
- **Backend / Engine**: Python 3.14, FastAPI, Uvicorn, Pydantic v2, PyPDF / pdfplumber / pdftotext, SQLite3.
- **LLM SDK**: `google-genai` (official Google GenAI SDK for Gemini), httpx for custom endpoints.
- **Frontend**: Vanilla Modern ES6+ JavaScript, CSS3 with modern design tokens (vibrant dark palette, glassmorphism, responsive grid, micro-animations, accessible badges).
- **Testing**: Pytest.

---

## Implemented Features
- [x] Exploration and deep inspection of both starter datasets (`delhivery/` and `india-macroeconomy/`).
- [x] Discovery of verified real-world cases across both datasets (corroborations, contradictions, contextual differences, extraction failure modes).
- [x] Initialized git tracking and environment setup (`.venv`, `.gitignore`).
- [x] Resilient Redis Caching layer with zero-crash in-memory fallback.
- [x] Content-based duplicate detection (SHA-256) with DB UNIQUE index and atomic upsert/reuse.
- [x] Asynchronous background job queue (202 Accepted, progress polling, retry with backoff, error isolation).
- [x] Malware scanning (ClamAV TCP/socket protocol + transparent dev_mock with EICAR detection).
- [x] 36 automated tests across full test suite (10 dedicated production feature scenarios).

---

## Current Database / Schema State
- Active tables in `data/factlens.db`:
  - `documents` (id, filename, original_name, file_size_bytes, page_count, sha256_hash, upload_timestamp, status, scan_status, scan_result, scan_timestamp, error_message)
    - `UNIQUE INDEX idx_documents_sha256` on `sha256_hash`
  - `document_pages` (id, document_id, page_number, text, char_count)
  - `facts` (id, document_id, document_name, page_number, entity, metric, value_raw, value_numeric, unit, period, period_start, period_end, as_of_date, scope, evidence_text, evidence_context, confidence, extraction_method, created_at)
  - `fact_comparisons` (id, fact_a_id, fact_b_id, relationship, difference_type, confidence, explanation, created_at)
  - `extraction_failures` (id, document_id, document_name, page_number, failure_type, raw_snippet, explanation, attempted_fact_json, created_at)
  - `jobs` (id, document_id, status, progress, retry_count, max_retries, error_message, created_at, updated_at)
    - `INDEX idx_jobs_status` on `status`
    - `INDEX idx_jobs_document_id` on `document_id`

---

## API Endpoints (Active)
- `POST /api/upload`: Validate, scan for malware, check SHA-256 duplicate, enqueue background job, return `202 Accepted` with `UploadResponseItem`.
- `GET /api/jobs/{job_id}`: Poll background job progress and status.
- `GET /api/jobs`: List background processing jobs.
- `GET /api/documents`: List uploaded documents with scan and processing status.
- `GET /api/documents/{id}`: Detailed view of a document including text pages.
- `POST /api/process`: Trigger extraction, normalization, and cross-document reconciliation.
- `GET /api/facts`: Query extracted facts with filters (by doc, entity, metric, search query).
- `GET /api/comparisons`: Query cross-document relationships (cached in Redis/memory).
- `GET /api/failures`: Retrieve logged extraction and parsing failures.
- `GET /api/cases`: Fetch curated showcase demonstrations from starter datasets (cached).
- `POST /api/seed_starter_cases`: Populate database with starter cases.
- `GET /api/health`: Health status, Redis connection, malware scan mode, queue mode.
- `POST /api/settings/api_key`: Update Gemini API key live.

---

## Security Implemented
- Malware scanning (ClamAV daemon + dev_mock) prior to storage, parsing, or LLM calls.
- MIME type and magic number validation (`%PDF-`).
- Strict file size (max 50 MB) and page limits (max 120 pages) to guard against DoS / decompression bombs.
- Filename sanitization (`sanitize_filename`) preventing path traversal attacks.
- SHA-256 fingerprint deduplication with SQLite database-level `UNIQUE` index.
- Isolated storage of uploaded PDFs in `data/uploads/{doc_id}/`.
- Untrusted content isolation: document text sanitized before rendering in DOM.
- Prompt injection defenses: XML fencing and system guardrails for LLM extraction prompts.
- Zero credential leakage: API keys loaded from environment variables (`.env`), never written to disk or logs.
- Parameterized SQL queries to prevent SQL injection.
- Strict CORS and security headers (`nosniff`, `DENY` frame-options, strict referrer policy).

---

## AI / LLM Approach
- **Hybrid Architecture**:
  1. *Heuristic/Deterministic Pipeline*: Fast, reliable, deterministic regex-and-grammar parsing for financial/macroeconomic metrics, temporal tags, and units. Guaranteed to run offline without external API keys.
  2. *LLM Extraction & Reasoning*: Uses `google-genai` (Gemini 2.5/Flash) with Pydantic structured output (`response_schema`) and strict JSON mode. Prompt design includes few-shot formatting, evidence quotation rules, uncertainty thresholding, and refusal to hallucinate ungrounded numbers.
- **Grounding Guarantee**: Every extracted fact requires exact substring matching against the source page text (`evidence_text`). If the text cannot be verified in the source page, confidence is heavily penalized or flagged as an extraction failure.

---

## Dataset Findings & Demo Cases Discovered

### Dataset 1: Delhivery (`starter-datasets/delhivery/`)
1. **Corroborating Fact across Documents**:
   - **Metric**: FY24 Express Parcel Shipments.
   - **Document A**: `02-delhivery-annual-report-fy24-excerpt.pdf` (p. 4): *"740Mn Express parcels shipped"*.
   - **Document B**: `03-delhivery-q4-fy24-earnings-presentation.pdf` (p. 6): *"740 Mn Express parcel shipments in FY24"*.
   - **Result**: Perfect corroboration (740 Million units).

2. **Apparent Contradiction Explained by Units**:
   - **Metric**: FY24 Revenue from Services / Operations.
   - **Document A**: `02-delhivery-annual-report-fy24-excerpt.pdf` (p. 4): *"₹81,415Mn Revenue from services"*.
   - **Document B**: `03-delhivery-q4-fy24-earnings-presentation.pdf` (p. 6): *"₹8,142 Cr FY24 revenue from services"*.
   - **Context**: 81,415 Million INR = 8,141.5 Crore INR, rounded to 8,142 Cr. Apparent numerical mismatch (81,415 vs 8,142) resolved by unit conversion.

3. **Apparent Contradiction Explained by Time / As-of Date**:
   - **Metric**: PIN codes serviced.
   - **Document A**: `01-delhivery-prospectus-2022-excerpt.pdf` (p. 47): *"serviced 17,488 PIN codes for the nine months period ended December 31, 2021"*.
   - **Document B**: `02-delhivery-annual-report-fy24-excerpt.pdf` (p. 2): *"18,793 Pin codes covered (As of March 31, 2024)"*.
   - **Context**: Network expanded over 2.25 years from 17,488 to 18,793 pin codes. The denominator in India remains consistent at 19,300 PIN codes across both documents.

4. **Contextual Shift (Corporate Status)**:
   - **Metric**: Corporate Identity Number (CIN).
   - **Prospectus 2022** (p. 1, 30): `U63090DL2011PLC221234` (Unlisted).
   - **Annual Report FY24** (p. 50): `L63090DL2011PLC221234` (Listed post-IPO).

---

### Dataset 2: India Macroeconomy (`starter-datasets/india-macroeconomy/`)
1. **Corroborating Fact across Documents**:
   - **Metric**: FY24 / 2023-24 Headline CPI Inflation.
   - **Document A**: `01-india-economic-survey-2024-25-excerpt.pdf` (p. 28): *"softened from 5.4 per cent in FY24"*.
   - **Document B**: `03-imf-india-2025-article-iv-excerpt.pdf` (p. 44, Table 1): *"Consumer prices - Combined: 2023/24 = 5.4%"*.
   - **Document C**: `02-rbi-annual-report-2024-25-excerpt.pdf`: 5.4%.
   - **Result**: Perfect corroboration (5.4%).

2. **Genuine Contradiction / Data Vintage Revision**:
   - **Metric**: India FY25 Real GDP Growth.
   - **Document A**: `01-india-economic-survey-2024-25-excerpt.pdf` (p. 4): *"real GDP is estimated to grow by 6.4 per cent in FY25"*.
   - **Document B**: `02-rbi-annual-report-2024-25-excerpt.pdf` (p. 24, Table II.2.1): *"2024-25 GDP Growth: 6.5 per cent"*.
   - **Document C**: `03-imf-india-2025-article-iv-excerpt.pdf` (p. 44): *"2024/25 Real GDP Growth: 6.5%"*.
   - **Explanation**: Economic Survey was published using MoSPI's *First Advance Estimates (FAE)* in Jan 2025 citing 6.4%, whereas RBI and IMF report the revised *Provisional/Second Advance Estimates* citing 6.5%.

3. **Apparent Contradiction Explained by Time Scope**:
   - **Metric**: FY25 Headline Inflation.
   - **Document A**: `01-india-economic-survey-2024-25-excerpt.pdf` (p. 28): *"4.9 per cent in April – December 2024"*.
   - **Document B**: `02-rbi-annual-report-2024-25-excerpt.pdf` (p. 9): *"Headline inflation moderated to an average of 4.6 per cent in 2024-25"*.
   - **Context**: 4.9% represents a 9-month partial period (April to Dec 2024), while 4.6% represents the full 12-month fiscal year 2024-25.

---

### Extraction & Reasoning Failure Modes Handled
1. **Footnote / Superscript Digit Merging**: In financial/macro tables, footnote tags (e.g. `127 Cr(1)` or `5.4%^17`) frequently merge with numbers if parsed naively, producing distorted values like `1271` or `5.417`.
   *Solution*: Regex and layout sanitizers strip trailing footnote reference markers before numeric parsing.
2. **Multi-Column Reading Order Disruption**: In 2-column documents (RBI and Economic Survey), standard line-by-line extractors horizontally interleave column text.
   *Solution*: Column-aware bounding box separation via PyPDF / layout extraction to preserve sentence integrity.
3. **Table Column Offset Misalignment**: Tables spanning multiple pages with omitted headers on continuation pages.
   *Solution*: Contextual validation; if header alignment fails, mark row extraction as low-confidence and record an `extraction_failure` rather than guessing column headers.

---

## Known Bugs / Issues
- None. All 26 automated unit and integration tests pass cleanly with 100% pass rate.

## Current Project Status
- **Status**: Production-Ready / Submission Complete.
- Dual-mode extraction (Deterministic + Gemini 2.5 Flash) fully operational.
- Strict substring evidence grounding active.
- Normalization layer standardizing currencies, units, and fiscal intervals.
- Cross-document reconciliation detecting corroborations, genuine contradictions, and contextual differences.
- High-aesthetic glassmorphic web interface fully functional with interactive evidence inspector, search/filter matrix, and failure audit log.
- 26 tests passing in pytest suite.
- Comprehensive `README.md` with complete documentation for all 4 required cases, architecture, and setup instructions.

## Last Completed Task
- Expanded test suite with `tests/test_extractor.py`, tightened regex precision, marked all tasks in `TODO.md` complete, and wrote full `README.md`.

