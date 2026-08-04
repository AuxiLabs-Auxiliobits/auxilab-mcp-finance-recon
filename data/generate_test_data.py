"""
Test Data Generator
Produces all synthetic CSV files needed for the demo flow:
  - bank_statement.csv       (50 rows)
  - gl_cash_ledger.csv       (48 rows, 45 match bank)
  - gl_prior_period.csv      (prior month GL extract)
  - gl_current_period.csv    (current month GL extract, with new/reversed entries)
  - entity_a_ledger.csv      (intercompany receivable — $125,000)
  - entity_b_ledger.csv      (intercompany payable — $123,500, $1,500 mismatch)
  - month_end_tasks.csv      (12 tasks: 4 complete, 3 overdue)
  - breaks_sample.csv        (unreconciled items for classifier demo)
"""

import pandas as pd
import numpy as np
import random
import os
from datetime import datetime, timedelta
from pathlib import Path

random.seed(42)
np.random.seed(42)

OUT_DIR = Path(__file__).parent / "sample_data"
OUT_DIR.mkdir(exist_ok=True)

PERIOD_START = datetime(2024, 11, 1)
PERIOD_END   = datetime(2024, 11, 30)


# ── Helpers ────────────────────────────────────────────────────────

def rand_date(start=PERIOD_START, end=PERIOD_END):
    delta = (end - start).days
    return start + timedelta(days=random.randint(0, delta))

def rand_amount(lo=-80_000, hi=80_000, nonzero=True):
    v = round(random.uniform(lo, hi), 2)
    return v if not nonzero or abs(v) > 0.01 else rand_amount(lo, hi)

VENDOR_DESCS = [
    "VENDOR PAYMENT - ACME SUPPLIES",
    "PAYROLL DISBURSEMENT",
    "UTILITY PAYMENT - ENERGY CO",
    "OFFICE SUPPLIES - STAPLES",
    "TRAVEL REIMBURSEMENT",
    "SOFTWARE LICENSE - ADOBE",
    "CONSULTING FEE - KPMG",
    "INSURANCE PREMIUM - MARSH",
    "RENT PAYMENT - PROPERTY MGT",
    "EQUIPMENT LEASE - DELL",
    "MAINTENANCE SERVICE - OTIS",
    "MARKETING EXPENSE - WPP",
    "LEGAL FEES - LINKLATERS",
    "AUDIT SERVICES - DELOITTE",
    "TRAINING EXPENSE - COURSERA",
    "BANK CHARGES",
    "INTEREST INCOME",
    "DIVIDEND RECEIPT",
    "LOAN REPAYMENT",
    "INTERCOMPANY TRANSFER",
]


# ── 1. Bank Statement + GL Cash Ledger ────────────────────────────

def generate_bank_and_gl():
    # Build 50 bank rows
    bank_rows = []
    amounts_used = set()
    for i in range(50):
        while True:
            amt = rand_amount()
            if amt not in amounts_used:
                amounts_used.add(amt)
                break
        bank_rows.append({
            "date":        rand_date().strftime("%Y-%m-%d"),
            "description": random.choice(VENDOR_DESCS) + f" #{i+1:04d}",
            "amount":      amt,
            "reference":   f"BNK2024{i+1:04d}",
        })
    bank_df = pd.DataFrame(bank_rows)

    # GL: 45 of the 50 bank items (with ±1-2 day date drift), + 3 GL-only items
    matched_idx = random.sample(range(50), 45)
    gl_rows = []

    for i in matched_idx:
        b = bank_rows[i]
        offset = random.choice([-2, -1, 0, 0, 0, 1, 2])  # mostly same-day
        gl_date = (datetime.strptime(b["date"], "%Y-%m-%d") + timedelta(days=offset))
        gl_rows.append({
            "date":        gl_date.strftime("%Y-%m-%d"),
            "description": b["description"],    # same description
            "amount":      b["amount"],
            "reference":   "GL" + b["reference"][3:],
        })

    # 3 GL-only timing items
    for j in range(3):
        gl_rows.append({
            "date":        (PERIOD_END - timedelta(days=j)).strftime("%Y-%m-%d"),
            "description": f"LATE POSTING - TIMING ITEM {j+1:02d}",
            "amount":      round(random.uniform(-5_000, 5_000), 2),
            "reference":   f"GL9999{j+1:04d}",
        })

    gl_df = pd.DataFrame(gl_rows)

    bank_df.to_csv(OUT_DIR / "bank_statement.csv", index=False)
    gl_df.to_csv(OUT_DIR / "gl_cash_ledger.csv", index=False)
    print(f"[✓] bank_statement.csv       ({len(bank_df)} rows)")
    print(f"[✓] gl_cash_ledger.csv       ({len(gl_df)} rows, 45 matched + 3 GL-only)")


# ── 2. GL Prior vs Current Period ─────────────────────────────────

def generate_gl_period_extracts():
    prior_rows = []
    for i in range(20):
        prior_rows.append({
            "date":        rand_date(PERIOD_START - timedelta(30), PERIOD_END - timedelta(30)).strftime("%Y-%m-%d"),
            "description": random.choice(VENDOR_DESCS) + f" OCT#{i+1:04d}",
            "amount":      rand_amount(-30_000, 30_000),
            "reference":   f"JNL2024OCT{i+1:04d}",
        })

    # Current = 15 of prior (carried forward) + 8 new + 2 reversals
    current_rows = [r.copy() for r in random.sample(prior_rows, 15)]

    for i in range(8):
        current_rows.append({
            "date":        rand_date().strftime("%Y-%m-%d"),
            "description": random.choice(VENDOR_DESCS) + f" NOV#{i+1:04d}",
            "amount":      rand_amount(-30_000, 30_000),
            "reference":   f"JNL2024NOV{i+1:04d}",
        })

    # 2 reversals — same ref as prior, opposite sign
    for rev_src in random.sample(prior_rows, 2):
        current_rows.append({
            "date":        rand_date().strftime("%Y-%m-%d"),
            "description": "REVERSAL: " + rev_src["description"],
            "amount":      -rev_src["amount"],
            "reference":   rev_src["reference"],    # same ref triggers reversal detection
        })

    pd.DataFrame(prior_rows).to_csv(OUT_DIR / "gl_prior_period.csv", index=False)
    pd.DataFrame(current_rows).to_csv(OUT_DIR / "gl_current_period.csv", index=False)
    print(f"[✓] gl_prior_period.csv      ({len(prior_rows)} rows)")
    print(f"[✓] gl_current_period.csv    ({len(current_rows)} rows, 8 new + 2 reversals)")


# ── 3. Intercompany ───────────────────────────────────────────────

def generate_intercompany():
    # Entity A: sum of receivables = $125,000
    ic_entries_a = [
        ("2024-11-05", "IC RECEIVABLE - ENTITY B - SVC FEES",    50_000.00, "IC-A-001"),
        ("2024-11-10", "IC RECEIVABLE - ENTITY B - MGMT CHARGE", 45_000.00, "IC-A-002"),
        ("2024-11-18", "IC RECEIVABLE - ENTITY B - ROYALTY",     30_000.00, "IC-A-003"),
    ]
    # Entity B: sum of payables = $123,500 → $1,500 mismatch
    ic_entries_b = [
        ("2024-11-05", "IC PAYABLE - ENTITY A - SVC FEES",      -50_000.00, "IC-B-001"),
        ("2024-11-11", "IC PAYABLE - ENTITY A - MGMT CHARGE",   -45_000.00, "IC-B-002"),  # 1-day timing diff
        ("2024-11-18", "IC PAYABLE - ENTITY A - ROYALTY",       -28_500.00, "IC-B-003"),  # $1,500 mismatch here
    ]

    entity_a = pd.DataFrame(ic_entries_a, columns=["date", "description", "amount", "reference"])
    entity_b = pd.DataFrame(ic_entries_b, columns=["date", "description", "amount", "reference"])

    entity_a.to_csv(OUT_DIR / "entity_a_ledger.csv", index=False)
    entity_b.to_csv(OUT_DIR / "entity_b_ledger.csv", index=False)
    print(f"[✓] entity_a_ledger.csv      (Entity A receivable total: $125,000)")
    print(f"[✓] entity_b_ledger.csv      (Entity B payable total: $123,500 — $1,500 mismatch)")


# ── 4. Month-End Close Tasks ──────────────────────────────────────

def generate_close_tasks():
    today = datetime(2024, 11, 29)   # 1 day before close deadline

    tasks = [
        # account_name,                   owner,            status,       due_date
        ("Cash - Main Account",          "Priya Sharma",   "complete",   "2024-11-26"),
        ("Accounts Receivable",          "Rajan Mehta",    "complete",   "2024-11-27"),
        ("Prepaid Expenses",             "Anita Roy",      "complete",   "2024-11-27"),
        ("Fixed Assets",                 "Deepak Nair",    "complete",   "2024-11-28"),
        ("Accounts Payable",             "Neha Gupta",     "in progress","2024-11-29"),
        ("Accrued Liabilities",          "Suresh Kumar",   "in progress","2024-11-29"),
        ("Intercompany - Entity B",      "Kavya Pillai",   "in progress","2024-11-29"),
        ("Revenue Recognition",          "Arjun Singh",    "not started","2024-11-30"),
        ("Tax Payable",                  "Meera Iyer",     "not started","2024-11-30"),
        ("Bank Reconciliation - USD",    "Priya Sharma",   "overdue",    "2024-11-25"),  # 4 days overdue
        ("Bank Reconciliation - EUR",    "Rajan Mehta",    "overdue",    "2024-11-26"),  # 3 days overdue
        ("Payroll Clearing",             "Sunita Rao",     "overdue",    "2024-11-24"),  # 5 days overdue
    ]

    df = pd.DataFrame(tasks, columns=["account_name", "owner", "status", "due_date"])
    df.to_csv(OUT_DIR / "month_end_tasks.csv", index=False)
    print(f"[✓] month_end_tasks.csv      (12 tasks: 4 complete, 3 overdue, deadline 2024-11-30)")


# ── 5. Sample Breaks for Classifier ──────────────────────────────

def generate_breaks():
    breaks = [
        ("BRK-001", "2024-11-28", "LATE POSTING - TIMING ITEM",             -3_250.00, "BANK"),
        ("BRK-002", "2024-11-27", "DUPLICATE POSTING - ACME SUPPLIES",       8_500.00, "GL"),
        ("BRK-003", "2024-11-25", "IC PAYABLE - ENTITY A ROYALTY MISMATCH", -1_500.00, "GL"),
        ("BRK-004", "2024-11-22", "FX ROUNDING DIFFERENCE USD/INR",             -4.73, "GL"),
        ("BRK-005", "2024-11-20", "MISSING GL ENTRY - INSURANCE PREMIUM",   12_000.00, "BANK"),
        ("BRK-006", "2024-11-29", "TRANSIT ITEM - CLEARING ACCOUNT",        -2_100.00, "BANK"),
        ("BRK-007", "2024-11-18", "VENDOR CREDIT NOTE NOT POSTED",           5_600.00, "GL"),
        ("BRK-008", "2024-11-15", "CURRENCY REVALUATION DIFF EUR",              -8.22, "GL"),
    ]

    df = pd.DataFrame(breaks, columns=["reference", "date", "description", "amount", "source"])
    df.to_csv(OUT_DIR / "breaks_sample.csv", index=False)
    print(f"[✓] breaks_sample.csv        ({len(breaks)} breaks for classifier demo)")


# ── Main ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 55)
    print("  Generating auxilab-mcp-finance-recon test data")
    print("=" * 55)
    generate_bank_and_gl()
    generate_gl_period_extracts()
    generate_intercompany()
    generate_close_tasks()
    generate_breaks()
    print("=" * 55)
    print(f"  All files written to: {OUT_DIR.resolve()}")
    print("=" * 55)