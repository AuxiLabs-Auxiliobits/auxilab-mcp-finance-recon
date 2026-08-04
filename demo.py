"""
demo.py — Full Month-End Close Demo
Simulates an AI agent receiving a close pack and running all 5 reconciliation tools.
Produces a Month-End Readiness Report at the end.

Run:
    python data/generate_test_data.py   # generate test CSVs first
    python demo.py
"""

import json
import sys
from pathlib import Path

# Allow running from project root
sys.path.insert(0, str(Path(__file__).parent / "src"))

from tools.bank_matcher import BankMatcher
from tools.gl_reconciler import GLReconciler
from tools.intercompany_checker import IntercompanyChecker
from tools.break_classifier import BreakClassifier
from tools.close_tracker import CloseTracker

DATA = Path(__file__).parent / "data" / "sample_data"

CLOSE_DEADLINE = "2024-11-30"
AS_OF_DATE     = "2024-11-29"   # demo date: 1 day before close


def read(filename: str) -> str:
    return (DATA / filename).read_text()


def section(title: str):
    print("\n" + "═" * 60)
    print(f"  {title}")
    print("═" * 60)


def print_json(data: dict):
    print(json.dumps(data, indent=2, default=str))


# ─────────────────────────────────────────────────────────────────

def run_demo():
    all_breaks = []

    # ── STEP 1: Bank Reconciliation ──────────────────────────────
    section("STEP 1 — Bank Statement Matching")

    bank_result = BankMatcher().match(
        bank_csv=read("bank_statement.csv"),
        gl_csv=read("gl_cash_ledger.csv"),
        opening_balance=500_000.00,
    )

    s = bank_result["reconciliation_summary"]
    print(f"  Transactions:  {s['bank_transactions']} bank / {s['gl_transactions']} GL")
    print(f"  Matched pairs: {s['matched_pairs']}  ({s['match_rate_pct']}%)")
    print(f"  Unmatched:     {s['unmatched_bank_count']} bank items, {s['unmatched_gl_count']} GL items")
    print(f"  Difference:    ${s['difference']:,.2f}")
    print(f"  Status:        {s['status']}")
    print(f"  Closing Bal:   ${s['closing_balance']:,.2f}")

    # Collect unmatched items as breaks
    for item in bank_result["unmatched_bank_items"] + bank_result["unmatched_gl_items"]:
        all_breaks.append({
            "reference":   item["reference"],
            "date":        item["date"],
            "description": item["description"],
            "amount":      item["amount"],
            "source":      item["source"],
        })


    # ── STEP 2: GL Account Reconciliation ────────────────────────
    section("STEP 2 — GL Account Reconciliation (Prior vs Current)")

    gl_result = GLReconciler().reconcile(
        period_a_csv=read("gl_prior_period.csv"),
        period_b_csv=read("gl_current_period.csv"),
        account_name="Accrued Liabilities — 2110",
    )

    rs = gl_result["reconciliation_statement"]
    print(f"  Prior period balance:    ${rs['period_a_balance']:,.2f}")
    print(f"  Current period balance:  ${rs['period_b_balance']:,.2f}")
    print(f"  Net movement:            ${rs['net_movement']:,.2f}")
    print(f"  New entries:             {rs['new_entries_in_b']}")
    print(f"  Removed entries:         {rs['removed_from_b']}")
    print(f"  Reversals detected:      {rs['reversals_detected']}")


    # ── STEP 3: Intercompany Check ───────────────────────────────
    section("STEP 3 — Intercompany Balance Check (Entity A vs Entity B)")

    ic_result = IntercompanyChecker().check(
        entity_a_csv=read("entity_a_ledger.csv"),
        entity_b_csv=read("entity_b_ledger.csv"),
        entity_a_name="Auxiliobits India Pvt Ltd",
        entity_b_name="Auxiliobits Singapore Pte Ltd",
        base_currency="USD",
    )

    ic = ic_result["summary"]
    print(f"  Entity A balance:     ${ic['entity_a_balance']:,.2f}")
    print(f"  Entity B (mirror):    ${ic['entity_b_mirror']:,.2f}")
    print(f"  Gross mismatch:       ${ic['gross_mismatch']:,.2f}")
    print(f"  FX component:         ${ic['currency_component']:,.2f}")
    print(f"  Timing component:     ${ic['timing_component']:,.2f}")
    print(f"  Risk:                 {ic['mismatch_risk']}")
    print(f"  Action:               {ic_result['mismatch_detail']['recommended_action']}")

    # Add IC mismatch to breaks
    for item in ic_result["entity_a_only"] + ic_result["entity_b_only"]:
        all_breaks.append({
            "reference":   item["reference"],
            "date":        item["date"],
            "description": "INTERCOMPANY MISMATCH: " + item["description"],
            "amount":      item["amount"],
            "source":      item["entity"],
        })


    # ── STEP 4: Break Classification ─────────────────────────────
    section("STEP 4 — Reconciliation Break Classification")

    # Merge auto-collected breaks with the pre-built sample breaks
    import csv, io
    sample_breaks = read("breaks_sample.csv")

    # Write collected breaks to inline CSV
    collected_csv_rows = ["reference,date,description,amount,source"]
    for b in all_breaks:
        collected_csv_rows.append(
            f"{b['reference']},{b['date']},\"{b['description']}\",{b['amount']},{b['source']}"
        )
    collected_csv = "\n".join(collected_csv_rows)

    # Classify the pre-built sample (more descriptive, better demo output)
    breaks_result = BreakClassifier().classify(breaks_csv=sample_breaks)

    bs = breaks_result["classification_summary"]
    print(f"  Total breaks:     {bs['total_breaks']}")
    print(f"  Total exposure:   ${bs['total_exposure']:,.2f}")
    print(f"  High priority:    {bs['high_priority']}")
    print(f"  By category:")
    for cat, cnt in bs["by_category"].items():
        print(f"    {cat:<28} {cnt}")


    # ── STEP 5: Month-End Close Tracker ──────────────────────────
    section("STEP 5 — Month-End Close Tracker")

    tracker_result = CloseTracker().track(
        tasks_csv=read("month_end_tasks.csv"),
        close_deadline=CLOSE_DEADLINE,
        as_of_date=AS_OF_DATE,
    )

    cs = tracker_result["close_status"]
    print(f"  Close deadline:   {cs['close_deadline']}  ({cs['days_to_deadline']} day(s) away)")
    print(f"  Completion:       {cs['completion_pct']}%  ({cs['complete']}/{cs['total_tasks']} tasks)")
    print(f"  In Progress:      {cs['in_progress']}")
    print(f"  Not Started:      {cs['not_started']}")
    print(f"  Overdue:          {cs['overdue']}")
    print(f"  ⚠  Risk Flag:     {cs['risk_flag']}")
    print(f"  Rationale:        {cs['risk_rationale']}")

    if tracker_result["overdue_items"]:
        print("\n  Overdue items:")
        for t in tracker_result["overdue_items"]:
            print(f"    [{t['days_overdue']}d] {t['account_name']} — {t['owner']}")


    # ── FINAL REPORT ─────────────────────────────────────────────
    section("MONTH-END READINESS REPORT")

    overall_risk = cs["risk_flag"]
    readiness = "NOT READY" if overall_risk in ("CRITICAL", "HIGH") else (
                "AT RISK"   if overall_risk == "MEDIUM" else "READY")

    print(f"""
  ╔══════════════════════════════════════════╗
  ║   MONTH-END CLOSE — READINESS SUMMARY   ║
  ╠══════════════════════════════════════════╣
  ║  Close deadline:  {CLOSE_DEADLINE}            ║
  ║  As of date:      {AS_OF_DATE}            ║
  ╠══════════════════════════════════════════╣
  ║  Bank Recon:      {s['status']:<23} ║
  ║  Breaks found:    {bs['total_breaks']:<23} ║
  ║  IC Mismatch:     ${ic['gross_mismatch']:>10,.2f}             ║
  ║  IC Risk:         {ic['mismatch_risk']:<23} ║
  ║  Close %:         {cs['completion_pct']:<23} ║
  ║  Overdue tasks:   {cs['overdue']:<23} ║
  ╠══════════════════════════════════════════╣
  ║  RISK RATING:     {overall_risk:<23} ║
  ║  CLOSE STATUS:    {readiness:<23} ║
  ╚══════════════════════════════════════════╝
""")


if __name__ == "__main__":
    run_demo()