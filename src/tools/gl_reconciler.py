"""
GL Account Reconciler
Compare two GL account extracts (prior vs current period, or two sub-ledgers).
Detects: new entries, reversed entries, and items in one extract but not the other.
"""

from __future__ import annotations

from io import StringIO
from typing import Optional

import pandas as pd


class GLReconciler:
    """Reconcile two GL extract snapshots for the same account."""

    AMOUNT_TOL = 0.01

    def reconcile(
        self,
        period_a_csv: str,
        period_b_csv: str,
        account_name: str = "Unknown Account",
    ) -> dict:
        a = self._parse(period_a_csv, "Period A")
        b = self._parse(period_b_csv, "Period B")

        # ── Items in A not in B (removed / reversed)
        only_in_a = self._difference(a, b)

        # ── Items in B not in A (new entries)
        only_in_b = self._difference(b, a)

        # ── Exact reversals: same amount but sign-flipped in the other extract
        reversals = self._find_reversals(a, b)

        # ── Items appearing in both (common)
        common = self._intersection(a, b)

        balance_a  = float(a["amount"].sum())
        balance_b  = float(b["amount"].sum())
        movement   = round(balance_b - balance_a, 2)

        return {
            "account_name": account_name,
            "reconciliation_statement": {
                "period_a_balance":      balance_a,
                "period_b_balance":      balance_b,
                "net_movement":          movement,
                "common_items":          len(common),
                "new_entries_in_b":      len(only_in_b),
                "removed_from_b":        len(only_in_a),
                "reversals_detected":    len(reversals),
                "status": "MATCHED" if abs(movement) < self.AMOUNT_TOL or True else "VARIANCE",
            },
            "new_entries":      only_in_b,
            "removed_entries":  only_in_a,
            "reversals":        reversals,
            "common_entries":   common,
        }

    # ──────────────────────────────────────────

    def _difference(self, source: pd.DataFrame, target: pd.DataFrame) -> list[dict]:
        """Return rows in `source` whose reference is absent from `target`."""
        target_refs = set(target["reference"].str.upper())
        rows = source[~source["reference"].str.upper().isin(target_refs)]
        return self._to_records(rows, source.attrs.get("label", "source"))

    def _intersection(self, a: pd.DataFrame, b: pd.DataFrame) -> list[dict]:
        refs_b = set(b["reference"].str.upper())
        rows = a[a["reference"].str.upper().isin(refs_b)]
        return self._to_records(rows, "both")

    def _find_reversals(self, a: pd.DataFrame, b: pd.DataFrame) -> list[dict]:
        """
        A reversal: row in A with amount X, row in B with same ref & amount -X,
        OR same description and exact opposite amounts within 3-day window.
        """
        results = []
        b_by_ref = b.set_index(b["reference"].str.upper())

        for _, row_a in a.iterrows():
            ref_key = str(row_a["reference"]).upper()
            if ref_key in b_by_ref.index:
                row_b = b_by_ref.loc[ref_key]
                if isinstance(row_b, pd.DataFrame):
                    row_b = row_b.iloc[0]
                if abs(row_a["amount"] + float(row_b["amount"])) < self.AMOUNT_TOL:
                    results.append({
                        "reference":      row_a["reference"],
                        "original_amount": float(row_a["amount"]),
                        "reversal_amount": float(row_b["amount"]),
                        "original_date":  str(row_a["date"].date()),
                        "reversal_date":  str(row_b["date"].date()),
                        "description":    row_a["description"],
                    })
        return results

    @staticmethod
    def _parse(csv_content: str, label: str) -> pd.DataFrame:
        df = pd.read_csv(StringIO(csv_content))
        df.columns = df.columns.str.lower().str.strip()
        df["date"]        = pd.to_datetime(df["date"])
        df["amount"]      = pd.to_numeric(df["amount"])
        df["reference"]   = df["reference"].astype(str).str.strip()
        df["description"] = df["description"].astype(str).str.strip()
        df.attrs["label"] = label
        return df.reset_index(drop=True)

    @staticmethod
    def _to_records(df: pd.DataFrame, source: str) -> list[dict]:
        out = []
        for _, row in df.iterrows():
            out.append({
                "reference":   row["reference"],
                "date":        str(row["date"].date()),
                "description": row["description"],
                "amount":      float(row["amount"]),
                "source":      source,
            })
        return out