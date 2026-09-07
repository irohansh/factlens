# Architectural & Design Decisions (DECISIONS.md)

### ADR 001: Dual-Mode Extraction (Deterministic Heuristic Engine + LLM Engine)
- **Decision**: Provide two interchangeable extraction modes:
  1. An offline, deterministic rule-and-regex engine with financial/macroeconomic metric patterns, unit standardizers, and multi-column parsing.
  2. An LLM-powered engine using `google-genai` (Gemini 2.5 Flash) with Pydantic structured output.
- **Why**: Evaluators may run the repository locally without an API key or paid service. The system must run immediately out-of-the-box, process PDFs, extract facts, normalize units, and perform cross-document comparisons without failing or demanding credits. When an API key is supplied, LLM mode activates automatically.
- **Alternatives Considered**: LLM-only (would fail for anyone without API credentials); pure keyword search (too brittle for semantic nuance).

### ADR 002: Evidence Grounding via Strict Substring Verification
- **Decision**: Every extracted fact MUST store an exact `evidence_text` quote and page number. During ingestion, the system validates that `evidence_text` actually exists on that page in the PDF.
- **Why**: Eliminates hallucinations and fabrication. If an extractor proposes a fact whose evidence is absent from the page, it is rejected and logged as an `ExtractionFailure`.
- **Alternatives Considered**: Storing only page summaries or LLM paraphrase (lacks verifiable audit trail).

### ADR 003: Multi-Column Aware PDF Extraction
- **Decision**: Use bounding box / coordinate-sorted text extraction (or column-aware flow) rather than naive line-by-line dumps.
- **Why**: Institutional reports like the RBI Annual Report and Economic Survey use 2-column layouts. Standard naive text extractors horizontally merge columns into illegible sentences.
- **Alternatives Considered**: Raw `pdftotext` without layout flags, OCR (too slow and unnecessary for digital PDFs).

### ADR 004: Unit & Temporal Normalization Pipeline
- **Decision**: Standardize all numerical values into a canonical base number (e.g. INR base value, USD base value, fractional percentages) and map temporal periods to ISO interval objects (`period_start`, `period_end`, `as_of_date`).
- **Why**: Allows cross-document reconciliation between documents using Crores vs Millions (e.g., Delhivery ₹81,415 Mn vs ₹8,142 Cr) and prevents false contradictions caused by differing reporting periods (e.g., 9-month FY25 vs 12-month FY25).
- **Alternatives Considered**: Relying solely on LLM prompt instructions to compare (unreliable with numerical rounding and magnitude conversions).

### ADR 005: SQLite with Parameterized Storage
- **Decision**: Use SQLite with parameterized queries for document, fact, and comparison persistence.
- **Why**: Zero external infrastructure setup required (no Docker container or Postgres daemon needed for local evaluation). Fast, portable, single-file database.
- **Alternatives Considered**: Neo4j / Graph DB (as noted in assignment: "A graph database or visualization alone is not the solution"), Postgres (requires external database server).

### ADR 006: Security Architecture & Untrusted PDF Input Model
- **Decision**: Treat all PDF uploads as untrusted input. Enforce magic byte check (`%PDF-`), MIME check, 50MB file limit, 120 page limit, path traversal sanitization, and output DOM sanitization.
- **Why**: PDF files are notorious attack vectors (decompression bombs, malformed xref tables, prompt injection payloads).
- **Alternatives Considered**: Permissive uploads (vulnerable to resource exhaustion).
