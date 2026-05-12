"""Weekly DCA into WSOL — buys $50 every 7 cycles.

Assumes daily bars (--bar 1D). Adjust DCA_EVERY_N_CYCLES if your
backtest uses a different cadence. Self-contained — no PM helpers
import so the file works anywhere.
"""

from __future__ import annotations

ASSET = "WSOL"
DCA_AMOUNT_USD = 50.0
DCA_EVERY_N_CYCLES = 7   # ~weekly on a daily bar feed


def decide(state, market_data):
    cycle = int(state.get("cycle_index", 0))
    if cycle % DCA_EVERY_N_CYCLES != 0:
        return []
    if float(state.get("cash_usd", 0)) < DCA_AMOUNT_USD:
        return []
    return [{"action": "buy", "asset": ASSET, "amount_usd": DCA_AMOUNT_USD}]
