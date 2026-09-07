import re
from typing import Tuple, Optional, Dict, Any

def normalize_number_and_unit(raw_value: str) -> Tuple[Optional[float], Optional[str]]:
    """
    Parses a raw numeric string (with currency symbols, suffixes like Mn, Cr, Bn, %, etc.)
    into a canonical float and standard unit.
    Standard units:
      - INR (base Indian Rupees)
      - USD (base US Dollars)
      - percent (%)
      - count (discrete items/parcels/pincodes)
      - tonnes (weight)
      - days (time duration)
    """
    if not raw_value:
        return None, None
        
    raw_str = str(raw_value).strip()
    is_inr = any(sym in raw_str.lower() for sym in ['₹', 'rs', 'inr', 'rupee'])
    is_usd = any(sym in raw_str.lower() for sym in ['$', 'usd', 'dollar'])
    is_pct = any(sym in raw_str.lower() for sym in ['%', 'per cent', 'percent', 'percentage'])
    is_days = 'day' in raw_str.lower()
    is_tons = any(sym in raw_str.lower() for sym in ['ton', 'tonne'])

    # Clean non-numeric characters except dots, minus, and digits
    cleaned = re.sub(r'[₹$,()]', '', raw_str)
    
    # Extract the main number match
    m = re.search(r'[-+]?\d*\.?\d+', cleaned)
    if not m:
        return None, None
        
    try:
        val = float(m.group(0))
    except ValueError:
        return None, None

    # Handle negative figures indicated by parentheses like (452 Cr)
    if '(' in raw_str and ')' in raw_str and not raw_str.strip().startswith('-'):
        val = -abs(val)

    lower_raw = raw_str.lower()

    if 'cr' in lower_raw or 'crore' in lower_raw:
        val *= 1e7
        unit = 'INR' if (is_inr or not is_usd) else 'USD'
    elif 'lakh' in lower_raw or 'lac' in lower_raw:
        val *= 1e5
        unit = 'INR' if (is_inr or not is_usd) else 'USD'
    elif 'mn' in lower_raw or 'million' in lower_raw:
        val *= 1e6
        if is_inr:
            unit = 'INR'
        elif is_usd:
            unit = 'USD'
        elif is_tons:
            unit = 'tonnes'
        else:
            unit = 'count'
    elif 'bn' in lower_raw or 'billion' in lower_raw:
        val *= 1e9
        if is_usd:
            unit = 'USD'
        elif is_inr:
            unit = 'INR'
        else:
            unit = 'count'
    elif 'k' in lower_raw and is_tons:
        val *= 1e3
        unit = 'tonnes'
    elif is_pct:
        unit = 'percent'
    elif is_days:
        unit = 'days'
    elif is_inr:
        unit = 'INR'
    elif is_usd:
        unit = 'USD'
    else:
        unit = 'count'
        
    return val, unit

def normalize_period(period_raw: Optional[str]) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """
    Normalizes a temporal expression into (period_start, period_end, as_of_date).
    Example:
      'FY24' -> ('2023-04-01', '2024-03-31', '2024-03-31')
      'FY25' -> ('2024-04-01', '2025-03-31', '2025-03-31')
      'April - December 2024' -> ('2024-04-01', '2024-12-31', '2024-12-31')
      'As of March 31, 2024' -> (None, None, '2024-03-31')
      'December 31, 2021' -> (None, None, '2021-12-31')
    """
    if not period_raw:
        return None, None, None
        
    p = period_raw.strip().lower()

    # Match FY 20XX or FYXX (Indian Fiscal Year runs April 1 to March 31)
    m_fy = re.search(r'fy\s*(\d{2,4})', p)
    if m_fy:
        year_token = int(m_fy.group(1))
        end_year = 2000 + year_token if year_token < 100 else year_token
        start_year = end_year - 1
        return f"{start_year}-04-01", f"{end_year}-03-31", f"{end_year}-03-31"

    # Match 2023-24 or 2024-25 or 2023/24
    m_range = re.search(r'(20\d{2})[-/](\d{2,4})', p)
    if m_range:
        start_year = int(m_range.group(1))
        end_suffix = int(m_range.group(2))
        end_year = (start_year // 100) * 100 + end_suffix if end_suffix < 100 else end_suffix
        return f"{start_year}-04-01", f"{end_year}-03-31", f"{end_year}-03-31"

    # Match April - December 2024 (9 months)
    if 'april' in p and 'december' in p:
        m_yr = re.search(r'20\d{2}', p)
        year = m_yr.group(0) if m_yr else "2024"
        return f"{year}-04-01", f"{year}-12-31", f"{year}-12-31"

    # Match specific point-in-time dates
    months = {
        'january': '01', 'february': '02', 'march': '03', 'april': '04',
        'may': '05', 'june': '06', 'july': '07', 'august': '08',
        'september': '09', 'october': '10', 'november': '11', 'december': '12',
        'jan': '01', 'feb': '02', 'mar': '03', 'apr': '04', 'may': '05',
        'jun': '06', 'jul': '07', 'aug': '08', 'sep': '09', 'oct': '10',
        'nov': '11', 'dec': '12'
    }
    for m_name, m_num in months.items():
        if m_name in p:
            # find day and year
            m_day = re.search(r'\b(\d{1,2})\b', p)
            m_yr = re.search(r'\b(20\d{2})\b', p)
            if m_yr:
                yr = m_yr.group(1)
                day = f"{int(m_day.group(1)):02d}" if m_day else "01"
                as_of = f"{yr}-{m_num}-{day}"
                return None, None, as_of

    return None, None, None

def normalize_entity(entity_raw: str) -> str:
    """Standardizes organizational/state entities to canonical names."""
    if not entity_raw:
        return "Unknown"
    e = entity_raw.strip().lower()
    if any(k in e for k in ["delhivery", "ssn logistics"]):
        return "Delhivery"
    if any(k in e for k in ["rbi", "reserve bank of india"]):
        return "Reserve Bank of India"
    if any(k in e for k in ["imf", "international monetary fund", "fund staff"]):
        return "IMF"
    if any(k in e for k in ["india", "government of india", "mospi", "nso", "economic survey"]):
        return "India"
    return entity_raw.strip()

def normalize_metric(metric_raw: str) -> str:
    """Standardizes metric phrases to canonical metric families."""
    if not metric_raw:
        return "unknown_metric"
    m = metric_raw.strip().lower()

    if any(k in m for k in ["revenue", "turnover", "topline"]):
        return "revenue"
    if "ebitda" in m:
        return "ebitda"
    if any(k in m for k in ["express parcel", "shipment volume", "parcels shipped"]):
        return "express_parcel_volume"
    if any(k in m for k in ["pin code", "pincode"]):
        return "pincodes_covered"
    if any(k in m for k in ["real gdp", "gdp growth"]):
        return "real_gdp_growth"
    if any(k in m for k in ["inflation", "cpi", "consumer price"]):
        return "headline_cpi_inflation"
    if any(k in m for k in ["forex reserve", "foreign exchange reserve"]):
        return "forex_reserves"
    if any(k in m for k in ["current account", "cad"]):
        return "current_account_deficit"
    if any(k in m for k in ["registered office", "corporate office", "office address"]):
        return "registered_office"
    if any(k in m for k in ["corporate identity number", "cin"]):
        return "corporate_identity_number"
    if any(k in m for k in ["working capital", "nwc days"]):
        return "net_working_capital_days"
    if any(k in m for k in ["freight tonnage", "part-truckload", "ptl"]):
        return "ptl_freight_tonnage"

    # Default fallback: clean snake_case
    clean = re.sub(r'[^a-zA-Z0-9]', '_', m).strip('_')
    return clean[:40]
