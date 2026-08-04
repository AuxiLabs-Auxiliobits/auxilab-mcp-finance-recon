"""
Intercompany Balance Checker
Compare two entity ledgers for a shared intercompany account.
Identifies balance mismatches and separates currency-related differences.
"""

from __future__ import annotations

from io import StringIO
from typing import Optional

import pandas as pd


CURRENCY_ROUNDING_THRESHOLD = 5.00   # differences ≤ this treated as FX rounding
SIGNIFICANT_MISMATCH_THRESHOLD = 100.00


class IntercompanyChecker:

    def check(
        self,
        entity_a_csv: str,
        entity_b_csv: str,
        entity_a_name: str = "Entity A",
        entity_b_name: str = "Entity B",
        base_currency: str = "USD",
    ) -> dict:
        a = self._parse(entity_a_csv)
        b = self._parse(entity_b_csv)

        balance_a = float(a["amount"].sum())
        # Entity B records the mirror side, so negate for comparison
        balance_b_raw = float(b["amount"].sum())
        balance_b_mirror = -balance_b_raw

        gross_mismatch = round(balance_a - balance_b_mirror, 2)
        abs_mismatch   = abs(gross_mismatch)

        # ── Transaction-level matching
        matched, only_a, only_b = self._match_transactions(a, b, entity_a_name, entity_b_name)

        # ── Classify the mismatch
        currency_component, timing_component = self._split_mismatch(only_a, only_b, gross_mismatch)

        risk = (
            "CRITICAL" if abs_mismatch > 10_000
            else "HIGH"   if abs_mismatch > 1_000
            else "MEDIUM" if abs_mismatch > SIGNIFICANT_MISMATCH_THRESHOLD
            else "LOW"    if abs_mismatch > CURRENCY_ROUNDING_THRESHOLD
            else "NONE"
        )

        return {
            "summary": {
                "entity_a":           entity_a_name,
                "entity_b":           entity_b_name,
                "base_currency":      base_currency,
                "entity_a_balance":   balance_a,
                "entity_b_balance_raw": balance_b_raw,
                "entity_b_mirror":    balance_b_mirror,
                "gross_mismatch":     gross_mismatch,
                "currency_component": currency_component,
                "timing_component":   timing_component,
                "unexplained":        round(gross_mismatch - currency_component - timing_component, 2),
                "mismatch_risk":      risk,
                "status": "AGREE" if abs_mismatch < 0.01 else "MISMATCH",
                "action_required": abs_mismatch >= CURRENCY_ROUNDING_THRESHOLD,
            },
            "matched_transactions": matched,
            "entity_a_only":        only_a,
            "entity_b_only":        only_b,
            "mismatch_detail": {
                "description": self._mismatch_narrative(
                    entity_a_name, entity_b_name, balance_a, balance_b_mirror,
                    gross_mismatch, currency_component
                ),
                "recommended_action": self._recommend(risk, gross_mismatch),
            }
        }

    # ──────────────────────────────────────────

    def _match_transactions(self, a, b, name_a, name_b):
        matched, only_a, only_b = [], [], list(range(len(b)))

        for _, ra in a.iterrows():
            best = self._find_match(ra, b, only_b)
            if best is not None:
                rb = b.iloc[best]
                matched.append({
                    "reference_a":  ra["reference"],
                    "reference_b":  rb["reference"],
                    "date_a":       str(ra["date"].date()),
                    "date_b":       str(rb["date"].date()),
                    "amount_a":     float(ra["amount"]),
                    "amount_b":     float(rb["amount"]),
                    "net_diff":     round(float(ra["amount"]) + float(rb["amount"]), 2),
                })
                only_b.remove(best)
            else:
                only_a.append({**self._row_dict(ra), "entity": name_a})

        for i in only_b:
            only_b_item = {**self._row_dict(b.iloc[i]), "entity": name_b}

        return matched, only_a, [
            {**self._row_dict(b.iloc[i]), "entity": name_b} for i in only_b
        ]

    def _find_match(self, row_a, b, available, tol=0.01, date_tol=5):
        for idx in available:
            rb = b.iloc[idx]
            amount_match = abs(float(row_a["amount"]) + float(rb["amount"])) <= tol
            date_diff = abs((row_a["date"] - rb["date"]).days)
            if amount_match and date_diff <= date_tol:
                return idx
        return None

    def _split_mismatch(self, only_a, only_b, gross):
        """Estimate FX/rounding component vs timing component."""
        # Small-value unmatched items ← likely FX rounding
        fx = sum(
            abs(i["amount"])
            for i in (only_a + only_b)
            if abs(i["amount"]) <= CURRENCY_ROUNDING_THRESHOLD
        )
        # Rest of unmatched ← timing
        timing = sum(
            abs(i["amount"])
            for i in (only_a + only_b)
            if abs(i["amount"]) > CURRENCY_ROUNDING_THRESHOLD
        )
        return round(min(fx, abs(gross)), 2), round(min(timing, abs(gross) - fx), 2)

    @staticmethod
    def _mismatch_narrative(ea, eb, bal_a, bal_b, mismatch, fx_part):
        sign = "greater" if mismatch > 0 else "lower"
        return (
            f"{ea} reports a balance of {bal_a:,.2f}, while {eb} reports a mirror balance of "
            f"{bal_b:,.2f}. The gross mismatch is {abs(mismatch):,.2f} "
            f"({sign} on {ea}'s side). "
            f"Estimated FX/rounding component: {fx_part:,.2f}."
        )

    @staticmethod
    def _recommend(risk, mismatch):
        if risk == "NONE":
            return "No action required — balances agree within tolerance."
        if risk == "LOW":
            return "Review FX conversion rates applied. Likely a rounding difference."
        if risk == "MEDIUM":
            return "Identify unposted transactions. Check for timing differences at period-end."
        if risk == "HIGH":
            return "Escalate to intercompany team. Locate missing journal entries in both entities."
        return "IMMEDIATE escalation required. Freeze intercompany account and perform full reconciliation."

    @staticmethod
    def _parse(csv_content: str) -> pd.DataFrame:
        df = pd.read_csv(StringIO(csv_content))
        df.columns = df.columns.str.lower().str.strip()
        df["date"]   = pd.to_datetime(df["date"])
        df["amount"] = pd.to_numeric(df["amount"])
        df["reference"]   = df["reference"].astype(str).str.strip()
        df["description"] = df["description"].astype(str).str.strip()
        return df.reset_index(drop=True)

    @staticmethod
    def _row_dict(row) -> dict:
        return {
            "reference":   row["reference"],
            "date":        str(row["date"].date()),
            "description": row["description"],
            "amount":      float(row["amount"]),
        }