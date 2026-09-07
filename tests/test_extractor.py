from pathlib import Path
import pytest

from factlens.schemas import DocumentPage, FailureType
from factlens.pdf_parser import extract_pdf_pages, verify_evidence_in_page
from factlens.extractor import DeterministicExtractor, fact_extractor


@pytest.fixture
def extractor():
    return DeterministicExtractor()


def test_grounding_verification():
    page_text = "In FY24, Delhivery reported ₹81,415Mn in Revenue from services across India."
    
    # 1. Exact quote
    is_grounded, conf, ctx = verify_evidence_in_page("₹81,415Mn in Revenue from services", page_text)
    assert is_grounded is True
    assert conf >= 0.95
    assert ctx is not None

    # 2. Fabricated quote
    is_grounded, conf, ctx = verify_evidence_in_page("Delhivery made 500 billion USD", page_text)
    assert is_grounded is False
    assert conf == 0.0


def test_card_layout_extraction(extractor):
    sample_text = """
    A year of impactful growth
    740Mn
    Express parcels shipped
    ₹81,415Mn
    Revenue from services
    ₹1,266Mn
    EBITDA
    """
    page = DocumentPage(
        document_id="doc_test",
        page_number=4,
        text=sample_text,
        char_count=len(sample_text)
    )
    facts = extractor.extract_from_card_layout(page, "annual_report.pdf", "Delhivery")
    metrics = {f.metric: f for f in facts}

    assert "Express Parcel Shipments" in metrics
    assert metrics["Express Parcel Shipments"].value_numeric == 740_000_000.0

    assert "Revenue from Services / Operations" in metrics
    assert metrics["Revenue from Services / Operations"].value_numeric == 81_415_000_000.0

    assert "EBITDA" in metrics
    assert metrics["EBITDA"].value_numeric == 1_266_000_000.0


def test_prose_sentence_extraction(extractor):
    sample_text = (
        "As per the first advance estimates of national accounts, India’s real GDP is "
        "estimated to grow by 6.4 per cent in FY25. Retail headline inflation, as measured "
        "by the Consumer Price Index (CPI), has softened from 5.4 per cent in FY24."
    )
    page = DocumentPage(
        document_id="doc_test",
        page_number=1,
        text=sample_text,
        char_count=len(sample_text)
    )
    facts, failures = extractor.extract_from_sentences(page, "survey.pdf", "India")
    metrics = {f.metric: f for f in facts}

    assert "Real GDP Growth" in metrics
    f_gdp = metrics["Real GDP Growth"]
    assert f_gdp.value_numeric == 6.4
    assert f_gdp.unit == "percent"
    assert f_gdp.period == "FY25"
    assert "First Advance Estimates" in (f_gdp.scope or "")

    assert "Headline CPI Inflation" in metrics
    f_cpi = metrics["Headline CPI Inflation"]
    assert f_cpi.value_numeric == 5.4
    assert f_cpi.unit == "percent"
    assert f_cpi.period == "FY24"


def test_delhivery_starter_pdf_extraction():
    pres_path = Path("starter-datasets/delhivery/03-delhivery-q4-fy24-earnings-presentation.pdf")
    if not pres_path.exists():
        pytest.skip("Starter dataset not found")

    pages = extract_pdf_pages(pres_path, "delhivery_pres")
    page_6 = [p for p in pages if p.page_number == 6]
    assert len(page_6) == 1

    facts, failures = fact_extractor.extract_document(page_6, pres_path.name, force_deterministic=True)

    rev_facts = [f for f in facts if f.metric == "Revenue from Services / Operations"]
    assert len(rev_facts) > 0
    assert any(f.value_numeric == 81_420_000_000.0 and "8,142 Cr" in f.value_raw for f in rev_facts)

    vol_facts = [f for f in facts if f.metric == "Express Parcel Shipments"]
    assert len(vol_facts) > 0
    assert any(f.value_numeric == 740_000_000.0 and "740 Mn" in f.value_raw for f in vol_facts)


def test_macro_starter_pdf_extraction():
    survey_path = Path("starter-datasets/india-macroeconomy/01-india-economic-survey-2024-25-excerpt.pdf")
    rbi_path = Path("starter-datasets/india-macroeconomy/02-rbi-annual-report-2024-25-excerpt.pdf")
    if not survey_path.exists() or not rbi_path.exists():
        pytest.skip("Starter dataset not found")

    # 1. Economic survey p.4 -> 6.4% GDP
    pages_survey = extract_pdf_pages(survey_path, "survey")
    p4 = [p for p in pages_survey if p.page_number == 4]
    facts_survey, _ = fact_extractor.extract_document(p4, survey_path.name, force_deterministic=True)
    gdp_facts_survey = [f for f in facts_survey if f.metric == "Real GDP Growth"]
    assert len(gdp_facts_survey) >= 1
    assert any(f.value_numeric == 6.4 and "FY25" in (f.period or "") for f in gdp_facts_survey)

    # 2. RBI report p.9 -> 4.6% inflation, p.24 -> 6.5% GDP
    pages_rbi = extract_pdf_pages(rbi_path, "rbi")
    p9_24 = [p for p in pages_rbi if p.page_number in (9, 24)]
    facts_rbi, _ = fact_extractor.extract_document(p9_24, rbi_path.name, force_deterministic=True)

    cpi_facts = [f for f in facts_rbi if f.metric == "Headline CPI Inflation"]
    assert len(cpi_facts) >= 1
    assert any(f.value_numeric == 4.6 for f in cpi_facts)

    gdp_facts_rbi = [f for f in facts_rbi if f.metric == "Real GDP Growth"]
    assert len(gdp_facts_rbi) >= 1
    assert any(f.value_numeric == 6.5 and "2024-25" in (f.period or "") for f in gdp_facts_rbi)

