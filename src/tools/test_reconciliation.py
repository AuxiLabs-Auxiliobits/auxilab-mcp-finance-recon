

import pytest

from bank_matcher import BankMatcher
from gl_reconciler import GLReconciler


# ──────────────────────────────────────────────────────────────
# 1. Happy path — BankMatcher
# ──────────────────────────────────────────────────────────────

def test_bank_matcher_happy_path_clean_match():
    """Two bank transactions with exact same-day, same-amount GL entries
    should match with HIGH confidence and reconcile to zero difference."""
    bank_csv = (
        "date,description,amount,reference\n"
        "2024-11-01,RENT PAYMENT,1000.00,BNK001\n"
        "2024-11-02,VENDOR PAYMENT,-500.00,BNK002\n"
    )
    gl_csv = (
        "date,description,amount,reference\n"
        "2024-11-01,RENT PAYMENT,1000.00,GL001\n"
        "2024-11-02,VENDOR PAYMENT,-500.00,GL002\n"
    )

    result = BankMatcher().match(bank_csv, gl_csv, opening_balance=0.0)
    summary = result["reconciliation_summary"]

    assert summary["matched_pairs"] == 2
    assert summary["unmatched_bank_count"] == 0
    assert summary["unmatched_gl_count"] == 0
    assert summary["match_rate_pct"] == 100.0
    assert summary["status"] == "RECONCILED"
    assert all(p["match_confidence"] == "HIGH" for p in result["matched_pairs"])


# ──────────────────────────────────────────────────────────────
# 2. Happy path — GLReconciler
# ──────────────────────────────────────────────────────────────

def test_gl_reconciler_happy_path_new_and_removed_entries():
    """Period B drops one prior-period entry and adds one new entry;
    the shared entry should land in common_entries."""
    period_a_csv = (
        "date,description,amount,reference\n"
        "2024-10-01,OFFICE SUPPLIES,-200.00,JNL001\n"
        "2024-10-05,LEGAL FEES,-300.00,JNL002\n"
    )
    period_b_csv = (
        "date,description,amount,reference\n"
        "2024-10-01,OFFICE SUPPLIES,-200.00,JNL001\n"
        "2024-11-10,CONSULTING FEE,150.00,JNL003\n"
    )

    result = GLReconciler().reconcile(period_a_csv, period_b_csv, account_name="Cash")
    stmt = result["reconciliation_statement"]

    assert stmt["common_items"] == 1
    assert stmt["new_entries_in_b"] == 1
    assert stmt["removed_from_b"] == 1
    assert result["new_entries"][0]["reference"] == "JNL003"
    assert result["removed_entries"][0]["reference"] == "JNL002"


# ──────────────────────────────────────────────────────────────
# 3. Edge case — BankMatcher ±3 day boundary
# ──────────────────────────────────────────────────────────────

def test_bank_matcher_date_tolerance_boundary():
    """A GL entry exactly 3 days from the bank date is inside the
    tolerance window and must match; one 4 days out must not."""
    bank_csv = (
        "date,description,amount,reference\n"
        "2024-11-01,WITHIN WINDOW,750.00,BNK010\n"
        "2024-11-01,OUTSIDE WINDOW,900.00,BNK011\n"
    )
    gl_csv = (
        "date,description,amount,reference\n"
        "2024-11-04,WITHIN WINDOW,750.00,GL010\n"   # exactly 3 days later
        "2024-11-05,OUTSIDE WINDOW,900.00,GL011\n"  # 4 days later
    )

    result = BankMatcher(date_tolerance_days=3).match(bank_csv, gl_csv)

    matched_refs = {p["bank_reference"] for p in result["matched_pairs"]}
    unmatched_refs = {u["reference"] for u in result["unmatched_bank_items"]}

    assert "BNK010" in matched_refs
    assert result["matched_pairs"][0]["date_diff_days"] == 3
    assert "BNK011" in unmatched_refs
    assert result["reconciliation_summary"]["unmatched_gl_count"] == 1


# ──────────────────────────────────────────────────────────────
# 4. Edge case — GLReconciler reversal detection
# ──────────────────────────────────────────────────────────────

def test_gl_reconciler_detects_reversal():
    """Same reference posted with a sign-flipped amount in period B
    should be flagged as a detected reversal."""
    period_a_csv = (
        "date,description,amount,reference\n"
        "2024-10-05,INSURANCE PREMIUM,500.00,JNL2024OCT0003\n"
    )
    period_b_csv = (
        "date,description,amount,reference\n"
        "2024-11-12,REVERSAL: INSURANCE PREMIUM,-500.00,JNL2024OCT0003\n"
    )

    result = GLReconciler().reconcile(period_a_csv, period_b_csv)

    assert result["reconciliation_statement"]["reversals_detected"] == 1
    rev = result["reversals"][0]
    assert rev["original_amount"] == 500.00
    assert rev["reversal_amount"] == -500.00


# ──────────────────────────────────────────────────────────────
# 5. Error condition — BankMatcher malformed CSV
# ──────────────────────────────────────────────────────────────

def test_bank_matcher_raises_on_missing_amount_column():
    """CSV missing the required 'amount' column should fail loudly
    (KeyError) rather than silently producing a wrong reconciliation."""
    bank_csv = (
        "date,description,reference\n"
        "2024-11-01,RENT PAYMENT,BNK001\n"
    )
    gl_csv = (
        "date,description,amount,reference\n"
        "2024-11-01,RENT PAYMENT,1000.00,GL001\n"
    )

    with pytest.raises(KeyError):
        BankMatcher().match(bank_csv, gl_csv)


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-v"]))