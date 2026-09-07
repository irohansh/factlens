import re
import json
import logging
from typing import List, Tuple, Optional, Dict, Any
from pathlib import Path

from factlens.schemas import Fact, ExtractionFailure, FailureType, DocumentPage
from factlens.pdf_parser import verify_evidence_in_page, normalize_whitespace
from factlens.normalizer import (
    normalize_number_and_unit,
    normalize_period,
    normalize_entity,
    normalize_metric
)
from factlens.config import settings
from factlens.security import wrap_untrusted_prompt

logger = logging.getLogger(__name__)

# Heuristic Metric Regex Patterns
PATTERNS = [
    # 1. Express parcel shipments / volume
    {
        "family": "express_parcel_volume",
        "metric_name": "Express Parcel Shipments",
        "regex": r'(?:express\s*parcel\s*shipments?|express\s*parcels?\s*shipped)\s*(?:in\s*fy\d+)?\s*(?:since\s*inception)?',
        "val_regex": r'(\d[\d,.]*\s*(?:mn|million|bn|billion)|\b\d{3,}[\d,.]*)'
    },
    # 2. Revenue from operations / services
    {
        "family": "revenue",
        "metric_name": "Revenue from Services / Operations",
        "regex": r'(?:revenue\s*from\s*operations|revenue\s*from\s*services|fy\d+\s*revenue\s*from\s*services)',
        "val_regex": r'([₹$]\s*[\d,.]+(?:\s*(?:cr|crore|mn|million|bn|billion))?|[\d,.]+\s*(?:cr|crore|mn|million|bn|billion))'
    },
    # 3. EBITDA / Adjusted EBITDA
    {
        "family": "ebitda",
        "metric_name": "EBITDA",
        "regex": r'(?:adjusted\s*ebitda|adj\.\s*ebitda|ebitda)',
        "val_regex": r'([₹$]\s*\(?[\d,.]+\)?(?:\s*(?:cr|crore|mn|million))?|\(?[\d,.]+\)?\s*(?:cr|crore|mn|million|%))'
    },
    # 4. PIN codes covered
    {
        "family": "pincodes_covered",
        "metric_name": "PIN Codes Covered",
        "regex": r'(?:pin\s*codes?\s*covered|serviced\s*\d[\d,.]*\s*pin\s*codes?|reach\s*more\s*than\s*\d[\d,.]*\s*out\s*of\s*the\s*\d[\d,.]*\s*pin\s*codes)',
        "val_regex": r'(\d{1,2}[,\s]\d{3}|\b\d{4,5}\b)'
    },
    # 5. Real GDP growth
    {
        "family": "real_gdp_growth",
        "metric_name": "Real GDP Growth",
        "regex": r'(?:real\s*gdp\s*(?:growth)?|gdp\s*at\s*constant\s*prices|real\s*gdp\s*is\s*estimated\s*to\s*grow\s*by)',
        "val_regex": r'(\d[\d,.]*\s*(?:per\s*cent|%))'
    },
    # 6. Headline CPI Inflation
    {
        "family": "headline_cpi_inflation",
        "metric_name": "Headline CPI Inflation",
        "regex": r'(?:retail\s*headline\s*inflation|headline\s*inflation|consumer\s*prices\s*-\s*combined|cpi\s*inflation)',
        "val_regex": r'(\d[\d,.]*\s*(?:per\s*cent|%))'
    },
    # 7. Forex reserves
    {
        "family": "forex_reserves",
        "metric_name": "Foreign Exchange Reserves",
        "regex": r'(?:foreign\s*exchange\s*reserves|forex\s*reserves)',
        "val_regex": r'([₹$]?\s*(?:usd|us\$)?\s*[\d,.]+\s*(?:billion|bn|million|mn))'
    },
    # 8. Net working capital days
    {
        "family": "net_working_capital_days",
        "metric_name": "Net Working Capital Days",
        "regex": r'(?:net\s*working\s*capital\s*days|nwc\s*days)',
        "val_regex": r'(\d+)\s*days'
    },
    # 9. PTL freight delivered
    {
        "family": "ptl_freight_tonnage",
        "metric_name": "PTL Freight Delivered",
        "regex": r'(?:ptl\s*freight\s*(?:delivered|tonnage)|part[\s-]truckload\s*freight)',
        "val_regex": r'(\d[\d,.]*\s*(?:mn|million|k)?\s*tonnes?)'
    },
    # 10. Corporate Identity Number (CIN)
    {
        "family": "corporate_identity_number",
        "metric_name": "Corporate Identity Number (CIN)",
        "regex": r'(?:cin|corporate\s*identity\s*number)[^\w]*([UL]\d{5}[A-Z]{2}\d{4}[A-Z]{3}\d{6})',
        "val_regex": r'([UL]\d{5}[A-Z]{2}\d{4}[A-Z]{3}\d{6})'
    }
]


class DeterministicExtractor:
    """
    Robust rule-guided and regex parser for corporate and macroeconomic documents.
    Operates offline with zero external API dependencies.
    """

    def infer_document_entity(self, doc_name: str, sample_text: str) -> str:
        d = doc_name.lower()
        t = sample_text.lower()
        if "delhivery" in d or "delhivery" in t:
            return "Delhivery"
        if "rbi" in d or "reserve bank of india" in t:
            return "Reserve Bank of India"
        if "imf" in d or "article iv" in d or "international monetary fund" in t:
            return "IMF"
        if "economic-survey" in d or "survey" in d or "ministry of finance" in t:
            return "India"
        return "Unknown"

    def extract_from_card_layout(
        self, page: DocumentPage, doc_name: str, default_entity: str
    ) -> List[Fact]:
        """
        Handles infographic/card layouts where a number is on line N and the metric title is on line N+1 or N-1.
        Example:
            740Mn
            Express parcels shipped
            ₹81,415Mn
            Revenue from services
        """
        facts: List[Fact] = []
        lines = [l.strip() for l in page.text.splitlines() if l.strip()]
        
        for i in range(len(lines)):
            line = lines[i]
            # Ignore isolated single-digit or slide numbers like "1", "2", "3", "(1)"
            if re.match(r'^\(?\d{1,2}\)?$', line):
                continue
                
            # Check if line looks like a metric value: e.g. "740Mn", "₹81,415Mn", "1.6%", "₹1,266Mn", "1,429K tonnes", "18,793"
            is_num_candidate = bool(re.match(r'^[₹$]?\s*\(?[\d,.]+\)?\s*(?:cr|crore|mn|million|bn|billion|k|%|tonnes?|days)?$', line, re.IGNORECASE))
            if not is_num_candidate:
                continue

            # Prioritize following line (line i+1) as the label
            matched = False
            if i + 1 < len(lines):
                next_line = lines[i+1]
                for pat in PATTERNS:
                    if re.search(pat["regex"], next_line, re.IGNORECASE):
                        val_num, unit = normalize_number_and_unit(line)
                        if val_num is None:
                            continue
                        quote = f"{line}\n{next_line}"
                        is_grounded, conf, ctx = verify_evidence_in_page(quote, page.text)
                        if not is_grounded:
                            quote = line
                            is_grounded, conf, ctx = verify_evidence_in_page(quote, page.text)

                        period_str = "FY24" if ("fy24" in page.text.lower() or "fy 2023-24" in page.text.lower()) else None
                        p_start, p_end, as_of = normalize_period(period_str)

                        facts.append(
                            Fact(
                                document_id=page.document_id,
                                document_name=doc_name,
                                page_number=page.page_number,
                                entity=default_entity,
                                metric=pat["metric_name"],
                                value_raw=line,
                                value_numeric=val_num,
                                unit=unit,
                                period=period_str,
                                period_start=p_start,
                                period_end=p_end,
                                as_of_date=as_of,
                                scope="Consolidated" if "consolidated" in page.text.lower() else None,
                                evidence_text=quote,
                                evidence_context=ctx,
                                confidence=conf,
                                extraction_method="deterministic"
                            )
                        )
                        matched = True
                        break

            # If not matched by next line, check preceding line (line i-1)
            if not matched and i > 0:
                prev_line = lines[i-1]
                for pat in PATTERNS:
                    if re.search(pat["regex"], prev_line, re.IGNORECASE):
                        val_num, unit = normalize_number_and_unit(line)
                        if val_num is None:
                            continue
                        quote = f"{prev_line}\n{line}"
                        is_grounded, conf, ctx = verify_evidence_in_page(quote, page.text)
                        if not is_grounded:
                            quote = line
                            is_grounded, conf, ctx = verify_evidence_in_page(quote, page.text)

                        period_str = "FY24" if ("fy24" in page.text.lower() or "fy 2023-24" in page.text.lower()) else None
                        p_start, p_end, as_of = normalize_period(period_str)

                        facts.append(
                            Fact(
                                document_id=page.document_id,
                                document_name=doc_name,
                                page_number=page.page_number,
                                entity=default_entity,
                                metric=pat["metric_name"],
                                value_raw=line,
                                value_numeric=val_num,
                                unit=unit,
                                period=period_str,
                                period_start=p_start,
                                period_end=p_end,
                                as_of_date=as_of,
                                scope="Consolidated" if "consolidated" in page.text.lower() else None,
                                evidence_text=quote,
                                evidence_context=ctx,
                                confidence=conf,
                                extraction_method="deterministic"
                            )
                        )
                        break
        return facts

    def extract_from_sentences(
        self, page: DocumentPage, doc_name: str, default_entity: str
    ) -> Tuple[List[Fact], List[ExtractionFailure]]:
        """
        Extracts facts from prose sentences and table rows.
        """
        facts: List[Fact] = []
        failures: List[ExtractionFailure] = []
        
        # Split text into sentences/statements
        # Protect abbreviations like US$, USD, Rs., FY.
        cleaned_text = page.text.replace("\n", " ")
        sentences = re.split(r'(?<=[.!?])\s+(?=[A-Z0-9₹$])', cleaned_text)

        for sent in sentences:
            sent_str = sent.strip()
            if len(sent_str) < 15:
                continue

            for pat in PATTERNS:
                m_metric = re.search(pat["regex"], sent_str, re.IGNORECASE)
                if not m_metric:
                    continue

                # Search for numeric value in the sentence
                m_val = re.search(pat["val_regex"], sent_str, re.IGNORECASE)
                if not m_val:
                    continue

                raw_val = m_val.group(1).strip()
                
                # Check for footnote digit concatenation: e.g. "8,142 Cr(1)" or "5.4 per cent17"
                m_footnote = re.search(r'(\(\d+\)|\^\d+|\b\d{1,2}\b$)', raw_val)
                if m_footnote and not any(k in raw_val.lower() for k in ["cr", "mn", "bn"]):
                    # Possible footnote contamination, sanitize it
                    raw_val_clean = re.sub(r'[\(\)\^]', '', raw_val).strip()
                else:
                    raw_val_clean = raw_val

                val_num, unit = normalize_number_and_unit(raw_val_clean)
                if val_num is None:
                    continue

                # Guardrail: reject bare small integers (< 50) without explicit unit or currency for financial / operational metrics
                if unit == "count" and val_num < 50 and pat["family"] in ("revenue", "ebitda", "express_parcel_volume", "pincodes_covered"):
                    continue


                # Verify grounding against original page text
                is_grounded, conf, ctx = verify_evidence_in_page(sent_str[:120], page.text)
                if not is_grounded:
                    # Fallback to smaller quote around value
                    quote = sent_str[max(0, m_val.start() - 30): min(len(sent_str), m_val.end() + 30)].strip()
                    is_grounded, conf, ctx = verify_evidence_in_page(quote, page.text)
                else:
                    quote = sent_str[:120]

                if not is_grounded:
                    failures.append(
                        ExtractionFailure(
                            document_id=page.document_id,
                            document_name=doc_name,
                            page_number=page.page_number,
                            failure_type=FailureType.UNGROUNDED_EVIDENCE,
                            raw_snippet=sent_str[:150],
                            explanation=f"Could not verify verbatim grounding in page text for quote: '{quote}'",
                            attempted_fact={"metric": pat["metric_name"], "value": raw_val}
                        )
                    )
                    continue

                # Determine period and scope
                period_candidate = None
                m_p = re.search(r'(fy\s*\d{2,4}|20\d{2}[-/]\d{2,4}|april\s*[-–]\s*december\s*20\d{2}|as\s*of\s+[A-Za-z]+\s+\d{1,2},?\s+20\d{2}|[A-Za-z]+\s+\d{1,2},?\s+20\d{2})', sent_str, re.IGNORECASE)
                if m_p:
                    period_candidate = m_p.group(0).strip()
                elif "fy24" in page.text.lower() or "2023-24" in page.text.lower():
                    period_candidate = "FY24"
                elif "fy25" in page.text.lower() or "2024-25" in page.text.lower():
                    period_candidate = "FY25"

                p_start, p_end, as_of = normalize_period(period_candidate)

                scope = None
                if "first advance estimates" in sent_str.lower() or "fae" in sent_str.lower():
                    scope = "First Advance Estimates (FAE)"
                elif "provisional" in sent_str.lower():
                    scope = "Provisional Estimates"
                elif "consolidated" in sent_str.lower():
                    scope = "Consolidated"
                elif "standalone" in sent_str.lower():
                    scope = "Standalone"
                elif "nine months" in sent_str.lower() or "9m" in sent_str.lower():
                    scope = "9-Month Period"

                fact = Fact(
                    document_id=page.document_id,
                    document_name=doc_name,
                    page_number=page.page_number,
                    entity=default_entity,
                    metric=pat["metric_name"],
                    value_raw=raw_val,
                    value_numeric=val_num,
                    unit=unit,
                    period=period_candidate,
                    period_start=p_start,
                    period_end=p_end,
                    as_of_date=as_of,
                    scope=scope,
                    evidence_text=quote,
                    evidence_context=ctx,
                    confidence=conf,
                    extraction_method="deterministic"
                )
                facts.append(fact)

        return facts, failures

    def extract_from_page(
        self, page: DocumentPage, doc_name: str
    ) -> Tuple[List[Fact], List[ExtractionFailure]]:
        entity = self.infer_document_entity(doc_name, page.text)
        card_facts = self.extract_from_card_layout(page, doc_name, entity)
        sent_facts, failures = self.extract_from_sentences(page, doc_name, entity)
        
        all_facts = card_facts + sent_facts
        # De-duplicate by metric, raw_val, and page
        unique_facts: List[Fact] = []
        seen = set()
        for f in all_facts:
            key = (normalize_metric(f.metric), f.value_numeric, f.period, f.page_number)
            if key not in seen:
                seen.add(key)
                unique_facts.append(f)
                
        return unique_facts, failures


class LLMExtractor:
    """
    LLM-powered extractor using Google GenAI SDK with structured output.
    """
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.client = None
        if api_key:
            try:
                from google import genai
                self.client = genai.Client(api_key=api_key)
            except Exception as e:
                logger.warning(f"Failed to initialize google.genai Client: {e}")

    def extract_from_page(
        self, page: DocumentPage, doc_name: str
    ) -> Tuple[List[Fact], List[ExtractionFailure]]:
        if not self.client:
            return [], []

        prompt = (
            "You are an expert financial and macroeconomic fact extraction engine.\n"
            "Extract structured, verifiable facts from the provided document page.\n"
            "CRITICAL RULES:\n"
            "1. Every extracted fact MUST include an exact verbatim 'evidence_quote' from the text.\n"
            "2. DO NOT fabricate or guess facts, numbers, or dates.\n"
            "3. If a number has a footnote, do not merge footnote digits into the value.\n"
            "4. Return a JSON list of objects with fields: entity, metric, value_raw, unit, period, scope, evidence_quote.\n\n"
            f"{wrap_untrusted_prompt(page.text[:3500])}"
        )

        try:
            response = self.client.models.generate_content(
                model='gemini-2.5-flash',
                contents=prompt,
                config={'response_mime_type': 'application/json'}
            )
            raw_json = response.text
            items = json.loads(raw_json)
            if isinstance(items, dict) and "facts" in items:
                items = items["facts"]
            if not isinstance(items, list):
                return [], []

            facts: List[Fact] = []
            failures: List[ExtractionFailure] = []
            for item in items:
                quote = item.get("evidence_quote", "").strip()
                is_grounded, conf, ctx = verify_evidence_in_page(quote, page.text)
                if not is_grounded:
                    failures.append(
                        ExtractionFailure(
                            document_id=page.document_id,
                            document_name=doc_name,
                            page_number=page.page_number,
                            failure_type=FailureType.UNGROUNDED_EVIDENCE,
                            raw_snippet=quote,
                            explanation="LLM proposed evidence quote that could not be verified in source page text.",
                            attempted_fact=item
                        )
                    )
                    continue

                val_raw = str(item.get("value_raw", ""))
                val_num, unit = normalize_number_and_unit(val_raw)
                p_start, p_end, as_of = normalize_period(item.get("period"))

                facts.append(
                    Fact(
                        document_id=page.document_id,
                        document_name=doc_name,
                        page_number=page.page_number,
                        entity=normalize_entity(item.get("entity", "Unknown")),
                        metric=item.get("metric", "Unknown Metric"),
                        value_raw=val_raw,
                        value_numeric=val_num,
                        unit=unit or item.get("unit"),
                        period=item.get("period"),
                        period_start=p_start,
                        period_end=p_end,
                        as_of_date=as_of,
                        scope=item.get("scope"),
                        evidence_text=quote,
                        evidence_context=ctx,
                        confidence=conf,
                        extraction_method="llm"
                    )
                )
            return facts, failures
        except Exception as e:
            logger.error(f"LLM extraction error on page {page.page_number}: {e}")
            return [], [
                ExtractionFailure(
                    document_id=page.document_id,
                    document_name=doc_name,
                    page_number=page.page_number,
                    failure_type=FailureType.PARSE_ERROR,
                    raw_snippet="",
                    explanation=f"LLM extraction call failed: {e}"
                )
            ]


class FactExtractionService:
    """
    Unified extraction service orchestrating deterministic and LLM extractors.
    """
    def __init__(self):
        self.deterministic = DeterministicExtractor()
        self.llm = LLMExtractor(api_key=settings.GEMINI_API_KEY) if settings.GEMINI_API_KEY else None

    def extract_document(
        self, pages: List[DocumentPage], doc_name: str, force_deterministic: bool = False
    ) -> Tuple[List[Fact], List[ExtractionFailure]]:
        all_facts: List[Fact] = []
        all_failures: List[ExtractionFailure] = []

        use_llm = bool(self.llm and not force_deterministic)

        for page in pages:
            # Deterministic pass is fast and reliable
            d_facts, d_failures = self.deterministic.extract_from_page(page, doc_name)
            all_facts.extend(d_facts)
            all_failures.extend(d_failures)

            # If LLM is available and page has potential tabular or dense text
            if use_llm and len(page.text) > 200:
                l_facts, l_failures = self.llm.extract_from_page(page, doc_name)
                all_facts.extend(l_facts)
                all_failures.extend(l_failures)

        # Global de-duplication per document
        unique_facts: List[Fact] = []
        seen = set()
        for f in all_facts:
            key = (normalize_metric(f.metric), f.value_numeric, f.period, f.page_number)
            if key not in seen:
                seen.add(key)
                unique_facts.append(f)

        return unique_facts, all_failures

fact_extractor = FactExtractionService()
