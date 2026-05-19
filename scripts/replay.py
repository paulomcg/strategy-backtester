"""Replay loop — drive PM through a parquet of historical OHLCV.

For each bar:
  1. Update sim_wallet marks to bar.close
  2. Serialize wallet + pnl + market snapshots to JSON files in the run dir
  3. Subprocess `pm watch --iterations 1` against those snapshot files,
     with PM_STATE_DIR pointed at the run dir so PM's audit accumulates
     in <run-dir>/pm-state/audit.jsonl
  4. Parse PM's stdout for the cycle record + fills
  5. Apply each fill back to the sim_wallet

After the loop:
  - Subprocess `pm report --audit-path <run-dir>/pm-state/audit.jsonl
                         --out <run-dir>/report/`

PM doesn't know it's in a backtest. The whole interface is the synthetic
file-source flags PM v0.1.0 already exposes for synthetic demos
(--positions-source / --pnl-source / --market-data-source / --executor
synthetic / --live).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from . import config
from .sim_wallet import SimulatedWallet


class ReplayError(Exception):
    """First word maps to a canonical FAILED token."""


def run_replay(
    *,
    ohlcv_paths: list[Path] | Path,
    strategy_path: Path,
    rules_path: Path,
    initial_usd: float = 1000.0,
    symbols: list[str] | str | None = None,
    chain: str = "solana",
    out_dir: Path | None = None,
    fees_bps: float = 30.0,
    slippage_bps: float = 50.0,
    pm_bin: str | None = None,
    max_loss_usd: float = 99_999.0,
    progress_cb=None,
) -> dict[str, Any]:
    """Drive PM through one or more OHLCV parquets, run pm report at the end.

    Multi-asset semantics: when multiple parquets are passed, each cycle
    feeds market_data for *every* asset simultaneously, marks the wallet
    against every asset's current price, and lets the strategy decide
    across the universe. Cycle timestamps are the intersection of every
    parquet's index — bars missing on any asset are skipped.
    """
    pm_bin = pm_bin or config.pm_bin()
    if isinstance(ohlcv_paths, (str, Path)):
        ohlcv_paths = [ohlcv_paths]
    ohlcv_paths = [Path(p).expanduser().resolve() for p in ohlcv_paths]
    strategy_path = Path(strategy_path).expanduser().resolve()
    rules_path = Path(rules_path).expanduser().resolve()
    for p in ohlcv_paths:
        if not p.exists():
            raise ReplayError(f"replay_input_invalid ohlcv not found: {p}")
    if not strategy_path.exists():
        raise ReplayError(f"replay_input_invalid strategy not found: {strategy_path}")
    if not rules_path.exists():
        raise ReplayError(f"replay_input_invalid rules not found: {rules_path}")

    # Symbol resolution: explicit list > inferred from each path's stem.
    if symbols is None:
        resolved_symbols = [_infer_symbol(p) for p in ohlcv_paths]
    elif isinstance(symbols, str):
        resolved_symbols = [symbols] if len(ohlcv_paths) == 1 else symbols.split(",")
    else:
        resolved_symbols = list(symbols)
    if len(resolved_symbols) != len(ohlcv_paths):
        raise ReplayError(
            f"replay_input_invalid symbol/parquet count mismatch: "
            f"{len(resolved_symbols)} symbols vs {len(ohlcv_paths)} parquets"
        )

    run_id = _make_run_id()
    out_dir = Path(out_dir) if out_dir else (config.runs_dir() / run_id)
    pm_state_dir = out_dir / "pm-state"
    snapshots_dir = out_dir / "snapshots"
    pm_state_dir.mkdir(parents=True, exist_ok=True)
    snapshots_dir.mkdir(parents=True, exist_ok=True)

    # Load + normalize each parquet, keyed by symbol.
    bars_by_asset: dict[str, pd.DataFrame] = {}
    for sym, p in zip(resolved_symbols, ohlcv_paths):
        df = _normalize_bars_df(pd.read_parquet(p))
        if df.empty:
            raise ReplayError(f"replay_input_invalid empty parquet for {sym}: {p}")
        bars_by_asset[sym] = df

    # Iterate over the intersection of all parquets' timestamp indices.
    common_idx = None
    for df in bars_by_asset.values():
        common_idx = df.index if common_idx is None else common_idx.intersection(df.index)
    common_idx = common_idx.sort_values()
    if len(common_idx) == 0:
        raise ReplayError("replay_input_invalid no overlapping timestamps across parquets")

    addresses = {sym: _infer_address(p, sym) for sym, p in zip(resolved_symbols, ohlcv_paths)}

    sim = SimulatedWallet.with_initial_cash(
        initial_usd, wallet_address=f"bt-{run_id[:8]}", chain=chain,
    )
    pm_env = _build_pm_env(pm_state_dir)
    pm_env["PM_SYNTHETIC_FEE_BPS"] = str(fees_bps)
    pm_env["PM_SYNTHETIC_SLIPPAGE_BPS"] = str(slippage_bps)

    # Per-asset history accumulator (PM strategies receive prior bars).
    history_by_asset: dict[str, list[dict[str, Any]]] = {s: [] for s in resolved_symbols}
    cycle_records: list[dict[str, Any]] = []
    fills_total = 0
    pm_call_failures = 0

    for bar_idx, ts in enumerate(common_idx):
        ts_str = ts.isoformat() if hasattr(ts, "isoformat") else str(ts)

        # Build the per-cycle bar dict for each asset, mark wallet.
        cycle_bars: dict[str, dict[str, Any]] = {}
        for sym in resolved_symbols:
            row = bars_by_asset[sym].loc[ts]
            # When .loc returns a DataFrame (duplicate ts) we'd already have
            # filtered duplicates; treat as a Series.
            if isinstance(row, pd.DataFrame):
                row = row.iloc[-1]
            bar_dict = {
                "ts": ts_str,
                "asset": sym,
                "bar_index": bar_idx,
                "o": float(row["o"]), "h": float(row["h"]),
                "l": float(row["l"]), "c": float(row["c"]),
                "vol": float(row["vol"]), "volUsd": float(row["volUsd"]),
            }
            sim.update_mark(sym, bar_dict["c"])
            cycle_bars[sym] = bar_dict

        # Build snapshots
        wallet_path = snapshots_dir / "wallet.json"
        pnl_path = snapshots_dir / "pnl.json"
        market_path = snapshots_dir / "market.json"
        wallet_path.write_text(json.dumps(sim.to_wallet_snapshot(ts_utc=ts_str)))
        pnl_path.write_text(json.dumps(sim.to_pnl_snapshot()))
        market_path.write_text(json.dumps({
            sym: {
                "current": cycle_bars[sym],
                "history": list(history_by_asset[sym]),
            }
            for sym in resolved_symbols
        }))

        # Drive PM for one cycle.
        argv = [
            pm_bin, "watch",
            "--config", str(rules_path),
            "--positions-source", str(wallet_path),
            "--pnl-source", str(pnl_path),
            "--market-data-source", str(market_path),
            "--strategy", str(strategy_path),
            "--executor", "synthetic",
            "--live", "--max-loss-usd", str(max_loss_usd),
            "--interval", "0",
            "--iterations", "1",
        ]
        try:
            res = subprocess.run(
                argv, capture_output=True, text=True, env=pm_env, timeout=60
            )
        except FileNotFoundError as e:
            raise ReplayError(f"pm_not_installed {e.filename}") from e
        except subprocess.TimeoutExpired as e:
            raise ReplayError(f"pm_call_timeout cycle={bar_idx}") from e

        if res.returncode != 0:
            pm_call_failures += 1
            tail = (res.stderr or "").strip().splitlines()[-1:] or ["non-zero exit"]
            cycle_records.append({
                "bar_index": bar_idx,
                "ok": False,
                "error": tail[0],
            })
            for sym in resolved_symbols:
                history_by_asset[sym].append(cycle_bars[sym])
            continue

        cycle, summary = _parse_pm_output(res.stdout)
        if cycle is not None:
            for fill in cycle.get("fills", []):
                if fill.get("ok") is False:  # skipped (cap-projected) — don't touch sim
                    continue
                sim.apply_fill(fill)
                fills_total += 1
            cycle_records.append({
                "bar_index": bar_idx,
                "ok": True,
                "ts_utc": ts_str,
                "fills": len(cycle.get("fills", [])),
                "decisions": len(cycle.get("decisions", [])),
                "strategy_actions": len((cycle.get("strategy") or {}).get("actions", [])),
                "errors": cycle.get("errors", []),
            })
        if progress_cb:
            progress_cb(bar_idx, len(common_idx), sim.total_equity_usd)
        for sym in resolved_symbols:
            history_by_asset[sym].append(cycle_bars[sym])

    # PM's per-cycle audit ts_utc reflects wall-clock subprocess execution
    # time (milliseconds apart in a backtest). Rewrite to bar timestamps so
    # pm report's annualized metrics (Sharpe/Sortino/Calmar) reflect the
    # actual bar cadence, not real-time clock cadence.
    audit_path = pm_state_dir / "audit.jsonl"
    # For the title + audit-rewrite, label using the first (primary) symbol.
    primary_sym = resolved_symbols[0]
    _rewrite_audit_ts_to_bars(audit_path, common_idx, primary_sym)

    # Final pm report
    report_dir = out_dir / "report"
    report_dir.mkdir(parents=True, exist_ok=True)
    title_assets = "+".join(resolved_symbols)
    report_argv = [
        pm_bin, "report",
        "--audit-path", str(audit_path),
        "--out", str(report_dir),
        "--title", f"Backtest {title_assets} {common_idx.min()} → {common_idx.max()}",
    ]
    try:
        rep = subprocess.run(
            report_argv, capture_output=True, text=True, env=pm_env, timeout=30
        )
    except FileNotFoundError as e:
        raise ReplayError(f"pm_not_installed {e.filename}") from e
    report_ok = rep.returncode == 0
    report_summary: dict[str, Any] | None = None
    if report_ok:
        try:
            report_summary = json.loads(rep.stdout).get("result")
        except json.JSONDecodeError:
            pass

    # Persist a top-level run.json
    run_meta = {
        "run_id": run_id,
        "ohlcv_paths": [str(p) for p in ohlcv_paths],
        "ohlcv_path": str(ohlcv_paths[0]),  # legacy single-asset compat
        "strategy_path": str(strategy_path),
        "rules_path": str(rules_path),
        "assets": resolved_symbols,
        "asset": primary_sym,  # legacy single-asset compat
        "addresses": addresses,
        "address": addresses.get(primary_sym, ""),
        "chain": chain,
        "initial_usd": initial_usd,
        "bars_processed": len(cycle_records),
        "fills_total": fills_total,
        "pm_call_failures": pm_call_failures,
        "final_equity_usd": sim.total_equity_usd,
        "report_path": str(report_dir / "report.json") if report_ok else None,
        "report_md_path": str(report_dir / "report.md") if report_ok else None,
        "equity_chart_path": str(report_dir / "equity.png") if report_ok else None,
        "report_summary": report_summary,
        "cycles": cycle_records[-10:],  # tail only — full audit is in pm-state/
    }
    (out_dir / "run.json").write_text(json.dumps(run_meta, indent=2, default=str))

    if report_ok:
        try:
            from . import html_report
            html_report.emit_html_report(out_dir)
        except Exception:
            pass
    return run_meta


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_run_id() -> str:
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{ts}-{uuid.uuid4().hex[:6]}"


def _build_pm_env(pm_state_dir: Path) -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    env["PM_STATE_DIR"] = str(pm_state_dir)
    env["PM_AUDIT_PATH"] = str(pm_state_dir / "audit.jsonl")
    env["PM_SQLITE_PATH"] = str(pm_state_dir / "positions.sqlite")
    env["PM_ALERTS_LOG_PATH"] = str(pm_state_dir / "alerts.jsonl")
    return env


def _normalize_bars_df(df: pd.DataFrame) -> pd.DataFrame:
    """Ensure the parquet has the expected columns + chronological order."""
    required = {"ts", "o", "h", "l", "c", "vol", "volUsd"}
    missing = required - set(df.columns)
    if missing:
        raise ReplayError(
            f"replay_input_invalid parquet missing columns: {sorted(missing)}"
        )
    df = df.copy()
    df.index = pd.to_datetime(df["ts"], utc=True, errors="coerce")
    df = df[df.index.notna()].sort_index()
    return df


def _row_to_bar_dict(row, asset: str, bar_idx: int) -> dict[str, Any]:
    return {
        "ts": str(row.ts),
        "asset": asset,
        "bar_index": bar_idx,
        "o": float(row.o), "h": float(row.h),
        "l": float(row.l), "c": float(row.c),
        "vol": float(row.vol), "volUsd": float(row.volUsd),
    }


def _parse_pm_output(stdout: str) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """pm watch emits one cycle line per iteration + one summary line. Parse both."""
    cycle: dict[str, Any] | None = None
    summary: dict[str, Any] | None = None
    for line in stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if "cycle_index" in obj:
            cycle = obj
        elif "result" in obj:
            summary = obj["result"]
    return cycle, summary


def _rewrite_audit_ts_to_bars(
    audit_path: Path, bar_index: pd.DatetimeIndex, asset: str
) -> None:
    """Rewrite each watch.cycle row's ts_utc to its corresponding bar ts.

    The Nth watch.cycle event in the audit corresponds to the Nth bar we
    drove PM through. Cycles that PM rejected (returncode != 0) didn't
    produce an audit row, so the count matches naturally.
    """
    if not audit_path.exists():
        return
    lines = audit_path.read_text(encoding="utf-8").splitlines()
    cycle_idx = 0
    out: list[str] = []
    for ln in lines:
        ln = ln.strip()
        if not ln:
            continue
        try:
            row = json.loads(ln)
        except json.JSONDecodeError:
            out.append(ln)
            continue
        if row.get("event") == "watch.cycle" and cycle_idx < len(bar_index):
            ts = bar_index[cycle_idx]
            iso = ts.isoformat() if hasattr(ts, "isoformat") else str(ts)
            row["ts_utc"] = iso
            row["wallet"] = row.get("wallet") or asset
            cycle_idx += 1
            out.append(json.dumps(row, default=str))
        else:
            out.append(ln)
    audit_path.write_text("\n".join(out) + ("\n" if out else ""), encoding="utf-8")


def _infer_symbol(parquet_path: Path) -> str:
    """Derive symbol from `<symbol>-<bar>.parquet` if possible."""
    stem = parquet_path.stem
    if "-" in stem:
        return stem.split("-")[0]
    return stem


def _infer_address(parquet_path: Path, symbol: str) -> str:
    """Best-effort: look for a sidecar .meta.json next to the parquet."""
    meta = parquet_path.with_suffix(".meta.json")
    if meta.exists():
        try:
            return json.loads(meta.read_text()).get("address", "") or ""
        except json.JSONDecodeError:
            return ""
    return ""
