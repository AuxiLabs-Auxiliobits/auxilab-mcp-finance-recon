"""
Tests for auxilab-mcp-finance-recon tools.
Run: pytest tests/test_tools.py -v
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import pytest
from tools.bank_matcher import BankMatcher
from tools.gl_reconciler import GLReconciler
from tools.intercompany_checker import IntercompanyChecker
from tools.break_classifier import BreakClassifier
from tools.close_tracker import CloseTracker


# ── Fixtures ──────────────────────────────────────────────────────

BANK_CSV = """date,description,amount,reference
2024-11-05,VENDOR PAYMENT - ACME,10000.00,BNK001
2024-11-10,PAYROLL DISBURSEMENT,-25000.00,BNK002
2024-11-15,UTILITY PAYMENT,-1200.00,BNK003
2024-11-28,TIMING ITEM BANK,5000.00,BNK004
"""

GL_CSV = """date,description,amount,reference
2024-11-05,VENDOR PAYMENT - ACME,10000.00,GL001
2024-11-11,PAYROLL DISBURSEMENT,-25000.00,GL002
2024-11-15,UTILITY PAYMENT,-1200.00,GL003
"""

IC_A_CSV = """date,description,amount,reference
2024-11-05,IC RECEIVABLE - SVC FEES,50000.00,IC-A-001
2024-11-10,IC RECEIVABLE - MGMT,45000.00,IC-A-002
2024-11-18,IC RECEIVABLE - ROYALTY,30000.00,IC-A-003
"""

IC_B_CSV = """date,description,amount,reference
2024-11-05,IC PAYABLE - SVC FEES,-50000.00,IC-B-001
2024-11-10,IC PAYABLE - MGMT,-45000.00,IC-B-002
2024-11-18,IC PAYABLE - ROYALTY,-28500.00,IC-B-003
"""

BREAKS_CSV = """reference,date,description,amount,source
BRK-001,2024-11-28,TIMING DIFFERENCE TRANSIT ITEM,-3250.00,BANK
BRK-002,2024-11-27,DUPLICATE POSTING ACME,8500.00,GL
BRK-003,2024-11-25,INTERCOMPANY MISMATCH ENTITY B,-1500.00,GL
BRK-004,2024-11-22,FX ROUNDING USD/EUR,-4.73,GL
BRK-005,2024-11-20,MISSING ENTRY NOT POSTED,12000.00,BANK
"""

TASKS_CSV = """account_name,owner,status,due_date
Cash,Alice,complete,2024-11-26
AR,Bob,complete,2024-11-27
AP,Carol,in progress,2024-11-29
Accruals,Dave,not started,2024-11-30
Bank Recon USD,Eve,overdue,2024-11-25
Bank Recon EUR,Frank,overdue,2024-11-24
"""


# ── Bank Matcher Tests ────────────────────────────────────────────

class TestBankMatcher:

    def test_match_count(self):
        result = BankMatcher().match(BANK_CSV, GL_CSV, opening_balance=100_000)
        s = result["reconciliation_summary"]
        assert s["matched_pairs"] == 3
        assert s["unmatched_bank_count"] == 1    # BNK004 timing item
        assert s["unmatched_gl_count"] == 0

    def test_summary_keys(self):
        result = BankMatcher().match(BANK_CSV, GL_CSV)
        assert "reconciliation_summary" in result
        assert "matched_pairs" in result
        assert "unmatched_bank_items" in result
        assert "unmatched_gl_items" in result

    def test_closing_balance(self):
        result = BankMatcher().match(BANK_CSV, GL_CSV, opening_balance=50_000)
        bank_total = 10_000 + (-25_000) + (-1_200) + 5_000   # = -11_200
        expected_closing = 50_000 + bank_total
        assert result["reconciliation_summary"]["closing_balance"] == expected_closing

    def test_match_confidence_levels(self):
        result = BankMatcher().match(BANK_CSV, GL_CSV)
        confidences = {p["match_confidence"] for p in result["matched_pairs"]}
        assert confidences.issubset({"HIGH", "MEDIUM", "LOW"})

    def test_status_unreconciled(self):
        result = BankMatcher().match(BANK_CSV, GL_CSV)
        # Bank has $5000 timing item not in GL → not reconciled
        assert result["reconciliation_summary"]["status"] == "UNRECONCILED"


# ── GL Reconciler Tests ───────────────────────────────────────────

PRIOR_CSV = """date,description,amount,reference
2024-10-05,ACCRUAL ENTRY,-5000.00,JNL2024OCT001
2024-10-10,RENT ACCRUAL,-3000.00,JNL2024OCT002
2024-10-15,INSURANCE,-1200.00,JNL2024OCT003
"""

CURRENT_CSV = """date,description,amount,reference
2024-10-05,ACCRUAL ENTRY,-5000.00,JNL2024OCT001
2024-11-01,NEW EXPENSE,-8000.00,JNL2024NOV001
2024-11-03,REVERSAL: RENT ACCRUAL,3000.00,JNL2024OCT002
"""

class TestGLReconciler:

    def test_new_entries(self):
        result = GLReconciler().reconcile(PRIOR_CSV, CURRENT_CSV)
        assert len(result["new_entries"]) == 1
        assert result["new_entries"][0]["reference"] == "JNL2024NOV001"

    def test_removed_entries(self):
        result = GLReconciler().reconcile(PRIOR_CSV, CURRENT_CSV)
        # JNL2024OCT003 (insurance) not in current
        assert len(result["removed_entries"]) == 1

    def test_reversal_detection(self):
        result = GLReconciler().reconcile(PRIOR_CSV, CURRENT_CSV)
        assert len(result["reversals"]) == 1
        assert result["reversals"][0]["original_amount"] == -3000.00

    def test_summary_keys(self):
        result = GLReconciler().reconcile(PRIOR_CSV, CURRENT_CSV)
        s = result["reconciliation_statement"]
        assert "period_a_balance" in s
        assert "period_b_balance" in s
        assert "net_movement" in s


# ── Intercompany Tests ────────────────────────────────────────────

class TestIntercompanyChecker:

    def test_mismatch_detected(self):
        result = IntercompanyChecker().check(IC_A_CSV, IC_B_CSV)
        assert result["summary"]["status"] == "MISMATCH"
        assert result["summary"]["gross_mismatch"] == 1500.0

    def test_risk_level(self):
        result = IntercompanyChecker().check(IC_A_CSV, IC_B_CSV)
        assert result["summary"]["mismatch_risk"] in ("LOW", "MEDIUM", "HIGH", "CRITICAL")

    def test_entity_balances(self):
        result = IntercompanyChecker().check(IC_A_CSV, IC_B_CSV)
        assert result["summary"]["entity_a_balance"] == 125_000.0
        assert result["summary"]["entity_b_balance_raw"] == -123_500.0

    def test_recommended_action_present(self):
        result = IntercompanyChecker().check(IC_A_CSV, IC_B_CSV)
        assert "recommended_action" in result["mismatch_detail"]
        assert len(result["mismatch_detail"]["recommended_action"]) > 10


# ── Break Classifier Tests ────────────────────────────────────────

class TestBreakClassifier:

    def test_timing_classification(self):
        csv = "reference,date,description,amount,source\nBRK-1,2024-11-28,TRANSIT ITEM,-100.00,BANK"
        result = BreakClassifier().classify(csv)
        assert result["classified_breaks"][0]["category"] == "Timing Difference"

    def test_duplicate_classification(self):
        csv = "reference,date,description,amount,source\nBRK-1,2024-11-28,DUPLICATE POSTING,5000.00,GL"
        result = BreakClassifier().classify(csv)
        assert result["classified_breaks"][0]["category"] == "Duplicate Posting"

    def test_fx_rounding_small_amount(self):
        csv = "reference,date,description,amount,source\nBRK-1,2024-11-28,SOME VENDOR,3.50,GL"
        result = BreakClassifier().classify(csv)
        assert result["classified_breaks"][0]["category"] == "Currency Rounding"

    def test_intercompany_classification(self):
        csv = "reference,date,description,amount,source\nBRK-1,2024-11-28,INTERCOMPANY ENTITY B,-1500.00,GL"
        result = BreakClassifier().classify(csv)
        assert result["classified_breaks"][0]["category"] == "Intercompany Mismatch"

    def test_summary_totals(self):
        result = BreakClassifier().classify(BREAKS_CSV)
        s = result["classification_summary"]
        assert s["total_breaks"] == 5
        assert s["total_exposure"] > 0
        assert "by_category" in s


# ── Close Tracker Tests ───────────────────────────────────────────

class TestCloseTracker:

    def test_completion_pct(self):
        result = CloseTracker().track(TASKS_CSV, "2024-11-30", "2024-11-29")
        cs = result["close_status"]
        assert cs["complete"] == 2
        assert cs["total_tasks"] == 6
        assert cs["completion_pct"] == pytest.approx(33.3, abs=0.2)

    def test_overdue_detection(self):
        result = CloseTracker().track(TASKS_CSV, "2024-11-30", "2024-11-29")
        assert result["close_status"]["overdue"] == 2

    def test_high_risk_flag(self):
        result = CloseTracker().track(TASKS_CSV, "2024-11-30", "2024-11-29")
        assert result["close_status"]["risk_flag"] in ("HIGH", "CRITICAL")

    def test_overdue_items_have_days(self):
        result = CloseTracker().track(TASKS_CSV, "2024-11-30", "2024-11-29")
        for item in result["overdue_items"]:
            assert item["days_overdue"] > 0

    def test_deadline_passed_is_critical(self):
        result = CloseTracker().track(TASKS_CSV, "2024-11-01", "2024-11-29")
        assert result["close_status"]["risk_flag"] == "CRITICAL"