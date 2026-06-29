"""
auxilab-mcp-finance-recon — MCP Server
Month-End Close Reconciliation Tools for Finance Shared Services
"""

import asyncio
import json
from typing import Any

import mcp.types as types
import mcp.server.stdio
from mcp.server import Server, NotificationOptions
from mcp.server.models import InitializationOptions

from tools.bank_matcher import BankMatcher
from tools.gl_reconciler import GLReconciler
from tools.intercompany_checker import IntercompanyChecker
from tools.break_classifier import BreakClassifier
from tools.close_tracker import CloseTracker

server = Server("auxilab-mcp-finance-recon")


# ─────────────────────────────────────────────
# Tool Registry
# ─────────────────────────────────────────────

@server.list_tools()
async def handle_list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="match_bank_statement",
            description=(
                "Match bank statement transactions against a GL cash account ledger "
                "using amount equality and date proximity (±3 days). "
                "Returns matched pairs, unmatched bank items, unmatched GL items, "
                "and a full reconciliation summary with closing balance."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "bank_csv": {
                        "type": "string",
                        "description": "Bank statement CSV: columns date, description, amount, reference"
                    },
                    "gl_csv": {
                        "type": "string",
                        "description": "GL cash ledger CSV: columns date, description, amount, reference"
                    },
                    "opening_balance": {
                        "type": "number",
                        "description": "Opening balance for the period (default 0)",
                        "default": 0
                    }
                },
                "required": ["bank_csv", "gl_csv"]
            }
        ),
        types.Tool(
            name="reconcile_gl_accounts",
            description=(
                "Compare two GL account extracts (prior vs current period, or two sub-ledgers). "
                "Identifies new entries, reversed entries, and items present in one extract "
                "but not the other. Returns a structured reconciliation statement."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "period_a_csv": {
                        "type": "string",
                        "description": "First GL extract CSV (prior period or sub-ledger A)"
                    },
                    "period_b_csv": {
                        "type": "string",
                        "description": "Second GL extract CSV (current period or sub-ledger B)"
                    },
                    "account_name": {
                        "type": "string",
                        "description": "Account name or number being reconciled",
                        "default": "Unknown Account"
                    }
                },
                "required": ["period_a_csv", "period_b_csv"]
            }
        ),
        types.Tool(
            name="check_intercompany_balances",
            description=(
                "Compare intercompany ledger entries between two entities for a shared account. "
                "Identifies balance mismatches, flags currency conversion differences separately, "
                "and returns a structured mismatch report."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "entity_a_csv": {
                        "type": "string",
                        "description": "Entity A ledger CSV (typically recording the receivable)"
                    },
                    "entity_b_csv": {
                        "type": "string",
                        "description": "Entity B ledger CSV (typically recording the payable)"
                    },
                    "entity_a_name": {"type": "string", "default": "Entity A"},
                    "entity_b_name": {"type": "string", "default": "Entity B"},
                    "base_currency": {
                        "type": "string",
                        "description": "Reporting currency for comparison",
                        "default": "USD"
                    }
                },
                "required": ["entity_a_csv", "entity_b_csv"]
            }
        ),
        types.Tool(
            name="classify_reconciliation_breaks",
            description=(
                "Classify a list of unreconciled items by likely cause: "
                "Timing Difference, Missing Entry, Duplicate Posting, "
                "Currency Rounding, Intercompany Mismatch, or Unknown. "
                "Each item receives a recommended next action."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "breaks_csv": {
                        "type": "string",
                        "description": "CSV of breaks: columns reference, date, description, amount, source"
                    }
                },
                "required": ["breaks_csv"]
            }
        ),
        types.Tool(
            name="track_month_end_close",
            description=(
                "Track month-end close progress across all reconciliation tasks. "
                "Returns completion %, overdue items, not-started items, "
                "and a HIGH/MEDIUM/LOW risk flag based on deadline proximity and outstanding work."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "tasks_csv": {
                        "type": "string",
                        "description": "CSV of tasks: account_name, owner, status, due_date"
                    },
                    "close_deadline": {
                        "type": "string",
                        "description": "Hard close deadline (YYYY-MM-DD)"
                    },
                    "as_of_date": {
                        "type": "string",
                        "description": "Evaluation date for overdue logic (YYYY-MM-DD, defaults to today)"
                    }
                },
                "required": ["tasks_csv", "close_deadline"]
            }
        )
    ]


# ─────────────────────────────────────────────
# Tool Dispatch
# ─────────────────────────────────────────────

@server.call_tool()
async def handle_call_tool(
    name: str, arguments: dict[str, Any]
) -> list[types.TextContent]:
    try:
        if name == "match_bank_statement":
            result = BankMatcher().match(
                bank_csv=arguments["bank_csv"],
                gl_csv=arguments["gl_csv"],
                opening_balance=float(arguments.get("opening_balance", 0))
            )

        elif name == "reconcile_gl_accounts":
            result = GLReconciler().reconcile(
                period_a_csv=arguments["period_a_csv"],
                period_b_csv=arguments["period_b_csv"],
                account_name=arguments.get("account_name", "Unknown Account")
            )

        elif name == "check_intercompany_balances":
            result = IntercompanyChecker().check(
                entity_a_csv=arguments["entity_a_csv"],
                entity_b_csv=arguments["entity_b_csv"],
                entity_a_name=arguments.get("entity_a_name", "Entity A"),
                entity_b_name=arguments.get("entity_b_name", "Entity B"),
                base_currency=arguments.get("base_currency", "USD")
            )

        elif name == "classify_reconciliation_breaks":
            result = BreakClassifier().classify(
                breaks_csv=arguments["breaks_csv"]
            )

        elif name == "track_month_end_close":
            result = CloseTracker().track(
                tasks_csv=arguments["tasks_csv"],
                close_deadline=arguments["close_deadline"],
                as_of_date=arguments.get("as_of_date")
            )

        else:
            result = {"error": f"Unknown tool: {name}"}

        return [types.TextContent(
            type="text",
            text=json.dumps(result, indent=2, default=str)
        )]

    except Exception as exc:
        return [types.TextContent(
            type="text",
            text=json.dumps({"error": str(exc), "tool": name}, indent=2)
        )]


# ─────────────────────────────────────────────
# Server Boot
# ─────────────────────────────────────────────

async def main():
    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="auxilab-mcp-finance-recon",
                server_version="0.1.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={}
                )
            )
        )


if __name__ == "__main__":
    asyncio.run(main())