"""
Bank Statement Matcher
Match bank statement transactions against a GL cash account ledger.
Matching criteria: exact amount (±0.01) + date proximity (±3 days).
Description fuzzy-match used as tiebreaker only.
"""

from __future__ import annotations

from io import StringIO
from typing import Optional

import pandas as pd

try:
    from rapidfuzz import fuzz as _fuzz
    def _desc_score(a: str, b: str) -> float:
        return _fuzz.token_sort_ratio(str(a), str(b))
except ImportError:
    import difflib
    def _desc_score(a: str, b: str) -> float:
        return difflib.SequenceMatcher(None, str(a).lower(), str(b).lower()).ratio() * 100


class BankMatcher:
    """Match bank statement rows against GL ledger rows."""

    def __init__(
        self,
        date_tolerance_days: int = 3,
        amount_tolerance: float = 0.01,
    ):
        self.date_tol = date_tolerance_days
        self.amount_tol = amount_tolerance

    # ──────────────────────────────────────────
    # Public API
    # ──────────────────────────────────────────

    def match(
        self,
        bank_csv: str,
        gl_csv: str,
        opening_balance: float = 0.0,
    ) -> dict:
        bank = self._parse(bank_csv)
        gl = self._parse(gl_csv)

        matched_pairs: list[dict] = []
        unmatched_bank: list[dict] = []
        available_gl: set[int] = set(range(len(gl)))

        for b_idx, b_row in bank.iterrows():
            candidate = self._find_best_match(b_row, gl, available_gl)

            if candidate is not None:
                g_row = gl.iloc[candidate]
                date_diff = int(abs((b_row["date"] - g_row["date"]).days))
                matched_pairs.append({
                    "bank_reference":   b_row["reference"],
                    "bank_date":        str(b_row["date"].date()),
                    "bank_description": b_row["description"],
                    "bank_amount":      float(b_row["amount"]),
                    "gl_reference":     g_row["reference"],
                    "gl_date":          str(g_row["date"].date()),
                    "gl_description":   g_row["description"],
                    "gl_amount":        float(g_row["amount"]),
                    "date_diff_days":   date_diff,
                    "match_confidence": "HIGH" if date_diff == 0 else (
                                        "MEDIUM" if date_diff <= 1 else "LOW"),
                })
                available_gl.discard(candidate)
            else:
                unmatched_bank.append(self._row_to_dict(b_row, "BANK"))

        unmatched_gl = [
            self._row_to_dict(gl.iloc[i], "GL") for i in sorted(available_gl)
        ]

        bank_total = float(bank["amount"].sum())
        gl_total   = float(gl["amount"].sum())
        diff       = round(bank_total - gl_total, 2)

        return {
            "reconciliation_summary": {
                "opening_balance":      opening_balance,
                "closing_balance":      round(opening_balance + bank_total, 2),
                "bank_transactions":    len(bank),
                "gl_transactions":      len(gl),
                "matched_pairs":        len(matched_pairs),
                "unmatched_bank_count": len(unmatched_bank),
                "unmatched_gl_count":   len(unmatched_gl),
                "bank_total":           bank_total,
                "gl_total":             gl_total,
                "difference":           diff,
                "match_rate_pct":       round(len(matched_pairs) / len(bank) * 100, 1),
                "status": "RECONCILED" if abs(diff) < self.amount_tol else "UNRECONCILED",
            },
            "matched_pairs":      matched_pairs,
            "unmatched_bank_items": unmatched_bank,
            "unmatched_gl_items":   unmatched_gl,
        }

    # ──────────────────────────────────────────
    # Private helpers
    # ──────────────────────────────────────────

    def _find_best_match(
        self,
        b_row: pd.Series,
        gl: pd.DataFrame,
        available: set[int],
    ) -> Optional[int]:
        best_idx: Optional[int] = None
        best_score: float = -1.0

        for g_idx in available:
            g_row = gl.iloc[g_idx]

            # Hard gate: amount must match within tolerance
            if abs(b_row["amount"] - g_row["amount"]) > self.amount_tol:
                continue

            # Hard gate: date proximity
            date_diff = abs((b_row["date"] - g_row["date"]).days)
            if date_diff > self.date_tol:
                continue

            # Soft tiebreaker: description similarity
            score = _desc_score(b_row["description"], g_row["description"])
            # Penalise date gap so same-day wins over far-day
            adjusted = score - (date_diff * 3)

            if adjusted > best_score:
                best_score = adjusted
                best_idx = g_idx

        return best_idx

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
    def _row_to_dict(row: pd.Series, source: str) -> dict:
        return {
            "reference":   row["reference"],
            "date":        str(row["date"].date()),
            "description": row["description"],
            "amount":      float(row["amount"]),
            "source":      source,
        }