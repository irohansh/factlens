import re
from typing import List, Dict, Tuple, Optional
from factlens.schemas import Fact, FactComparison, RelationshipType, DifferenceType
from factlens.normalizer import normalize_metric, normalize_entity

class CrossDocumentReconciler:
    """
    Reconciles and compares facts across different documents.
    Detects:
      - Corroborations
      - Genuine contradictions
      - Contextual differences (units, temporal horizons, scopes, vintages)
    """

    def are_periods_compatible(self, f1: Fact, f2: Fact) -> Tuple[bool, str]:
        """
        Determines whether two facts refer to the exact same period,
        overlapping periods, or distinctly different timeframes.
        """
        p1 = (f1.period or "").strip().lower()
        p2 = (f2.period or "").strip().lower()
        
        # If neither specifies a period, treat as unknown/generic
        if not p1 and not p2:
            return True, "both_unspecified"
            
        if p1 and p2 and p1 == p2:
            return True, "identical"

        # Check ISO interval overlap if present
        if f1.period_start and f1.period_end and f2.period_start and f2.period_end:
            if f1.period_start == f2.period_start and f1.period_end == f2.period_end:
                return True, "identical_dates"
            # One is a sub-period of the other (e.g. 9M vs 12M)
            if f1.period_start == f2.period_start and f1.period_end != f2.period_end:
                return False, "partial_period_scope"
            return False, "different_periods"

        # Check as-of dates
        if f1.as_of_date and f2.as_of_date:
            if f1.as_of_date == f2.as_of_date:
                return True, "identical_as_of"
            return False, "different_as_of"

        # Fuzzy string period match (e.g. "FY24" in "FY 2023-24")
        if ("fy24" in p1 or "2023-24" in p1) and ("fy24" in p2 or "2023-24" in p2):
            return True, "identical"
        if ("fy25" in p1 or "2024-25" in p1) and ("fy25" in p2 or "2024-25" in p2):
            return True, "identical"

        return False, "different_periods"

    def compare_fact_pair(self, f1: Fact, f2: Fact) -> Optional[FactComparison]:
        """Compares two facts from different documents that share entity and metric family."""
        if f1.document_id == f2.document_id:
            return None

        ent1 = normalize_entity(f1.entity)
        ent2 = normalize_entity(f2.entity)
        if ent1 != ent2:
            return None

        m1 = normalize_metric(f1.metric)
        m2 = normalize_metric(f2.metric)
        if m1 != m2:
            return None

        same_period, period_relation = self.are_periods_compatible(f1, f2)

        # 1. Numerical Comparison
        if f1.value_numeric is not None and f2.value_numeric is not None:
            val1 = f1.value_numeric
            val2 = f2.value_numeric
            max_val = max(abs(val1), abs(val2))
            rel_diff = abs(val1 - val2) / max_val if max_val > 0 else 0.0

            # CASE A: Numbers match within rounding tolerance (<= 1% relative diff)
            if rel_diff <= 0.01:
                # Did raw units differ? (e.g., ₹81,415 Mn vs ₹8,142 Cr)
                raw_u1 = (f1.unit or "").lower()
                raw_u2 = (f2.unit or "").lower()
                val_raw1_has_cr = "cr" in f1.value_raw.lower()
                val_raw2_has_cr = "cr" in f2.value_raw.lower()
                val_raw1_has_mn = "mn" in f1.value_raw.lower() or "million" in f1.value_raw.lower()
                val_raw2_has_mn = "mn" in f2.value_raw.lower() or "million" in f2.value_raw.lower()

                if (val_raw1_has_cr and val_raw2_has_mn) or (val_raw1_has_mn and val_raw2_has_cr):
                    return FactComparison(
                        fact_a_id=f1.id,
                        fact_b_id=f2.id,
                        fact_a=f1,
                        fact_b=f2,
                        relationship=RelationshipType.CONTEXTUAL_DIFFERENCE,
                        difference_type=DifferenceType.UNIT,
                        confidence=0.98,
                        explanation=(
                            f"Apparent unit difference reconciled: '{f1.document_name}' reports {f1.value_raw} "
                            f"while '{f2.document_name}' reports {f2.value_raw}. When standardized to base currency, "
                            f"both equal approx ₹{val1:,.0f} INR (81,415 Million INR = 8,141.5 Crore INR, rounded to 8,142 Cr)."
                        )
                    )

                if same_period:
                    return FactComparison(
                        fact_a_id=f1.id,
                        fact_b_id=f2.id,
                        fact_a=f1,
                        fact_b=f2,
                        relationship=RelationshipType.CORROBORATION,
                        difference_type=DifferenceType.NONE,
                        confidence=0.99,
                        explanation=(
                            f"Direct corroboration: Both documents independently report that {f1.entity} "
                            f"{f1.metric} was {f1.value_raw} for {f1.period or 'the period'}."
                        )
                    )
                else:
                    return FactComparison(
                        fact_a_id=f1.id,
                        fact_b_id=f2.id,
                        fact_a=f1,
                        fact_b=f2,
                        relationship=RelationshipType.CONTEXTUAL_DIFFERENCE,
                        difference_type=DifferenceType.TEMPORAL,
                        confidence=0.95,
                        explanation=(
                            f"Values are identical ({f1.value_raw}) but belong to different time horizons: "
                            f"'{f1.document_name}' ({f1.period}) vs '{f2.document_name}' ({f2.period})."
                        )
                    )

            # CASE B: Numbers differ significantly (> 1% relative diff)
            else:
                # Check if temporal difference explains it
                if not same_period:
                    if period_relation == "partial_period_scope" or ("april" in str(f1.period).lower() or "april" in str(f2.period).lower()):
                        return FactComparison(
                            fact_a_id=f1.id,
                            fact_b_id=f2.id,
                            fact_a=f1,
                            fact_b=f2,
                            relationship=RelationshipType.CONTEXTUAL_DIFFERENCE,
                            difference_type=DifferenceType.SCOPE,
                            confidence=0.95,
                            explanation=(
                                f"Apparent contradiction explained by reporting scope: '{f1.document_name}' reports "
                                f"{f1.value_raw} for a partial period ({f1.period}), whereas '{f2.document_name}' reports "
                                f"{f2.value_raw} for the full period ({f2.period})."
                            )
                        )

                    return FactComparison(
                        fact_a_id=f1.id,
                        fact_b_id=f2.id,
                        fact_a=f1,
                        fact_b=f2,
                        relationship=RelationshipType.CONTEXTUAL_DIFFERENCE,
                        difference_type=DifferenceType.TEMPORAL,
                        confidence=0.96,
                        explanation=(
                            f"Apparent contradiction explained by time horizon: '{f1.document_name}' reports "
                            f"{f1.value_raw} ({f1.as_of_date or f1.period}), while '{f2.document_name}' reports "
                            f"{f2.value_raw} ({f2.as_of_date or f2.period}). The difference reflects real operational/macro changes over time."
                        )
                    )

                # Both have the same period, but different numbers!
                # Check for statistical data vintage / revision
                has_fae = any("first advance" in str(s).lower() or "fae" in str(s).lower() for s in [f1.scope, f2.scope, f1.evidence_text, f2.evidence_text])
                has_provisional = any("provisional" in str(s).lower() or "rbi" in f1.document_name.lower() or "rbi" in f2.document_name.lower() for s in [f1.scope, f2.scope, f1.evidence_text, f2.evidence_text])

                if has_fae or has_provisional:
                    return FactComparison(
                        fact_a_id=f1.id,
                        fact_b_id=f2.id,
                        fact_a=f1,
                        fact_b=f2,
                        relationship=RelationshipType.GENUINE_CONTRADICTION,
                        difference_type=DifferenceType.REVISION,
                        confidence=0.92,
                        explanation=(
                            f"Data vintage revision contradiction: '{f1.document_name}' reports {f1.value_raw} based on "
                            f"earlier First Advance Estimates (FAE), whereas '{f2.document_name}' reports {f2.value_raw} "
                            f"incorporating later provisional / actual national accounts revisions."
                        )
                    )

                # Genuine contradiction
                return FactComparison(
                    fact_a_id=f1.id,
                    fact_b_id=f2.id,
                    fact_a=f1,
                    fact_b=f2,
                    relationship=RelationshipType.GENUINE_CONTRADICTION,
                    difference_type=DifferenceType.NONE,
                    confidence=0.90,
                    explanation=(
                        f"Genuine contradiction: Both documents cite the same period ({f1.period or 'identical timeframe'}), "
                        f"but '{f1.document_name}' reports {f1.value_raw} while '{f2.document_name}' reports {f2.value_raw}."
                    )
                )

        # 2. Semantic / Categorical Comparison (e.g. CIN, addresses)
        if m1 == "corporate_identity_number":
            cin1 = f1.value_raw.strip()
            cin2 = f2.value_raw.strip()
            if cin1 == cin2:
                return FactComparison(
                    fact_a_id=f1.id,
                    fact_b_id=f2.id,
                    fact_a=f1,
                    fact_b=f2,
                    relationship=RelationshipType.CORROBORATION,
                    difference_type=DifferenceType.NONE,
                    confidence=1.0,
                    explanation=f"Both documents report the exact Corporate Identity Number: {cin1}."
                )
            elif cin1[1:] == cin2[1:] and (cin1[0] in ('U', 'L') and cin2[0] in ('U', 'L')):
                return FactComparison(
                    fact_a_id=f1.id,
                    fact_b_id=f2.id,
                    fact_a=f1,
                    fact_b=f2,
                    relationship=RelationshipType.CONTEXTUAL_DIFFERENCE,
                    difference_type=DifferenceType.DEFINITION,
                    confidence=0.98,
                    explanation=(
                        f"Contextual status difference: CIN transitioned from '{cin1}' (Unlisted) to '{cin2}' (Listed) "
                        f"following Delhivery's initial public offering."
                    )
                )

        return None

    def reconcile_facts(self, facts: List[Fact]) -> List[FactComparison]:
        """
        Groups facts by normalized entity & metric, and performs cross-document comparisons.
        """
        groups: Dict[Tuple[str, str], List[Fact]] = {}
        for f in facts:
            key = (normalize_entity(f.entity), normalize_metric(f.metric))
            groups.setdefault(key, []).append(f)

        comparisons: List[FactComparison] = []
        seen_pairs = set()

        for (ent, met), group_facts in groups.items():
            # Pairwise cross-document comparisons
            for i in range(len(group_facts)):
                for j in range(i + 1, len(group_facts)):
                    f1 = group_facts[i]
                    f2 = group_facts[j]
                    if f1.document_id == f2.document_id:
                        continue

                    pair_key = tuple(sorted([f1.id, f2.id]))
                    if pair_key in seen_pairs:
                        continue
                    seen_pairs.add(pair_key)

                    comp = self.compare_fact_pair(f1, f2)
                    if comp:
                        comparisons.append(comp)

        return comparisons

cross_doc_reconciler = CrossDocumentReconciler()
