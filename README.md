# FactLens

**A grounded fact extraction, canonical normalization, and cross-document reconciliation engine for unstructured financial and macroeconomic filings.**

---

## Overview

Enterprise filings, investor presentations, and macroeconomic reports frequently present facts using disparate conventions:
- Different magnitudes and currencies (e.g., Millions vs. Crores, USD vs. INR)
- Shifting temporal horizons (e.g., 9-month interim vs. full 12-month fiscal periods)
- Vintage statistical revisions (e.g., Advance Estimates vs. Provisional Actuals)

Naively comparing these statements creates false contradictions and hallucinated discrepancies.

**FactLens** solves this by providing a structured knowledge pipeline:
1. **Multi-Page Ingestion**: Extracts digital text, layout geometries, and table contents from PDF filings.
2. **Dual-Mode Extraction Engine**: Operates fully offline using deterministic layout-aware rules, or with Google Gemini (`gemini-2.5-flash`) when an API key is configured.
3. **Strict Evidence Grounding**: Every extracted fact is anchored to exact page numbers and verbatim source quotes, verified through multi-tier substring validation.
4. **Canonical Normalization**: Standardizes non-standard currencies, Indian and Western scale units (Crores, Lakhs, Millions, Billions), and fiscal time periods into comparable ISO interval bounds.
5. **Cross-Document Reconciliation**: Evaluates metric pairs across documents to classify relationships as **Corroborations**, **Genuine Contradictions**, or **Contextual Differences** (Unit, Time, Scope, Definition, or Revision).
6. **Failure & Audit Logging**: Ungrounded or ambiguous assertions are captured in an audit trail rather than silently dropped or hallucinated.

---

## Architecture

```
                       ┌────────────────────────┐
                       │   PDF Document Upload  │
                       │   (Multi-file upload)  │
                       └───────────┬────────────┘
                                   │
                                   ▼
                     ┌───────────────────────────┐
                     │ Security & Input Defense  │
                     │ - Magic byte check (%PDF-)│
                     │ - Size & page count limit │
                     │ - Malware / ClamAV filter │
                     └─────────────┬─────────────┘
                                   │
                                   ▼
                     ┌───────────────────────────┐
                     │    PDF Document Parser    │
                     │ - Layout-aware extraction │
                     │ - Page & coordinate maps  │
                     │ - Table boundary parsing  │
                     └─────────────┬─────────────┘
                                   │
                                   ▼
            ┌─────────────────────────────────────────────┐
            │          Dual-Mode Extraction Engine        │
            │                                             │
            │  [Deterministic Rule Engine]                │
            │  - Layout-aware regex & table parsing       │
            │  - Fully offline, zero external calls       │
            │                                             │
            │  [LLM-Augmented Engine (Optional)]          │
            │  - Google Gemini 2.5 Flash                  │
            │  - Pydantic structured output schema        │
            └──────────────────────┬──────────────────────┘
                                   │
                                   ▼
                     ┌───────────────────────────┐
                     │    Evidence Grounding     │
                     │ - Verbatim substring match│
                     │ - Context snippet window  │
                     │ - Multi-tier verification │
                     └─────────────┬─────────────┘
                                   │
                                   ▼
                     ┌───────────────────────────┐
                     │    Normalization Layer    │
                     │ - Scalar unit conversion  │
                     │ - ISO temporal intervals  │
                     │ - Canonical metric aliases│
                     └─────────────┬─────────────┘
                                   │
                                   ▼
                     ┌───────────────────────────┐
                     │ Cross-Document Reconciler │
                     │ - Corroboration detection │
                     │ - Genuine contradictions  │
                     │ - Contextual differences  │
                     └─────────────┬─────────────┘
                                   │
                                   ▼
       ┌───────────────────────────────────────────────────────┐
       │                  Storage & Interface                  │
       │  - SQLite Database (WAL mode, parameterized queries)  │
       │  - Optional Redis Cache (In-memory TTL fallback)      │
       │  - FastAPI REST Backend                               │
       │  - Interactive Web Dashboard (Vanilla HTML/CSS/JS)    │
       └───────────────────────────────────────────────────────┘
```

---

## Core Capabilities

### 1. Evidence Grounding & Verification
Every fact must be strictly grounded in the source text:
- **Exact Quote Matching**: Verifies the extracted `evidence_text` directly against the raw text of the specified page.
- **Multi-Tier Fallback**: Performs verbatim substring matching, normalized whitespace matching, and token overlap analysis.
- **Audit Logging**: Any claim that cannot be verified on the page is flagged as an `UNGROUNDED_EVIDENCE` failure in the audit log.

### 2. Canonical Normalization
- **Currency & Scale Units**: Normalizes Indian numbering systems (`Crore`, `Lakh`) and Western notations (`Million`, `Billion`) to base numeric values:
  - `₹81,415 Mn` $\rightarrow$ `81,415,000,000 INR`
  - `₹8,142 Cr` $\rightarrow$ `81,420,000,000 INR`
- **Temporal Alignment**: Translates fiscal periods and relative dates into ISO 8601 date intervals:
  - `FY24` $\rightarrow$ `[2023-04-01, 2024-03-31]`
  - `9M ended Dec 31, 2021` $\rightarrow$ `[2021-04-01, 2021-12-31]`
  - `As of March 31, 2024` $\rightarrow$ `[2024-03-31, 2024-03-31]`
- **Metric Aliasing**: Maps lexical variants to canonical ontology keys (e.g., `Revenue from operations` and `Revenue from services` map to `revenue`).

### 3. Cross-Document Reconciliation
When facts share the same canonical entity and metric, FactLens determines their relationship:

| Classification | Condition | Example |
| :--- | :--- | :--- |
| **CORROBORATION** | Equivalent normalized values over the same temporal period across separate documents. | Parcel volume reported as `740 Mn` in Annual Report and `740 Mn` in Earnings Deck. |
| **CONTEXTUAL_DIFFERENCE (Unit)** | Discrepancies resolved once units are converted to common base scales. | `₹81,415 Mn` vs. `₹8,142 Cr` (0.006% rounding equivalence). |
| **CONTEXTUAL_DIFFERENCE (Temporal)** | Discrepancies resulting from non-overlapping or expanded measurement periods. | Network reach at `17,488 PIN codes` (Dec 2021) vs. `18,793 PIN codes` (Mar 2024). |
| **CONTEXTUAL_DIFFERENCE (Scope)** | Discrepancies explained by partial vs. full reporting intervals. | Headline inflation at `4.9%` (9-month interim) vs. `4.6%` (full 12-month fiscal year). |
| **GENUINE_CONTRADICTION** | Conflicting figures for identical metrics and time horizons without scope justification. | India FY25 Real GDP Growth reported as `6.4%` (First Advance Estimates) vs. `6.5%` (Provisional Actuals / RBI). |

---

## Production Features

- **Asynchronous Background Processing**: File uploads are accepted immediately (`202 Accepted`), with parsing, extraction, and reconciliation executing in decoupled background workers with progress tracking and automatic retry logic.
- **Content-Based Deduplication**: Uploaded documents are fingerprinted via SHA-256 hashes. Duplicate files (even with different filenames) reuse existing processing artifacts immediately.
- **Resilient Caching**: Redis-backed cache layer for document facts and reconciliation results, with an automatic, zero-crash fallback to in-memory TTL caching when Redis is unavailable.
- **Security & Payload Defense**:
  - Magic byte validation (`%PDF-`) and MIME verification
  - Configurable page count and file size limits
  - Path traversal sanitization
  - ClamAV antivirus stream scanning with safe fail-closed behavior and development mock modes
  - Prompt injection boundary isolation for LLM payloads

---

## Getting Started

### Prerequisites
- Python 3.10 to 3.14
- Git

### Installation

```bash
# 1. Clone repository
git clone https://github.com/irohansh/factlens.git
cd factlens

# 2. Set up virtual environment
python3 -m venv .venv
source .venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt
```

### Configuration

FactLens runs out of the box in **Offline Deterministic Mode** with zero configuration.

To enable optional LLM-assisted extraction or configure cache and scanner settings, copy the example environment file:

```bash
cp .env.example .env
```

Key environment variables in `.env`:

```ini
# Optional: Google Gemini API Key for LLM extraction
GEMINI_API_KEY=your_gemini_api_key_here

# Cache configuration (redis or memory)
CACHE_BACKEND=memory
REDIS_URL=redis://localhost:6379/0

# Malware scanner mode (dev_mock, clamav, or disabled)
SCANNER_MODE=dev_mock
CLAMAV_HOST=localhost
CLAMAV_PORT=3310
```

### Running the Server

```bash
# Start FastAPI application with live reload
uvicorn factlens.api:app --reload --host 127.0.0.1 --port 8000
```

Access the interfaces:
- **Web Dashboard**: [http://localhost:8000](http://localhost:8000)
- **Interactive OpenAPI Documentation**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **Health Endpoint**: [http://localhost:8000/api/health](http://localhost:8000/api/health)

---

## API Reference

### Ingestion & Processing

#### `POST /api/upload`
Upload one or more PDF files for validation, deduplication, and queued processing.
```bash
curl -X POST "http://localhost:8000/api/upload" \
  -F "files=@data/samples/delhivery/02-delhivery-annual-report-fy24-excerpt.pdf"
```

#### `GET /api/jobs/{job_id}`
Check background processing progress and worker status.
```bash
curl "http://localhost:8000/api/jobs/job_123456"
```

#### `POST /api/process`
Trigger synchronous extraction and reconciliation on ingested documents.
```bash
curl -X POST "http://localhost:8000/api/process"
```

### Data & Query Endpoints

#### `GET /api/facts`
Query extracted and grounded facts with optional filters.
```bash
# Filter by entity or metric
curl "http://localhost:8000/api/facts?entity=Delhivery&metric=revenue"
```

#### `GET /api/comparisons`
Retrieve cross-document reconciliation pairs.
```bash
# Filter by reconciliation classification
curl "http://localhost:8000/api/comparisons?relationship=GENUINE_CONTRADICTION"
```

#### `GET /api/failures`
Inspect ungrounded claims or parsing errors in the audit log.
```bash
curl "http://localhost:8000/api/failures"
```

#### `GET /api/cases`
Retrieve reference reconciliation case studies across standard test datasets.
```bash
curl "http://localhost:8000/api/cases"
```

---

## Reference Reconciliation Scenarios

The repository includes pre-packaged test documents illustrating common cross-filing patterns:

### 1. Volume Corroboration Across Filings
- **Metric**: FY24 Express Parcel Volume
- **Filings**: Delhivery FY24 Annual Report (Page 4) vs. Q4 FY24 Earnings Presentation (Page 6)
- **Values**: `"740Mn Express parcels shipped"` vs. `"740 Mn Express parcel shipments in FY24"`
- **Result**: `CORROBORATION` (normalized: `740,000,000` parcels)

### 2. Unit-Explained Difference
- **Metric**: FY24 Revenue from Services
- **Filings**: Delhivery FY24 Annual Report (Page 4) vs. Q4 FY24 Earnings Presentation (Page 6)
- **Values**: `₹81,415 Mn` vs. `₹8,142 Cr`
- **Result**: `CONTEXTUAL_DIFFERENCE (Unit)` (both normalize to ₹81.42B within standard rounding tolerance)

### 3. Temporal Network Expansion
- **Metric**: PIN Codes Covered
- **Filings**: Delhivery 2022 Prospectus (Page 47) vs. FY24 Annual Report (Page 2)
- **Values**: `17,488 PIN codes` (Dec 31, 2021) vs. `18,793 PIN codes` (Mar 31, 2024)
- **Result**: `CONTEXTUAL_DIFFERENCE (Temporal)` (2.25-year network expansion)

### 4. Macroeconomic Statistical Revision
- **Metric**: India FY25 Real GDP Growth Rate
- **Filings**: India Economic Survey 2024-25 (Page 4) vs. RBI Annual Report 2024-25 (Page 24)
- **Values**: `6.4%` vs. `6.5%`
- **Result**: `GENUINE_CONTRADICTION (Revision)` (reflects First Advance Estimates vs. Provisional Actuals)

---

## Testing

FactLens includes an automated test suite verifying security checks, extraction accuracy, unit conversions, temporal intervals, reconciliation logic, and production resilience features.

```bash
# Run full test suite
pytest -v

# Run production feature tests (caching, deduplication, job queue, scanner)
pytest tests/test_production_features.py -v
```

---

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE) for details.
