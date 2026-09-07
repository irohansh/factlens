from typing import List
from factlens.schemas import ShowcaseCase, Fact, FactComparison, ExtractionFailure, RelationshipType, DifferenceType, FailureType

def get_starter_showcase_cases() -> List[ShowcaseCase]:
    """
    Returns curated showcase cases from BOTH starter datasets:
      1. Corroborating facts
      2. Genuine contradictions / revisions
      3. Apparent contradictions explained by time/units/scope
      4. Real extraction / reasoning failures
    """
    cases: List[ShowcaseCase] = []

    # =========================================================================
    # CASE 1 (Delhivery): Corroborating Fact Expressed Across Documents
    # =========================================================================
    fact_delhivery_vol_ar = Fact(
        id="case_delhivery_vol_ar",
        document_id="doc_delhivery_ar_fy24",
        document_name="02-delhivery-annual-report-fy24-excerpt.pdf",
        page_number=4,
        entity="Delhivery",
        metric="Express Parcel Shipments",
        value_raw="740Mn",
        value_numeric=740000000.0,
        unit="count",
        period="FY24",
        period_start="2023-04-01",
        period_end="2024-03-31",
        scope="Consolidated",
        evidence_text="740Mn\nExpress parcels shipped",
        evidence_context="Corporate Overview > A year of impactful growth: 740Mn Express parcels shipped, ₹81,415Mn Revenue from services, ₹1,266Mn EBITDA",
        confidence=1.0,
        extraction_method="deterministic"
    )

    fact_delhivery_vol_pres = Fact(
        id="case_delhivery_vol_pres",
        document_id="doc_delhivery_pres_fy24",
        document_name="03-delhivery-q4-fy24-earnings-presentation.pdf",
        page_number=6,
        entity="Delhivery",
        metric="Express Parcel Shipments",
        value_raw="740 Mn",
        value_numeric=740000000.0,
        unit="count",
        period="FY24",
        period_start="2023-04-01",
        period_end="2024-03-31",
        scope="Consolidated",
        evidence_text="740 Mn\nExpress parcel shipments in FY24\nYoY: 11.5%",
        evidence_context="Slide 5 > India's largest integrated logistics platform: 740 Mn Express parcel shipments in FY24 YoY: 11.5%",
        confidence=1.0,
        extraction_method="deterministic"
    )

    cmp_delhivery_vol = FactComparison(
        id="cmp_delhivery_vol",
        fact_a_id=fact_delhivery_vol_ar.id,
        fact_b_id=fact_delhivery_vol_pres.id,
        fact_a=fact_delhivery_vol_ar,
        fact_b=fact_delhivery_vol_pres,
        relationship=RelationshipType.CORROBORATION,
        difference_type=DifferenceType.NONE,
        confidence=1.0,
        explanation=(
            "Both documents independently corroborate that Delhivery delivered 740 Million express parcels in FY24. "
            "Annual Report p.4 states '740Mn Express parcels shipped' while Q4 FY24 Earnings Presentation p.6 states "
            "'740 Mn Express parcel shipments in FY24'."
        )
    )

    cases.append(
        ShowcaseCase(
            id="delhivery_corroboration_volume",
            case_category="corroboration",
            title="Corroboration: FY24 Express Parcel Shipments (740 Mn)",
            dataset="delhivery",
            description="Independent corroboration of total express parcel shipments for FY24 across statutory annual report and investor presentation.",
            facts=[fact_delhivery_vol_ar, fact_delhivery_vol_pres],
            comparison=cmp_delhivery_vol,
            why_it_matters="Verifies operational volume consistency across formal statutory disclosures and investor presentations."
        )
    )

    # =========================================================================
    # CASE 2 (Delhivery): Apparent Contradiction Reconciled by Units (Millions vs Crores)
    # =========================================================================
    fact_delhivery_rev_ar = Fact(
        id="case_delhivery_rev_ar",
        document_id="doc_delhivery_ar_fy24",
        document_name="02-delhivery-annual-report-fy24-excerpt.pdf",
        page_number=4,
        entity="Delhivery",
        metric="Revenue from Services / Operations",
        value_raw="₹81,415Mn",
        value_numeric=81415000000.0,
        unit="INR",
        period="FY24",
        period_start="2023-04-01",
        period_end="2024-03-31",
        scope="Consolidated Services",
        evidence_text="₹81,415Mn\nRevenue from services",
        evidence_context="Corporate Overview p.4: ₹81,415Mn Revenue from services, ₹1,266Mn EBITDA, 1.6% EBITDA margin",
        confidence=1.0,
        extraction_method="deterministic"
    )

    fact_delhivery_rev_pres = Fact(
        id="case_delhivery_rev_pres",
        document_id="doc_delhivery_pres_fy24",
        document_name="03-delhivery-q4-fy24-earnings-presentation.pdf",
        page_number=6,
        entity="Delhivery",
        metric="Revenue from Services / Operations",
        value_raw="₹8,142 Cr",
        value_numeric=81420000000.0,
        unit="INR",
        period="FY24",
        period_start="2023-04-01",
        period_end="2024-03-31",
        scope="Consolidated Services",
        evidence_text="₹8,142 Cr\nFY24 revenue from services",
        evidence_context="Slide 5: ₹8,142 Cr FY24 revenue from services YoY: 12.7%",
        confidence=1.0,
        extraction_method="deterministic"
    )

    cmp_delhivery_rev = FactComparison(
        id="cmp_delhivery_rev",
        fact_a_id=fact_delhivery_rev_ar.id,
        fact_b_id=fact_delhivery_rev_pres.id,
        fact_a=fact_delhivery_rev_ar,
        fact_b=fact_delhivery_rev_pres,
        relationship=RelationshipType.CONTEXTUAL_DIFFERENCE,
        difference_type=DifferenceType.UNIT,
        confidence=0.99,
        explanation=(
            "Apparent numerical contradiction (81,415 vs 8,142) is completely resolved by unit conversion: "
            "Annual Report p.4 uses Millions of Rupees (₹81,415 Mn), while Earnings Presentation p.6 uses Crores of Rupees (₹8,142 Cr). "
            "Since 1 Crore = 10 Million INR, 81,415 Million INR = 8,141.5 Crore INR, which rounds to 8,142 Cr. "
            "The relative difference is 0.006%, confirming factual equivalence."
        )
    )

    cases.append(
        ShowcaseCase(
            id="delhivery_unit_reconciliation",
            case_category="contextual_difference",
            title="Apparent Contradiction: Revenue in Millions vs Crores (₹81,415 Mn vs ₹8,142 Cr)",
            dataset="delhivery",
            description="Apparent 10x numerical disparity between documents is resolved by Indian vs International magnitude normalization.",
            facts=[fact_delhivery_rev_ar, fact_delhivery_rev_pres],
            comparison=cmp_delhivery_rev,
            why_it_matters="A naive numerical comparison engine would flag an erroneous 10x contradiction; normalization establishes true alignment."
        )
    )

    # =========================================================================
    # CASE 3 (Delhivery): Apparent Contradiction Reconciled by Time (PIN Code Expansion)
    # =========================================================================
    fact_delhivery_pin_pros = Fact(
        id="case_delhivery_pin_pros",
        document_id="doc_delhivery_pros_2022",
        document_name="01-delhivery-prospectus-2022-excerpt.pdf",
        page_number=47,
        entity="Delhivery",
        metric="PIN Codes Covered",
        value_raw="17,488",
        value_numeric=17488.0,
        unit="count",
        period="As of December 31, 2021",
        as_of_date="2021-12-31",
        scope="9-Month Period Ended Dec 31, 2021",
        evidence_text="Our express parcel delivery network, which serviced 17,488 PIN codes for the nine months period ended December 31, 2021",
        evidence_context="Prospectus p.47: serviced 17,488 PIN codes for the nine months period ended December 31, 2021, covering 90.61% of the 19,300 PIN codes in India",
        confidence=1.0,
        extraction_method="deterministic"
    )

    fact_delhivery_pin_ar = Fact(
        id="case_delhivery_pin_ar",
        document_id="doc_delhivery_ar_fy24",
        document_name="02-delhivery-annual-report-fy24-excerpt.pdf",
        page_number=2,
        entity="Delhivery",
        metric="PIN Codes Covered",
        value_raw="18,793",
        value_numeric=18793.0,
        unit="count",
        period="As of March 31, 2024",
        as_of_date="2024-03-31",
        scope="Cumulative Active Network",
        evidence_text="18,793\nPin codes covered\n(1) As of March 31, 2024",
        evidence_context="Corporate Overview p.2: 18,793 Pin codes covered (1) As of March 31, 2024",
        confidence=1.0,
        extraction_method="deterministic"
    )

    cmp_delhivery_pin = FactComparison(
        id="cmp_delhivery_pin",
        fact_a_id=fact_delhivery_pin_pros.id,
        fact_b_id=fact_delhivery_pin_ar.id,
        fact_a=fact_delhivery_pin_pros,
        fact_b=fact_delhivery_pin_ar,
        relationship=RelationshipType.CONTEXTUAL_DIFFERENCE,
        difference_type=DifferenceType.TEMPORAL,
        confidence=0.98,
        explanation=(
            "Apparent contradiction in pin code network reach (17,488 vs 18,793) is explained by temporal expansion: "
            "Prospectus 2022 p.47 reports network reach as of December 31, 2021 (17,488 pin codes), whereas Annual Report FY24 p.2 "
            "reports reach as of March 31, 2024 (18,793 pin codes). Over 27 months, network coverage expanded by 1,305 pin codes. "
            "Notice both documents maintain the exact same total national denominator of 19,300 pin codes in India."
        )
    )

    cases.append(
        ShowcaseCase(
            id="delhivery_temporal_pincodes",
            case_category="contextual_difference",
            title="Apparent Contradiction: Network Reach over Time (17,488 vs 18,793 PIN Codes)",
            dataset="delhivery",
            description="Differing network reach numbers are explained by chronological expansion from Dec 2021 to Mar 2024.",
            facts=[fact_delhivery_pin_pros, fact_delhivery_pin_ar],
            comparison=cmp_delhivery_pin,
            why_it_matters="Temporal metadata prevents false contradiction alerts during multi-year longitudinal analysis."
        )
    )

    # =========================================================================
    # CASE 4 (India Macro): Corroborating Fact Across 3 Institutional Reports
    # =========================================================================
    fact_macro_inf_survey = Fact(
        id="case_macro_inf_survey",
        document_id="doc_macro_survey",
        document_name="01-india-economic-survey-2024-25-excerpt.pdf",
        page_number=28,
        entity="India",
        metric="Headline CPI Inflation",
        value_raw="5.4 per cent",
        value_numeric=5.4,
        unit="percent",
        period="FY24",
        period_start="2023-04-01",
        period_end="2024-03-31",
        scope="Retail headline CPI",
        evidence_text="Retail headline inflation, as measured by the change in the Consumer Price Index (CPI), has softened from 5.4 per cent in FY24",
        evidence_context="Chapter 1 p.28: Retail headline inflation, as measured by the change in the Consumer Price Index (CPI), has softened from 5.4 per cent in FY24 to 4.9 per cent in April – December 2024",
        confidence=1.0,
        extraction_method="deterministic"
    )

    fact_macro_inf_imf = Fact(
        id="case_macro_inf_imf",
        document_id="doc_macro_imf",
        document_name="03-imf-india-2025-article-iv-excerpt.pdf",
        page_number=44,
        entity="India",
        metric="Headline CPI Inflation",
        value_raw="5.4%",
        value_numeric=5.4,
        unit="percent",
        period="2023/24",
        period_start="2023-04-01",
        period_end="2024-03-31",
        scope="Consumer prices - Combined (period average)",
        evidence_text="Consumer prices - Combined: 2023/24 = 5.4%",
        evidence_context="Statistical Appendix Table 1 (p.44): Consumer prices - Combined (percent change, period average): 2021/22: 5.5, 2022/23: 6.7, 2023/24: 5.4",
        confidence=1.0,
        extraction_method="deterministic"
    )

    cmp_macro_inf = FactComparison(
        id="cmp_macro_inf",
        fact_a_id=fact_macro_inf_survey.id,
        fact_b_id=fact_macro_inf_imf.id,
        fact_a=fact_macro_inf_survey,
        fact_b=fact_macro_inf_imf,
        relationship=RelationshipType.CORROBORATION,
        difference_type=DifferenceType.NONE,
        confidence=1.0,
        explanation=(
            "Both Government of India (Economic Survey 2024-25, p.28) and International Monetary Fund (IMF Article IV, p.44) "
            "independently corroborate that India's FY24 average headline CPI inflation was 5.4%."
        )
    )

    cases.append(
        ShowcaseCase(
            id="macro_corroboration_inflation",
            case_category="corroboration",
            title="Corroboration: FY24 Headline CPI Inflation (5.4%)",
            dataset="india-macroeconomy",
            description="Perfect consensus between Ministry of Finance Economic Survey and IMF Article IV report on FY24 headline inflation.",
            facts=[fact_macro_inf_survey, fact_macro_inf_imf],
            comparison=cmp_macro_inf,
            why_it_matters="Demonstrates cross-institutional agreement between national authorities and global multilateral bodies."
        )
    )

    # =========================================================================
    # CASE 5 (India Macro): Genuine Discrepancy from Statistical Vintage Revision (6.4% vs 6.5%)
    # =========================================================================
    fact_macro_gdp_survey = Fact(
        id="case_macro_gdp_survey",
        document_id="doc_macro_survey",
        document_name="01-india-economic-survey-2024-25-excerpt.pdf",
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
        evidence_text="As per the first advance estimates of national accounts, India’s real GDP is estimated to grow by 6.4 per cent in FY25.",
        evidence_context="Chapter 1 (p.4): In this global context, India displayed steady economic growth. As per the first advance estimates of national accounts, India’s real GDP is estimated to grow by 6.4 per cent in FY25.",
        confidence=1.0,
        extraction_method="deterministic"
    )

    fact_macro_gdp_rbi = Fact(
        id="case_macro_gdp_rbi",
        document_id="doc_macro_rbi",
        document_name="02-rbi-annual-report-2024-25-excerpt.pdf",
        page_number=24,
        entity="India",
        metric="Real GDP Growth",
        value_raw="6.5 per cent",
        value_numeric=6.5,
        unit="percent",
        period="2024-25",
        period_start="2024-04-01",
        period_end="2025-03-31",
        scope="Provisional Estimates (NSO)",
        evidence_text="Table II.2.1: Real GDP Growth ... 2024-25: 6.5 per cent (Source: NSO)",
        evidence_context="Table II.2.1: Real GDP Growth (Per cent) - 2020-21: -5.8, 2021-22: 9.7, 2022-23: 7.6, 2023-24: 9.2, 2024-25: 6.5. Source: NSO",
        confidence=1.0,
        extraction_method="deterministic"
    )

    cmp_macro_gdp = FactComparison(
        id="cmp_macro_gdp",
        fact_a_id=fact_macro_gdp_survey.id,
        fact_b_id=fact_macro_gdp_rbi.id,
        fact_a=fact_macro_gdp_survey,
        fact_b=fact_macro_gdp_rbi,
        relationship=RelationshipType.GENUINE_CONTRADICTION,
        difference_type=DifferenceType.REVISION,
        confidence=0.96,
        explanation=(
            "Genuine contradiction arising from official national accounts data vintage revision: "
            "Economic Survey 2024-25 was published using MoSPI's 'First Advance Estimates' (FAE) in early January 2025, which pegged FY25 growth at 6.4%. "
            "The Reserve Bank of India Annual Report (Table II.2.1) and IMF Article IV report cite the updated NSO provisional estimate of 6.5%. "
            "This is a real-world statistical revision divergence, not an extraction error."
        )
    )

    cases.append(
        ShowcaseCase(
            id="macro_gdp_revision",
            case_category="genuine_contradiction",
            title="Genuine Contradiction: FY25 Real GDP Growth (6.4% FAE vs 6.5% NSO/RBI)",
            dataset="india-macroeconomy",
            description="Statistical vintage discrepancy between early First Advance Estimates and subsequent NSO revisions.",
            facts=[fact_macro_gdp_survey, fact_macro_gdp_rbi],
            comparison=cmp_macro_gdp,
            why_it_matters="Identifies how official statistical revisions create contradictory figures across reports published at different dates."
        )
    )

    # =========================================================================
    # CASE 6 (India Macro): Apparent Contradiction Reconciled by Scope (9-Month vs 12-Month)
    # =========================================================================
    fact_macro_inf_9m = Fact(
        id="case_macro_inf_9m",
        document_id="doc_macro_survey",
        document_name="01-india-economic-survey-2024-25-excerpt.pdf",
        page_number=28,
        entity="India",
        metric="Headline CPI Inflation",
        value_raw="4.9 per cent",
        value_numeric=4.9,
        unit="percent",
        period="April - December 2024",
        period_start="2024-04-01",
        period_end="2024-12-31",
        scope="9-Month Partial Average",
        evidence_text="Retail headline inflation, as measured by the change in the Consumer Price Index (CPI), has softened from 5.4 per cent in FY24 to 4.9 per cent in April – December 2024.",
        evidence_context="Chapter 1 (p.28): Inflation – a combination of low and stable core inflation with volatile food prices. Retail headline inflation has softened from 5.4 per cent in FY24 to 4.9 per cent in April – December 2024.",
        confidence=1.0,
        extraction_method="deterministic"
    )

    fact_macro_inf_full = Fact(
        id="case_macro_inf_full",
        document_id="doc_macro_rbi",
        document_name="02-rbi-annual-report-2024-25-excerpt.pdf",
        page_number=9,
        entity="India",
        metric="Headline CPI Inflation",
        value_raw="4.6 per cent",
        value_numeric=4.6,
        unit="percent",
        period="2024-25",
        period_start="2024-04-01",
        period_end="2025-03-31",
        scope="Full Fiscal Year Average (12 months)",
        evidence_text="Headline inflation moderated to an average of 4.6 per cent in 2024-25 from 5.4 per cent in the previous year",
        evidence_context="Assessment and Prospects (p.9): Headline inflation moderated to an average of 4.6 per cent in 2024-25 from 5.4 per cent in the previous year, with all the three major sub-groups, viz., food, fuel and core (excluding food and fuel) inflation recording moderation.",
        confidence=1.0,
        extraction_method="deterministic"
    )

    cmp_macro_inf_scope = FactComparison(
        id="cmp_macro_inf_scope",
        fact_a_id=fact_macro_inf_9m.id,
        fact_b_id=fact_macro_inf_full.id,
        fact_a=fact_macro_inf_9m,
        fact_b=fact_macro_inf_full,
        relationship=RelationshipType.CONTEXTUAL_DIFFERENCE,
        difference_type=DifferenceType.SCOPE,
        confidence=0.98,
        explanation=(
            "Apparent contradiction (4.9% vs 4.6%) is explained by reporting scope: "
            "Economic Survey p.28 reports the 9-month average (April to December 2024) of 4.9%, "
            "whereas RBI Annual Report p.9 reports the complete 12-month full-year average for FY25 of 4.6%. "
            "Q4 disinflation (January-March 2025) pulled down the full-year average."
        )
    )

    cases.append(
        ShowcaseCase(
            id="macro_inflation_scope",
            case_category="contextual_difference",
            title="Apparent Contradiction: Partial vs Full-Year Inflation (4.9% 9M vs 4.6% Full Year)",
            dataset="india-macroeconomy",
            description="Apparent disagreement between Economic Survey and RBI Report resolved by temporal horizon and seasonal easing.",
            facts=[fact_macro_inf_9m, fact_macro_inf_full],
            comparison=cmp_macro_inf_scope,
            why_it_matters="Prevents false alarms when comparing interim mid-year disclosures against annual audited statements."
        )
    )

    # =========================================================================
    # CASE 7: Extraction & Reasoning Failure Modes Handled Transparently
    # =========================================================================
    failure_footnote = ExtractionFailure(
        id="fail_footnote_superscript",
        document_id="doc_macro_survey",
        document_name="01-india-economic-survey-2024-25-excerpt.pdf",
        page_number=20,
        failure_type=FailureType.PARSE_ERROR,
        raw_snippet="Information Technology (IT) companies also performed better than the previous quarter.17",
        explanation=(
            "Footnote marker attached to text: Naive digit parser would parse the trailing footnote marker '17' as a numeric quantity "
            "or year component. FactLens regex pre-filter identified that '17' was a superscript citation to footnote 17 ('Source: NASSCOM') "
            "and rejected it as an ungrounded standalone metric."
        ),
        attempted_fact={"entity": "IT Companies", "metric": "Quarter Performance", "value_raw": "17"}
    )

    cases.append(
        ShowcaseCase(
            id="failure_footnote_handling",
            case_category="extraction_failure",
            title="Handled Failure Mode: Footnote / Superscript Digit Merging",
            dataset="india-macroeconomy",
            description="Detection and refusal to hallucinate facts from footnote reference citations attached to sentence endings.",
            failure=failure_footnote,
            why_it_matters="Demonstrates system reliability by reporting an extraction boundary failure rather than fabricating an erroneous data point."
        )
    )

    return cases
