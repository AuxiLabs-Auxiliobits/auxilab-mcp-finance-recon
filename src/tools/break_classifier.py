"""
Reconciliation Break Classifier
Rules-based classification of unreconciled items.
Possible classes:
  - Timing Difference
  - Missing Entry
  - Duplicate Posting
  - Currency Rounding
  - Intercompany Mismatch
  - Unknown

Each class carries a recommended next action.
"""

from __future__ import annotations

import re
from io import StringIO
from datetime import datetime

import pandas as pd


# ── Keyword patterns for rule matching ──────────────────────────────

TIMING_KEYWORDS = [
    r"timing", r"transit", r"in.?transit", r"outstanding", r"pending",
    r"cut.?off", r"cut off", r"clearing", r"uncleared", r"deposit in transit",
]

MISSING_KEYWORDS = [
    r"missing", r"not posted", r"unposted", r"no entry", r"not recorded",
    r"not in (gl|bank|ledger)", r"no (gl|bank) entry",
]

DUPLICATE_KEYWORDS = [
    r"duplicate", r"dup\b", r"double.?post", r"posted twice", r"twice",
    r"double entry", r"repeat",
]

FX_KEYWORDS = [
    r"fx", r"foreign exchange", r"currency", r"forex", r"exchange rate",
    r"rounding", r"round.?diff", r"translation", r"revaluation", r"usd|eur|gbp|inr|sgd",
]

IC_KEYWORDS = [
    r"interco", r"intercompany", r"inter.?company", r"related party",
    r"entity [a-z]", r"subsidiary", r"affiliate", r"intra.?group",
]


NEXT_ACTION: dict[str, str] = {
    "Timing Difference":    "Confirm posting date alignment. Items should self-clear next period.",
    "Missing Entry":        "Raise journal entry request to posting team. Attach supporting document.",
    "Duplicate Posting":    "Verify original and duplicate reference. Reverse duplicate entry.",
    "Currency Rounding":    "Check FX rate applied on transaction date. Post rounding adjustment if > tolerance.",
    "Intercompany Mismatch":"Circulate confirmation to counterpart entity. Agree on journal adjustments.",
    "Unknown":              "Escalate to Senior Accountant for manual investigation.",
}


class BreakClassifier:

    SMALL_AMOUNT_THRESHOLD = 10.00    # ≤ this → Currency Rounding candidate
    LARGE_AMOUNT_THRESHOLD = 50_000   # ≥ this → flag as HIGH priority

    def classify(self, breaks_csv: str) -> dict:
        df = self._parse(breaks_csv)
        classified: list[dict] = []

        for _, row in df.iterrows():
            category, confidence = self._classify_row(row)
            priority = self._priority(row, category)
            classified.append({
                "reference":      row["reference"],
                "date":           str(row["date"].date()),
                "description":    row["description"],
                "amount":         float(row["amount"]),
                "source":         row.get("source", "UNKNOWN"),
                "category":       category,
                "confidence":     confidence,
                "priority":       priority,
                "recommended_action": NEXT_ACTION[category],
            })

        # ── Summary stats
        from collections import Counter
        cat_counts = Counter(r["category"] for r in classified)
        total_exposure = sum(abs(r["amount"]) for r in classified)

        return {
            "classification_summary": {
                "total_breaks":       len(classified),
                "total_exposure":     round(total_exposure, 2),
                "by_category":        dict(cat_counts),
                "high_priority":      sum(1 for r in classified if r["priority"] == "HIGH"),
            },
            "classified_breaks": classified,
        }

    # ──────────────────────────────────────────

    def _classify_row(self, row: pd.Series) -> tuple[str, str]:
        text = f"{row['description']} {row.get('source', '')}".lower()
        amount = abs(float(row["amount"]))

        # Rule 1: Currency Rounding — small amount
        if amount <= self.SMALL_AMOUNT_THRESHOLD:
            if self._match(text, FX_KEYWORDS):
                return "Currency Rounding", "HIGH"
            return "Currency Rounding", "MEDIUM"

        # Rule 2: Explicit keyword matches (checked high→low specificity)
        if self._match(text, DUPLICATE_KEYWORDS):
            return "Duplicate Posting", "HIGH"

        if self._match(text, IC_KEYWORDS):
            return "Intercompany Mismatch", "HIGH"

        if self._match(text, FX_KEYWORDS):
            return "Currency Rounding", "HIGH"

        if self._match(text, MISSING_KEYWORDS):
            return "Missing Entry", "HIGH"

        if self._match(text, TIMING_KEYWORDS):
            return "Timing Difference", "MEDIUM"

        # Rule 3: Source-based heuristics
        source = str(row.get("source", "")).upper()
        if source == "BANK" and amount < 500:
            return "Timing Difference", "LOW"
        if source == "GL" and amount > 1_000:
            return "Missing Entry", "MEDIUM"

        # Rule 4: Round-number amounts often indicate manual/estimated entries
        if amount % 1000 == 0 and amount > 0:
            return "Missing Entry", "LOW"

        return "Unknown", "LOW"

    def _priority(self, row: pd.Series, category: str) -> str:
        amount = abs(float(row["amount"]))
        if amount >= self.LARGE_AMOUNT_THRESHOLD:
            return "HIGH"
        if category in ("Duplicate Posting", "Missing Entry", "Intercompany Mismatch"):
            return "MEDIUM"
        return "LOW"

    @staticmethod
    def _match(text: str, patterns: list[str]) -> bool:
        return any(re.search(p, text, re.IGNORECASE) for p in patterns)

    @staticmethod
    def _parse(csv_content: str) -> pd.DataFrame:
        df = pd.read_csv(StringIO(csv_content))
        df.columns = df.columns.str.lower().str.strip()
        df["date"]   = pd.to_datetime(df["date"])
        df["amount"] = pd.to_numeric(df["amount"])
        for col in ("reference", "description", "source"):
            if col in df.columns:
                df[col] = df[col].astype(str).str.strip()
            else:
                df[col] = "UNKNOWN"
        return df.reset_index(drop=True)