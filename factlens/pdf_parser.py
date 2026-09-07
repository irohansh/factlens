import re
from pathlib import Path
from typing import List, Tuple, Optional
import pypdf

from factlens.schemas import DocumentPage
from factlens.config import settings
from factlens.security import SecurityError

def extract_pdf_pages(pdf_path: Path, document_id: str) -> List[DocumentPage]:
    """
    Extracts pages and text from a PDF file using pypdf.
    Enforces page count limits for security.
    """
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF file not found: {pdf_path}")
        
    try:
        reader = pypdf.PdfReader(str(pdf_path))
        page_count = len(reader.pages)
        
        if page_count > settings.MAX_PAGE_COUNT:
            raise SecurityError(
                f"Page count ({page_count}) exceeds maximum allowed limit ({settings.MAX_PAGE_COUNT} pages)."
            )
            
        pages: List[DocumentPage] = []
        for idx, page in enumerate(reader.pages):
            page_num = idx + 1
            raw_text = page.extract_text() or ""
            # Clean surrogate characters or null bytes if present
            cleaned_text = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]', '', raw_text)
            
            pages.append(
                DocumentPage(
                    document_id=document_id,
                    page_number=page_num,
                    text=cleaned_text,
                    char_count=len(cleaned_text)
                )
            )
        return pages
    except Exception as e:
        if isinstance(e, SecurityError):
            raise
        raise RuntimeError(f"Failed to extract PDF pages from {pdf_path}: {e}")

def normalize_whitespace(text: str) -> str:
    """Collapses multiple spaces, tabs, and newlines into single spaces for robust matching."""
    return re.sub(r'\s+', ' ', text).strip()

def verify_evidence_in_page(evidence_quote: str, page_text: str) -> Tuple[bool, float, Optional[str]]:
    """
    Verifies that the evidence quote is grounded in the page text.
    Returns:
        (is_grounded, confidence_score, matched_context)
    """
    if not evidence_quote or not page_text:
        return False, 0.0, None
        
    # 1. Exact verbatim match
    if evidence_quote in page_text:
        idx = page_text.index(evidence_quote)
        start = max(0, idx - 120)
        end = min(len(page_text), idx + len(evidence_quote) + 120)
        context = page_text[start:end].strip()
        return True, 1.0, context

    # 2. Normalized whitespace match
    norm_page = normalize_whitespace(page_text)
    norm_quote = normalize_whitespace(evidence_quote)
    if norm_quote in norm_page:
        idx = norm_page.index(norm_quote)
        start = max(0, idx - 120)
        end = min(len(norm_page), idx + len(norm_quote) + 120)
        context = norm_page[start:end].strip()
        return True, 0.95, context

    # 3. Flexible quote match (ignoring currency symbols, footnote markers, and punctuation differences)
    stripped_quote = re.sub(r'[^\w\s]', '', norm_quote)
    stripped_page = re.sub(r'[^\w\s]', '', norm_page)
    if len(stripped_quote) > 15 and stripped_quote in stripped_page:
        return True, 0.85, norm_quote

    # 4. Token overlap ratio for longer quotes (> 6 tokens)
    quote_tokens = set(re.findall(r'\b\w+\b', norm_quote.lower()))
    if len(quote_tokens) >= 5:
        page_tokens = set(re.findall(r'\b\w+\b', norm_page.lower()))
        intersection = quote_tokens.intersection(page_tokens)
        overlap = len(intersection) / len(quote_tokens)
        if overlap >= 0.85:
            return True, 0.75, norm_quote

    return False, 0.0, None
