"""In-memory simulated wallet that the replay loop owns.

Per cycle the loop:
  1. Updates the simulator's mark price for each asset (from the bar's close)
  2. Asks the simulator to produce wallet + per-token PnL snapshots
  3. Hands those snapshots to PM as --positions-source / --pnl-source
  4. Reads the cycle output back from PM
  5. Applies any fills PM emitted to the simulator

PM doesn't know it's in a backtest — it reads JSON files in exactly the
shape its v0.1.0 synthetic-state demos use. The simulator is the only
piece that ever advances time / tracks state across cycles.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

USDC_BY_CHAIN: dict[str, str] = {
    "solana": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
}


@dataclass
class TokenPosition:
    asset: str
    chain: str
    address: str
    qty: float = 0.0
    cost_basis_usd: float = 0.0
    mark_price_usd: float = 0.0
    realized_pnl_usd: float = 0.0

    @property
    def value_usd(self) -> float:
        return self.qty * self.mark_price_usd

    @property
    def unrealized_pnl_usd(self) -> float:
        return self.value_usd - self.cost_basis_usd


@dataclass
class SimulatedWallet:
    """A toy wallet — cash USDC + an arbitrary number of token positions."""

    wallet_address: str = "bt-wallet"
    chain: str = "solana"
    cash_usd: float = 0.0
    positions: dict[str, TokenPosition] = field(default_factory=dict)

    # ----- factory ----------------------------------------------------

    @classmethod
    def with_initial_cash(
        cls,
        usd: float,
        wallet_address: str = "bt-wallet",
        chain: str = "solana",
    ) -> "SimulatedWallet":
        return cls(wallet_address=wallet_address, chain=chain, cash_usd=float(usd))

    # ----- mutation ---------------------------------------------------

    def update_mark(self, asset: str, mark_price_usd: float) -> None:
        if asset in self.positions:
            self.positions[asset].mark_price_usd = float(mark_price_usd)

    def upsert_position(
        self,
        asset: str,
        address: str,
        chain: str | None = None,
        mark_price_usd: float | None = None,
    ) -> TokenPosition:
        """Idempotent: creates an empty position if missing, returns it."""
        if asset not in self.positions:
            self.positions[asset] = TokenPosition(
                asset=asset, chain=chain or self.chain,
                address=address, mark_price_usd=float(mark_price_usd or 0.0),
            )
        elif mark_price_usd is not None:
            self.positions[asset].mark_price_usd = float(mark_price_usd)
        return self.positions[asset]

    def apply_fill(self, fill: dict[str, Any]) -> None:
        """Mutate state to reflect a Fill dict returned by PM.

        Fill shape: see PM's executor.SwapExecutor docstring. We care about:
          action ∈ {buy, sell, exit, trim, halt}
          asset, qty_swapped, fill_price_usd, gross_proceeds_usd,
          fees_usd, realized_pnl_usd
        """
        action = fill.get("action")
        if action == "halt":
            # PM's executor returns a sentinel for halt; per-position exits
            # come through as separate fills.
            return
        asset = fill.get("asset")
        if not asset:
            return
        qty = float(fill.get("qty_swapped") or 0.0)
        fill_price = float(fill.get("fill_price_usd") or 0.0)
        fees = float(fill.get("fees_usd") or 0.0)

        if action == "buy":
            cost = abs(float(fill.get("gross_proceeds_usd") or qty * fill_price))
            pos = self.upsert_position(
                asset=asset, address=fill.get("address") or "",
                mark_price_usd=fill_price,
            )
            pos.qty += qty
            pos.cost_basis_usd += cost
            self.cash_usd -= cost + fees
        elif action in ("sell", "exit", "trim"):
            pos = self.positions.get(asset)
            if pos is None:
                # PM emitted a fill against a position we don't track —
                # most likely an executor bug; record nothing.
                return
            proceeds = float(fill.get("gross_proceeds_usd") or qty * fill_price)
            # Pro-rata cost basis being sold off.
            prev_qty = pos.qty
            new_qty = max(0.0, prev_qty - qty)
            if prev_qty > 0:
                cost_chunk = pos.cost_basis_usd * (qty / prev_qty)
            else:
                cost_chunk = 0.0
            pos.qty = new_qty
            pos.cost_basis_usd = max(0.0, pos.cost_basis_usd - cost_chunk)
            pos.realized_pnl_usd += float(fill.get("realized_pnl_usd") or 0.0)
            self.cash_usd += proceeds - fees
            if pos.qty == 0:
                # Keep the row so realized_pnl_usd doesn't get lost from the snapshot.
                pass

    # ----- snapshots --------------------------------------------------

    def to_wallet_snapshot(self, ts_utc: str | None = None) -> dict[str, Any]:
        """Shape: PM's SyntheticWalletSource consumes via --positions-source."""
        ts = ts_utc or datetime.now(timezone.utc).isoformat()
        usdc_addr = USDC_BY_CHAIN.get(self.chain, "USDC")
        tokens: list[dict[str, Any]] = [
            {
                "asset": "USDC",
                "chain": self.chain,
                "address": usdc_addr,
                "qty": round(self.cash_usd, 8),
                "mark_price_usd": 1.0,
                "value_usd": round(self.cash_usd, 2),
            }
        ]
        for pos in self.positions.values():
            if pos.qty <= 0:
                continue
            tokens.append({
                "asset": pos.asset,
                "chain": pos.chain,
                "address": pos.address,
                "qty": round(pos.qty, 8),
                "mark_price_usd": round(pos.mark_price_usd, 8),
                "value_usd": round(pos.value_usd, 2),
            })
        return {
            "wallet_address": self.wallet_address,
            "ts_utc": ts,
            "tokens": tokens,
        }

    def to_pnl_snapshot(self) -> dict[str, dict[str, Any]]:
        """Shape PM consumes via --pnl-source.
        Keyed by '<chain>:<address>'."""
        out: dict[str, dict[str, Any]] = {}
        for pos in self.positions.values():
            if pos.qty <= 0 and pos.realized_pnl_usd == 0:
                continue
            key = f"{pos.chain}:{pos.address}"
            out[key] = {
                "asset": pos.asset,
                "unrealized_pnl_usd": round(pos.unrealized_pnl_usd, 4),
                "realized_pnl_usd": round(pos.realized_pnl_usd, 4),
            }
        return out

    @property
    def total_equity_usd(self) -> float:
        return round(self.cash_usd + sum(p.value_usd for p in self.positions.values()), 2)
