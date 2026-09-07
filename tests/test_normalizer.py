import pytest
from factlens.normalizer import (
    normalize_number_and_unit,
    normalize_period,
    normalize_entity,
    normalize_metric
)

def test_normalize_revenue_units_equivalence():
    # ₹81,415 Mn vs ₹8,142 Cr
    val_mn, unit_mn = normalize_number_and_unit("₹81,415Mn")
    val_cr, unit_cr = normalize_number_and_unit("₹8,142 Cr")

    assert unit_mn == "INR"
    assert unit_cr == "INR"
    assert val_mn == 81415000000.0
    assert val_cr == 81420000000.0

    # Relative difference is within 0.01%
    rel_diff = abs(val_mn - val_cr) / max(val_mn, val_cr)
    assert rel_diff < 0.001

def test_normalize_volumes_and_percentages():
    val_vol, unit_vol = normalize_number_and_unit("740Mn")
    assert val_vol == 740000000.0
    assert unit_vol == "count"

    val_pct1, unit_pct1 = normalize_number_and_unit("6.4 per cent")
    val_pct2, unit_pct2 = normalize_number_and_unit("6.5%")
    assert val_pct1 == 6.4
    assert unit_pct1 == "percent"
    assert val_pct2 == 6.5
    assert unit_pct2 == "percent"

def test_normalize_usd_billions():
    val, unit = normalize_number_and_unit("USD 634.6 billion")
    assert val == 634600000000.0
    assert unit == "USD"

def test_normalize_periods():
    # FY24
    start, end, as_of = normalize_period("FY24")
    assert start == "2023-04-01"
    assert end == "2024-03-31"

    # 2024-25
    start, end, as_of = normalize_period("2024-25")
    assert start == "2024-04-01"
    assert end == "2025-03-31"

    # April - December 2024 (9 months)
    start, end, as_of = normalize_period("April – December 2024")
    assert start == "2024-04-01"
    assert end == "2024-12-31"

    # As of March 31, 2024
    start, end, as_of = normalize_period("As of March 31, 2024")
    assert as_of == "2024-03-31"

def test_normalize_entity_and_metric():
    assert normalize_entity("Delhivery Limited") == "Delhivery"
    assert normalize_entity("Reserve Bank of India") == "Reserve Bank of India"
    assert normalize_entity("MoSPI Economic Survey") == "India"

    assert normalize_metric("Revenue from operations") == "revenue"
    assert normalize_metric("Revenue from services") == "revenue"
    assert normalize_metric("Express parcels shipped") == "express_parcel_volume"
    assert normalize_metric("Real GDP Growth") == "real_gdp_growth"
    assert normalize_metric("Retail headline inflation") == "headline_cpi_inflation"
