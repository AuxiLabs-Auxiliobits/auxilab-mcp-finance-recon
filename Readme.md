# auxilab-mcp-finance-recon

**MCP Server for Month-End Close Reconciliation**  
Finance Shared Services · GBS/SSC · Auxiliobits

> Automate the most manual, error-prone activities in a shared services team:  
> bank reconciliation, GL close, intercompany matching, and month-end close tracking.

---

## What it does

| MCP Tool | Description |
|---|---|
| `match_bank_statement` | Match bank CSV vs GL cash ledger — ±3 day date proximity, exact amount |
| `reconcile_gl_accounts` | Compare prior vs current GL extract — new entries, reversals, variances |
| `check_intercompany_balances` | Entity A vs Entity B — gross mismatch, FX component, risk flag |
| `classify_reconciliation_breaks` | Rules-based break classification with recommended next actions |
| `track_month_end_close` | 12-task close tracker with overdue detection and risk rating |

---

## Quick Start

### 1. Install

```bash
git clone https://github.com/auxiliobits/auxilab-mcp-finance-recon
cd auxilab-mcp-finance-recon
pip install -e ".[dev]"
```

### 2. Generate test data

```bash
python data/generate_test_data.py
```

This creates `data/sample_data/` with 7 synthetic CSV files — no real data required.

### 3. Run the standalone demo

```bash
python demo.py
```

Expected output: full 5-step reconciliation flow ending with a Month-End Readiness Report.

### 4. Start the MCP server (for Claude Desktop / agent use)

```bash
python src/server.py
```

---

## MCP Server Config (claude_desktop_config.json)

```json
{
  "mcpServers": {
    "finance-recon": {
      "command": "python",
      "args": ["/path/to/auxilab-mcp-finance-recon/src/server.py"]
    }
  }
}
```

---

## Tool Reference

### `match_bank_statement`

```json
{
  "bank_csv": "<CSV string>",
  "gl_csv": "<CSV string>",
  "opening_balance": 500000.00
}
```

**Returns:** `reconciliation_summary`, `matched_pairs`, `unmatched_bank_items`, `unmatched_gl_items`

**Matching logic:**
- Amount match: exact within ±$0.01
- Date proximity: ±3 calendar days
- Tiebreaker: rapidfuzz `token_sort_ratio` on description

---

### `reconcile_gl_accounts`

```json
{
  "period_a_csv": "<prior period CSV>",
  "period_b_csv": "<current period CSV>",
  "account_name": "Accrued Liabilities — 2110"
}
```

**Returns:** `reconciliation_statement`, `new_entries`, `removed_entries`, `reversals`, `common_entries`

---

### `check_intercompany_balances`

```json
{
  "entity_a_csv": "<Entity A ledger CSV>",
  "entity_b_csv": "<Entity B ledger CSV>",
  "entity_a_name": "Auxiliobits India",
  "entity_b_name": "Auxiliobits Singapore",
  "base_currency": "USD"
}
```

**Returns:** `summary` (with `mismatch_risk`: NONE/LOW/MEDIUM/HIGH/CRITICAL), `matched_transactions`, entity-only lists, `mismatch_detail`

**Demo scenario:** Entity A = $125,000 receivable · Entity B = $123,500 payable → $1,500 mismatch, flagged HIGH

---

### `classify_reconciliation_breaks`

```json
{
  "breaks_csv": "<unreconciled items CSV>"
}
```

CSV columns: `reference, date, description, amount, source`

**Classification categories:**
| Category | Rule |
|---|---|
| Timing Difference | Keywords: transit, outstanding, cut-off, clearing |
| Missing Entry | Keywords: missing, not posted, unposted |
| Duplicate Posting | Keywords: duplicate, double post, twice |
| Currency Rounding | Amount ≤ $10, or FX/forex keywords |
| Intercompany Mismatch | Keywords: interco, entity, subsidiary |
| Unknown | No rule matched — escalate |

---

### `track_month_end_close`

```json
{
  "tasks_csv": "<tasks CSV>",
  "close_deadline": "2024-11-30",
  "as_of_date": "2024-11-29"
}
```

CSV columns: `account_name, owner, status, due_date`

Valid statuses: `complete`, `in progress`, `not started`, `overdue`, `on hold`

**Risk logic:**
- `CRITICAL`: deadline ≤ 1 day with outstanding tasks, or deadline passed
- `HIGH`: deadline ≤ 2 days with >3 outstanding, or ≥3 overdue tasks
- `MEDIUM`: completion < 75% or any overdue
- `LOW`: on track

---

## Project Structure

```
auxilab-mcp-finance-recon/
├── src/
│   ├── server.py               # MCP server — tool registry + dispatch
│   └── tools/
│       ├── __init__.py
│       ├── bank_matcher.py     # Bank ↔ GL matching (Pandas + rapidfuzz)
│       ├── gl_reconciler.py    # Prior vs current GL extract diff
│       ├── intercompany_checker.py  # Entity A vs Entity B
│       ├── break_classifier.py # Rules-based break classifier
│       └── close_tracker.py   # Month-end task tracker
├── data/
│   ├── generate_test_data.py  # Synthetic CSV generator
│   └── sample_data/           # Generated CSVs (gitignored)
├── tests/
│   └── test_tools.py
├── demo.py                    # Full 5-step demo runner
├── pyproject.toml
└── README.md
```

---

## Tech Stack

| Component | Library |
|---|---|
| MCP protocol | `mcp` Python SDK >= 1.0.0 |
| Matching logic | `pandas` >= 2.0, `numpy` |
| Fuzzy description matching | `rapidfuzz` (falls back to `difflib`) |
| CSV parsing | `pandas.read_csv` |
| Break classification | Rules-based (regex) — no LLM required |

---

## Demo Data Summary

| File | Rows | Notes |
|---|---|---|
| `bank_statement.csv` | 50 | Unique amounts, full month |
| `gl_cash_ledger.csv` | 48 | 45 match bank (±1-2 day drift), 3 GL-only timing items |
| `gl_prior_period.csv` | 20 | October GL extract |
| `gl_current_period.csv` | 25 | 15 carry-forward + 8 new + 2 reversals |
| `entity_a_ledger.csv` | 3 | $125,000 receivable |
| `entity_b_ledger.csv` | 3 | $123,500 payable — $1,500 mismatch |
| `month_end_tasks.csv` | 12 | 4 complete, 3 overdue, deadline in 1 day → HIGH risk |
| `breaks_sample.csv` | 8 | Covers all 6 break categories |

---

## License

MIT · Built for the Auxiliobits Hackathon — Financial Reconciliation Pillar