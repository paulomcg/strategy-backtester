"""Buy-and-Hold WSOL — opens once on cycle 0 with all available cash.

Self-contained — no external imports beyond stdlib. Lives in the
backtester examples dir so demos work out of the box.
"""

from __future__ import annotations


def decide(state, market_data):
    if state.get("cycle_index", 0) != 0:
        return []
    for p in state.get("positions", []):
        if p.get("asset") == "WSOL" and float(p.get("qty", 0)) > 0:
            return []
    cash = float(state.get("cash_usd", 0))
    if cash <= 0:
        return []
    return [{"action": "buy", "asset": "WSOL", "amount_usd": cash}]
