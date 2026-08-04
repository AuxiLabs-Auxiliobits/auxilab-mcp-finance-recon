"""
Month-End Close Tracker
Track progress across all reconciliation tasks in a close pack.
Returns completion %, overdue items, not-started items,
and a risk flag based on deadline proximity.
"""

from __future__ import annotations

from io import StringIO
from datetime import datetime, date

import pandas as pd


VALID_STATUSES = {"complete", "in progress", "not started", "overdue", "on hold"}

STATUS_WEIGHT = {
    "complete":     1.0,
    "in progress":  0.5,
    "not started":  0.0,
    "overdue":      0.0,
    "on hold":      0.0,
}


class CloseTracker:

    DEADLINE_CRITICAL_DAYS = 1   # < this → CRITICAL
    DEADLINE_HIGH_DAYS     = 2   # ≤ this → HIGH

    def track(
        self,
        tasks_csv: str,
        close_deadline: str,
        as_of_date: str | None = None,
    ) -> dict:
        tasks = self._parse(tasks_csv)
        today = (
            datetime.strptime(as_of_date, "%Y-%m-%d").date()
            if as_of_date
            else date.today()
        )
        deadline = datetime.strptime(close_deadline, "%Y-%m-%d").date()
        days_to_deadline = (deadline - today).days

        # ── Enrich each task
        enriched: list[dict] = []
        for _, row in tasks.iterrows():
            due = row["due_date"].date() if pd.notna(row["due_date"]) else deadline
            status_norm = str(row["status"]).strip().lower()
            is_overdue = (due < today) and status_norm not in ("complete",)
            actual_status = "overdue" if is_overdue else status_norm

            enriched.append({
                "account_name": row["account_name"],
                "owner":        row["owner"],
                "status":       actual_status,
                "due_date":     str(due),
                "is_overdue":   is_overdue,
                "days_overdue": max(0, (today - due).days) if is_overdue else 0,
            })

        total       = len(enriched)
        complete    = sum(1 for t in enriched if t["status"] == "complete")
        overdue     = [t for t in enriched if t["is_overdue"]]
        not_started = [t for t in enriched if t["status"] == "not started"]
        in_progress = [t for t in enriched if t["status"] == "in progress"]
        on_hold     = [t for t in enriched if t["status"] == "on hold"]

        outstanding = total - complete
        completion_pct = round(complete / total * 100, 1) if total else 0.0

        # ── Risk rating
        risk = self._risk_rating(
            days_to_deadline=days_to_deadline,
            outstanding=outstanding,
            overdue_count=len(overdue),
            completion_pct=completion_pct,
        )

        return {
            "close_status": {
                "as_of_date":           str(today),
                "close_deadline":       str(deadline),
                "days_to_deadline":     days_to_deadline,
                "total_tasks":          total,
                "complete":             complete,
                "in_progress":          len(in_progress),
                "not_started":          len(not_started),
                "overdue":              len(overdue),
                "on_hold":              len(on_hold),
                "outstanding":          outstanding,
                "completion_pct":       completion_pct,
                "risk_flag":            risk["level"],
                "risk_rationale":       risk["rationale"],
                "close_achievable":     risk["achievable"],
            },
            "overdue_items":     overdue,
            "not_started_items": not_started,
            "all_tasks":         enriched,
        }

    # ──────────────────────────────────────────

    def _risk_rating(
        self,
        days_to_deadline: int,
        outstanding: int,
        overdue_count: int,
        completion_pct: float,
    ) -> dict:
        if days_to_deadline < 0:
            return {
                "level": "CRITICAL",
                "rationale": f"Close deadline has passed. {outstanding} tasks still outstanding.",
                "achievable": False,
            }

        if days_to_deadline <= self.DEADLINE_CRITICAL_DAYS and outstanding > 0:
            return {
                "level": "CRITICAL",
                "rationale": (
                    f"Deadline is TODAY or TOMORROW with {outstanding} outstanding tasks. "
                    "Immediate management escalation required."
                ),
                "achievable": outstanding <= 2,
            }

        if days_to_deadline <= self.DEADLINE_HIGH_DAYS and outstanding > 3:
            return {
                "level": "HIGH",
                "rationale": (
                    f"{outstanding} tasks outstanding with only {days_to_deadline} day(s) remaining. "
                    "Prioritise high-value accounts immediately."
                ),
                "achievable": False,
            }

        if overdue_count >= 3 or completion_pct < 50:
            return {
                "level": "HIGH",
                "rationale": (
                    f"{overdue_count} overdue tasks and {completion_pct:.0f}% completion. "
                    "Resource allocation review required."
                ),
                "achievable": days_to_deadline >= 3,
            }

        if overdue_count > 0 or completion_pct < 75:
            return {
                "level": "MEDIUM",
                "rationale": (
                    f"{completion_pct:.0f}% complete with {days_to_deadline} day(s) to deadline. "
                    "Monitor closely."
                ),
                "achievable": True,
            }

        return {
            "level": "LOW",
            "rationale": f"Close on track. {completion_pct:.0f}% complete, {days_to_deadline} day(s) remaining.",
            "achievable": True,
        }

    @staticmethod
    def _parse(csv_content: str) -> pd.DataFrame:
        df = pd.read_csv(StringIO(csv_content))
        df.columns = df.columns.str.lower().str.strip()
        df["due_date"]     = pd.to_datetime(df["due_date"], errors="coerce")
        df["account_name"] = df["account_name"].astype(str).str.strip()
        df["owner"]        = df["owner"].astype(str).str.strip()
        df["status"]       = df["status"].astype(str).str.strip().str.lower()
        return df.reset_index(drop=True)