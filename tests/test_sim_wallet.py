"""Tests for the simulated wallet."""

from __future__ import annotations

import pytest

from scripts.sim_wallet import SimulatedWallet, TokenPosition


def _buy_fill(asset="WSOL", qty=1.0, price=100.0, fees=0.5, address=""):
    return {
        "ok": True, "action": "buy", "asset": asset,
        "qty_swapped": qty, "fill_price_usd": price,
        "gross_proceeds_usd": -qty * price,   # negative for buy outflow
        "fees_usd": fees, "slippage_usd": 0.0,
        "realized_pnl_usd": 0.0,
        "address": address,
    }


def _sell_fill(asset="WSOL", qty=1.0, price=100.0, fees=0.5, realized=0.0):
    return {
        "ok": True, "action": "sell", "asset": asset,
        "qty_swapped": qty, "fill_price_usd": price,
        "gross_proceeds_usd": qty * price,
        "fees_usd": fees, "slippage_usd": 0.0,
        "realized_pnl_usd": realized,
    }


# ---------------------------------------------------------------------------
# Construction + initial state
# ---------------------------------------------------------------------------


class TestInitial:
    def test_starts_with_cash_only(self):
        w = SimulatedWallet.with_initial_cash(1000)
        snap = w.to_wallet_snapshot(ts_utc="2026-01-01T00:00:00Z")
        assert snap["tokens"] == [
            {"asset": "USDC", "chain": "solana",
             "address": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
             "qty": 1000.0, "mark_price_usd": 1.0, "value_usd": 1000.0}
        ]
        assert w.total_equity_usd == 1000.0
        assert w.to_pnl_snapshot() == {}


# ---------------------------------------------------------------------------
# Buys
# ---------------------------------------------------------------------------


class TestBuys:
    def test_buy_decrements_cash_and_creates_position(self):
        w = SimulatedWallet.with_initial_cash(1000)
        w.apply_fill(_buy_fill(asset="WSOL", qty=2.0, price=100.0, fees=0.6,
                                address="So11"))
        assert w.cash_usd == pytest.approx(1000 - 200 - 0.6, abs=1e-6)
        assert "WSOL" in w.positions
        pos = w.positions["WSOL"]
        assert pos.qty == 2.0
        assert pos.cost_basis_usd == 200.0
        assert pos.address == "So11"

    def test_subsequent_buy_aggregates(self):
        w = SimulatedWallet.with_initial_cash(1000)
        w.apply_fill(_buy_fill(qty=1, price=100, fees=0))
        w.apply_fill(_buy_fill(qty=1, price=120, fees=0))
        pos = w.positions["WSOL"]
        assert pos.qty == 2.0
        assert pos.cost_basis_usd == 220.0  # 100 + 120

    def test_buy_creates_position_with_address(self):
        w = SimulatedWallet.with_initial_cash(1000)
        w.apply_fill(_buy_fill(qty=1, price=100, address="X-addr"))
        snap = w.to_wallet_snapshot()
        wsol = next(t for t in snap["tokens"] if t["asset"] == "WSOL")
        assert wsol["address"] == "X-addr"


# ---------------------------------------------------------------------------
# Sells
# ---------------------------------------------------------------------------


class TestSells:
    def test_sell_increments_cash_and_decrements_qty(self):
        w = SimulatedWallet.with_initial_cash(1000)
        w.apply_fill(_buy_fill(qty=2, price=100, fees=0))
        # Now sell 1 at 110
        w.apply_fill(_sell_fill(qty=1, price=110, fees=0.5, realized=10))
        pos = w.positions["WSOL"]
        assert pos.qty == 1.0
        # Pro-rata cost basis: 200 * (1/2) = 100 sold off, 100 remains.
        assert pos.cost_basis_usd == pytest.approx(100.0, abs=1e-6)
        # Cash: 1000 - 200 (buy) + 110 (proceeds) - 0.5 (sell fee) = 909.5
        assert w.cash_usd == pytest.approx(909.5, abs=1e-6)
        # Realized PnL accumulated
        assert pos.realized_pnl_usd == 10.0

    def test_sell_against_unknown_position_is_noop(self):
        w = SimulatedWallet.with_initial_cash(1000)
        w.apply_fill(_sell_fill(asset="MYSTERY", qty=5, price=10, fees=0))
        assert w.cash_usd == 1000.0
        assert "MYSTERY" not in w.positions

    def test_full_exit_zeroes_qty(self):
        w = SimulatedWallet.with_initial_cash(1000)
        w.apply_fill(_buy_fill(qty=3, price=100, fees=0))
        w.apply_fill(_sell_fill(qty=3, price=120, fees=0, realized=60))
        assert w.positions["WSOL"].qty == 0.0
        assert w.positions["WSOL"].cost_basis_usd == 0.0
        assert w.positions["WSOL"].realized_pnl_usd == 60.0


# ---------------------------------------------------------------------------
# Halt / unrelated actions
# ---------------------------------------------------------------------------


class TestHaltAndOther:
    def test_halt_is_noop(self):
        w = SimulatedWallet.with_initial_cash(1000)
        w.apply_fill({"ok": True, "action": "halt", "asset": None,
                      "qty_swapped": 0, "fill_price_usd": 0,
                      "gross_proceeds_usd": 0, "fees_usd": 0,
                      "realized_pnl_usd": 0})
        assert w.cash_usd == 1000.0
        assert w.positions == {}


# ---------------------------------------------------------------------------
# Mark-to-market
# ---------------------------------------------------------------------------


class TestMarks:
    def test_update_mark_changes_value_and_unrealized_pnl(self):
        w = SimulatedWallet.with_initial_cash(1000)
        w.apply_fill(_buy_fill(qty=2, price=100, fees=0))
        w.update_mark("WSOL", 150.0)
        snap = w.to_wallet_snapshot()
        wsol = next(t for t in snap["tokens"] if t["asset"] == "WSOL")
        assert wsol["mark_price_usd"] == 150.0
        assert wsol["value_usd"] == 300.0
        # Unrealized PnL = 300 - 200 = 100
        pnl = w.to_pnl_snapshot()
        # Address was empty on the buy fill, so the key is "solana:"
        key = next(iter(pnl))
        assert pnl[key]["unrealized_pnl_usd"] == 100.0
        assert pnl[key]["realized_pnl_usd"] == 0.0

    def test_update_mark_for_unknown_asset_is_noop(self):
        w = SimulatedWallet.with_initial_cash(1000)
        w.update_mark("MYSTERY", 999)
        assert "MYSTERY" not in w.positions


# ---------------------------------------------------------------------------
# Snapshot shapes
# ---------------------------------------------------------------------------


class TestSnapshots:
    def test_wallet_snapshot_excludes_zero_qty_positions(self):
        w = SimulatedWallet.with_initial_cash(1000)
        w.apply_fill(_buy_fill(qty=1, price=100))
        w.apply_fill(_sell_fill(qty=1, price=100))
        snap = w.to_wallet_snapshot()
        assets = [t["asset"] for t in snap["tokens"]]
        # Only USDC remains in the wallet snapshot — zero-qty WSOL is filtered.
        assert assets == ["USDC"]

    def test_pnl_snapshot_keyed_by_chain_address(self):
        w = SimulatedWallet.with_initial_cash(1000)
        w.apply_fill(_buy_fill(asset="WSOL", qty=1, price=100, address="So11"))
        w.update_mark("WSOL", 110)
        pnl = w.to_pnl_snapshot()
        assert "solana:So11" in pnl
        assert pnl["solana:So11"]["asset"] == "WSOL"
        assert pnl["solana:So11"]["unrealized_pnl_usd"] == 10.0

    def test_total_equity_includes_cash_and_marks(self):
        w = SimulatedWallet.with_initial_cash(500)
        w.apply_fill(_buy_fill(qty=2, price=100, fees=0))   # cash 300, position $200 @ mark
        w.update_mark("WSOL", 150)                          # value now $300
        # Cash 300 + WSOL 300 = 600
        assert w.total_equity_usd == 600.0
