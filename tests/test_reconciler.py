import pytest
from factlens.schemas import Fact, RelationshipType, DifferenceType
from factlens.reconciler import cross_doc_reconciler

def test_reconcile_corroboration():
    f1 = Fact(
        id="f1",
        document_id="doc1",
        document_name="Doc1.pdf",
        page_number=4,
        entity="Delhivery",
        metric="Express Parcel Shipments",
        value_raw="740Mn",
        value_numeric=740000000.0,
        unit="count",
        period="FY24",
        evidence_text="740Mn Express parcels shipped"
    )
    f2 = Fact(
        id="f2",
        document_id="doc2",
        document_name="Doc2.pdf",
        page_number=6,
        entity="Delhivery",
        metric="Express Parcel Shipments",
        value_raw="740 Mn",
        value_numeric=740000000.0,
        unit="count",
        period="FY24",
        evidence_text="740 Mn Express parcel shipments in FY24"
    )
    cmp = cross_doc_reconciler.compare_fact_pair(f1, f2)
    assert cmp is not None
    assert cmp.relationship == RelationshipType.CORROBORATION
    assert cmp.difference_type == DifferenceType.NONE
    assert "corroborat" in cmp.explanation.lower()

def test_reconcile_unit_contextual_difference():
    # 81,415 Mn vs 8,142 Cr
    f1 = Fact(
        id="f1",
        document_id="doc1",
        document_name="AnnualReport.pdf",
        page_number=4,
        entity="Delhivery",
        metric="Revenue from Services / Operations",
        value_raw="₹81,415Mn",
        value_numeric=81415000000.0,
        unit="INR",
        period="FY24",
        evidence_text="₹81,415Mn Revenue from services"
    )
    f2 = Fact(
        id="f2",
        document_id="doc2",
        document_name="Presentation.pdf",
        page_number=6,
        entity="Delhivery",
        metric="Revenue from Services / Operations",
        value_raw="₹8,142 Cr",
        value_numeric=81420000000.0,
        unit="INR",
        period="FY24",
        evidence_text="₹8,142 Cr FY24 revenue from services"
    )
    cmp = cross_doc_reconciler.compare_fact_pair(f1, f2)
    assert cmp is not None
    assert cmp.relationship == RelationshipType.CONTEXTUAL_DIFFERENCE
    assert cmp.difference_type == DifferenceType.UNIT
    assert "unit" in cmp.explanation.lower()

def test_reconcile_temporal_contextual_difference():
    # Pin codes 17,488 in 2021 vs 18,793 in 2024
    f1 = Fact(
        id="f1",
        document_id="doc1",
        document_name="Prospectus2022.pdf",
        page_number=47,
        entity="Delhivery",
        metric="PIN Codes Covered",
        value_raw="17,488",
        value_numeric=17488.0,
        unit="count",
        period="As of December 31, 2021",
        as_of_date="2021-12-31",
        evidence_text="serviced 17,488 PIN codes for the nine months period ended December 31, 2021"
    )
    f2 = Fact(
        id="f2",
        document_id="doc2",
        document_name="AnnualReport2024.pdf",
        page_number=2,
        entity="Delhivery",
        metric="PIN Codes Covered",
        value_raw="18,793",
        value_numeric=18793.0,
        unit="count",
        period="As of March 31, 2024",
        as_of_date="2024-03-31",
        evidence_text="18,793 Pin codes covered As of March 31, 2024"
    )
    cmp = cross_doc_reconciler.compare_fact_pair(f1, f2)
    assert cmp is not None
    assert cmp.relationship == RelationshipType.CONTEXTUAL_DIFFERENCE
    assert cmp.difference_type == DifferenceType.TEMPORAL
    assert "time horizon" in cmp.explanation.lower() or "temporal" in cmp.explanation.lower()

def test_reconcile_revision_genuine_contradiction():
    # FY25 GDP Growth 6.4% FAE vs 6.5% NSO/RBI
    f1 = Fact(
        id="f1",
        document_id="doc1",
        document_name="EconomicSurvey.pdf",
        page_number=4,
        entity="India",
        metric="Real GDP Growth",
        value_raw="6.4 per cent",
        value_numeric=6.4,
        unit="percent",
        period="FY25",
        period_start="2024-04-01",
        period_end="2025-03-31",
        scope="First Advance Estimates (FAE)",
        evidence_text="real GDP is estimated to grow by 6.4 per cent in FY25"
    )
    f2 = Fact(
        id="f2",
        document_id="doc2",
        document_name="RBIAnnualReport.pdf",
        page_number=24,
        entity="India",
        metric="Real GDP Growth",
        value_raw="6.5 per cent",
        value_numeric=6.5,
        unit="percent",
        period="FY25",
        period_start="2024-04-01",
        period_end="2025-03-31",
        scope="Provisional Estimates",
        evidence_text="Table II.2.1: Real GDP Growth ... 2024-25: 6.5 per cent"
    )
    cmp = cross_doc_reconciler.compare_fact_pair(f1, f2)
    assert cmp is not None
    assert cmp.relationship == RelationshipType.GENUINE_CONTRADICTION
    assert cmp.difference_type == DifferenceType.REVISION
    assert "revision" in cmp.explanation.lower() or "advance estimates" in cmp.explanation.lower()
