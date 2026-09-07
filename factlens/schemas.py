from typing import Optional, List, Dict, Any
from enum import Enum
from pydantic import BaseModel, Field
from datetime import datetime, timezone
import uuid

def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

class RelationshipType(str, Enum):
    CORROBORATION = "corroboration"
    GENUINE_CONTRADICTION = "genuine_contradiction"
    CONTEXTUAL_DIFFERENCE = "contextual_difference"
    UNCERTAIN = "uncertain"

class DifferenceType(str, Enum):
    NONE = "none"
    UNIT = "unit"
    TEMPORAL = "temporal"
    SCOPE = "scope"
    REVISION = "revision"
    DEFINITION = "definition"

class FailureType(str, Enum):
    UNGROUNDED_EVIDENCE = "ungrounded_evidence"
    PARSE_ERROR = "parse_error"
    AMBIGUOUS_SCOPE = "ambiguous_scope"
    TABLE_MISALIGNMENT = "table_misalignment"
    LAYOUT_DISRUPTION = "layout_disruption"

class DocumentMetadata(BaseModel):
    id: str = Field(default_factory=lambda: f"doc_{uuid.uuid4().hex[:12]}")
    filename: str
    original_name: str
    file_size_bytes: int
    page_count: int
    sha256_hash: str
    upload_timestamp: str = Field(default_factory=utc_now_iso)
    status: str = "uploaded"  # uploaded, processing, processed, failed
    error_message: Optional[str] = None

class DocumentPage(BaseModel):
    id: str = Field(default_factory=lambda: f"page_{uuid.uuid4().hex[:12]}")
    document_id: str
    page_number: int  # 1-indexed
    text: str
    char_count: int

class Fact(BaseModel):
    id: str = Field(default_factory=lambda: f"fact_{uuid.uuid4().hex[:12]}")
    document_id: str
    document_name: str
    page_number: int  # 1-indexed
    entity: str
    metric: str
    value_raw: str
    value_numeric: Optional[float] = None
    unit: Optional[str] = None
    period: Optional[str] = None
    period_start: Optional[str] = None
    period_end: Optional[str] = None
    as_of_date: Optional[str] = None
    scope: Optional[str] = None
    evidence_text: str
    evidence_context: Optional[str] = None
    confidence: float = 1.0
    extraction_method: str = "deterministic"  # deterministic | llm
    created_at: str = Field(default_factory=utc_now_iso)

class FactComparison(BaseModel):
    id: str = Field(default_factory=lambda: f"cmp_{uuid.uuid4().hex[:12]}")
    fact_a_id: str
    fact_b_id: str
    fact_a: Fact
    fact_b: Fact
    relationship: RelationshipType
    difference_type: DifferenceType = DifferenceType.NONE
    confidence: float = 1.0
    explanation: str
    created_at: str = Field(default_factory=utc_now_iso)

class ExtractionFailure(BaseModel):
    id: str = Field(default_factory=lambda: f"fail_{uuid.uuid4().hex[:12]}")
    document_id: str
    document_name: str
    page_number: int
    failure_type: FailureType
    raw_snippet: str
    explanation: str
    attempted_fact: Optional[Dict[str, Any]] = None
    created_at: str = Field(default_factory=utc_now_iso)

class ShowcaseCase(BaseModel):
    id: str
    case_category: str  # corroboration, genuine_contradiction, contextual_difference, extraction_failure
    title: str
    dataset: str  # delhivery | india-macroeconomy
    description: str
    facts: List[Fact] = []
    comparison: Optional[FactComparison] = None
    failure: Optional[ExtractionFailure] = None
    why_it_matters: str
