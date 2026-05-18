"""Render the self-contained interactive HTML report for a backtester run.

Reads `<run_dir>/run.json`, `<run_dir>/report/report.json`, and
`<run_dir>/pm-state/audit.jsonl`; constructs a ReportPayload matching the
shape consumed by `report-ui/src/types.ts`; injects it as
`window.__RUN_DATA__` into the bundled single-file React template at
`scripts/report_template.html`; writes `<run_dir>/report/report.html`.

The template is rebuilt by `cd report-ui && npm run build` — that script
copies the latest `dist/index.html` here automatically.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

TEMPLATE_PATH = Path(__file__).resolve().parent / "report_template.html"
PLACEHOLDER = "// window.__RUN_DATA__ = __RUN_DATA_JSON__;"


def emit_html_report(run_dir: Path) -> Path | None:
    """Write report.html alongside report.md. Returns the path or None if inputs missing."""
    run_dir = Path(run_dir)
    run_json_path = run_dir / "run.json"
    audit_path = run_dir / "pm-state" / "audit.jsonl"
    report_dir = run_dir / "report"
    report_json_path = report_dir / "report.json"

    if not run_json_path.exists():
        return None
    if not report_json_path.exists():
        return None
    if not TEMPLATE_PATH.exists():
        return None

    run_meta = json.loads(run_json_path.read_text())
    report_json = json.loads(report_json_path.read_text())

    cycles = _read_cycles(audit_path) if audit_path.exists() else []
    equity = _build_equity_with_dd(cycles)
    fills = _collect_fills(cycles)

    metrics = report_json.get("metrics") or {}
    payload: dict[str, Any] = {
        "schema_version": "1",
        "meta": _build_meta(run_meta, report_json),
        "metrics": _normalize_metrics(metrics),
        "equity": equity,
        "fills": fills,
    }

    template = TEMPLATE_PATH.read_text(encoding="utf-8")
    injection = f"window.__RUN_DATA__ = {json.dumps(payload, default=str)};"
    if PLACEHOLDER in template:
        out = template.replace(PLACEHOLDER, injection, 1)
    else:
        # Template was rebuilt without the placeholder — inject a fresh script
        # right before </head> so the global is set before main.tsx runs.
        out = template.replace(
            "</head>", f"<script>{injection}</script></head>", 1
        )

    html_path = report_dir / "report.html"
    report_dir.mkdir(parents=True, exist_ok=True)
    html_path.write_text(out, encoding="utf-8")
    return html_path


def _build_meta(run_meta: dict[str, Any], report_json: dict[str, Any]) -> dict[str, Any]:
    return {
        "run_id": run_meta.get("run_id", ""),
        "generated_at_utc": report_json.get("generated_at_utc")
            or run_meta.get("generated_at_utc")
            or "",
        "asset": run_meta.get("asset", ""),
        "address": run_meta.get("address") or None,
        "chain": run_meta.get("chain", ""),
        "initial_usd": _as_float(run_meta.get("initial_usd"), default=0.0),
        "bars_processed": int(run_meta.get("bars_processed") or 0),
        "fills_total": int(run_meta.get("fills_total") or 0),
        "pm_call_failures": int(run_meta.get("pm_call_failures") or 0),
        "final_equity_usd": _as_float(run_meta.get("final_equity_usd"), default=0.0),
        "strategy_path": run_meta.get("strategy_path", ""),
        "rules_path": run_meta.get("rules_path", ""),
        "ohlcv_path": run_meta.get("ohlcv_path", ""),
        "mode": "backtest",
        "title": run_meta.get("title") or f"Backtest {run_meta.get('asset', '')}".strip(),
    }


def _normalize_metrics(m: dict[str, Any]) -> dict[str, Any]:
    """Ensure all required fields are present (default to 0 / empty)."""
    trades = m.get("trades") or {}
    return {
        "schema_version": str(m.get("schema_version", "1")),
        "bars": int(m.get("bars") or 0),
        "periods_per_year": m.get("periods_per_year"),
        "initial_equity_usd": _as_float(m.get("initial_equity_usd"), default=0.0),
        "final_equity_usd": _as_float(m.get("final_equity_usd"), default=0.0),
        "total_return_pct": _as_float(m.get("total_return_pct"), default=0.0),
        "cagr_pct": _as_float(m.get("cagr_pct"), default=0.0),
        "sharpe": _as_float(m.get("sharpe"), default=0.0),
        "sortino": _as_float(m.get("sortino"), default=0.0),
        "calmar": _as_float(m.get("calmar"), default=0.0),
        "max_drawdown_pct": _as_float(m.get("max_drawdown_pct"), default=0.0),
        "max_drawdown_peak_ts": m.get("max_drawdown_peak_ts"),
        "max_drawdown_trough_ts": m.get("max_drawdown_trough_ts"),
        "trades": {
            "trades": int(trades.get("trades") or 0),
            "winners": int(trades.get("winners") or 0),
            "losers": int(trades.get("losers") or 0),
            "win_rate": _as_float(trades.get("win_rate"), default=0.0),
            "expectancy_usd": _as_float(trades.get("expectancy_usd"), default=0.0),
            "total_pnl_usd": _as_float(trades.get("total_pnl_usd"), default=0.0),
        },
        "per_asset_pnl_usd": {
            k: _as_float(v, default=0.0) for k, v in (m.get("per_asset_pnl_usd") or {}).items()
        },
        "warning": m.get("warning"),
    }


def _read_cycles(audit_path: Path) -> list[dict[str, Any]]:
    """Read the audit JSONL and return watch.cycle events in chronological order."""
    cycles: list[dict[str, Any]] = []
    for line in audit_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if row.get("event") != "watch.cycle":
            continue
        cycles.append(row)
    cycles.sort(key=lambda r: r.get("ts_utc", ""))
    return cycles


def _build_equity_with_dd(cycles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Equity series with rolling drawdown vs high-water mark, in chronological order."""
    out: list[dict[str, Any]] = []
    hwm = float("-inf")
    for c in cycles:
        positions = c.get("positions") or {}
        eq = positions.get("total_equity_usd")
        ts = c.get("ts_utc")
        if eq is None or ts is None:
            continue
        try:
            eq_f = float(eq)
        except (TypeError, ValueError):
            continue
        hwm = max(hwm, eq_f)
        dd = ((eq_f - hwm) / hwm) * 100 if hwm > 0 else 0.0
        out.append(
            {"ts_utc": ts, "equity_usd": round(eq_f, 6), "drawdown_pct": round(dd, 4)}
        )
    return out


def _collect_fills(cycles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Flatten + normalize PM's fill records into the UI's Fill schema."""
    out: list[dict[str, Any]] = []
    for c in cycles:
        cycle_ts = c.get("ts_utc")
        for f in c.get("fills") or []:
            if f.get("ok") is False:
                continue  # cap-projected / skipped
            action = f.get("action") or ""
            if action in ("sell", "exit"):
                side = "sell"
            elif action == "buy":
                side = "buy"
            else:
                continue  # halts / other non-positional actions
            qty = _as_float(f.get("qty_swapped"), default=0.0)
            price = _as_float(f.get("fill_price_usd"), default=0.0)
            value = abs(qty * price)
            out.append({
                "ts_utc": f.get("ts_utc") or cycle_ts,
                "asset": f.get("asset", ""),
                "side": side,
                "qty": round(abs(qty), 8),
                "price_usd": round(price, 6),
                "value_usd": round(value, 4),
                "fees_usd": _as_float(f.get("fees_usd")),
                "slippage_usd": _as_float(f.get("slippage_usd")),
                "rule": f.get("rule") if f.get("source") != "strategy" else None,
                "decision": "strategy.decide" if f.get("source") == "strategy" else None,
            })
    return out


def _as_float(v: Any, default: float | None = None) -> float | None:
    if v is None:
        return default
    try:
        return float(v)
    except (TypeError, ValueError):
        return default
