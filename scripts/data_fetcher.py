"""OHLCV data fetcher — wraps `onchainos market kline` + parquet caching.

The backtester's only OKX-touching path. Fetches historical bars for a
single (chain, token, bar) tuple, walks --after pagination cursors to
assemble multi-call history, dedups by ts, writes a parquet at
`<cache_dir>/<symbol>-<bar>.parquet` (or --out).

Cache-hit behavior: a subsequent invocation with the same args returns the
existing parquet path without touching the network. Override with --force.
"""

from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from . import config


class DataFetchError(Exception):
    """First word maps to a canonical FAILED token, e.g. 'data_fetch_failed'."""


# OKX-DEX kline cap per response — verified against the docs in the planning
# session. We page via --after to walk further back than 299 bars.
KLINE_PAGE_SIZE = 299
# Hard upper bound — OKX docs cap historical depth at ~1440 entries per token.
KLINE_HARD_CAP = 1440


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def fetch(
    *,
    token: str,
    chain: str = "solana",
    bar: str = "1D",
    start: str | None = None,
    end: str | None = None,
    symbol: str | None = None,
    out: Path | None = None,
    force: bool = False,
    cli_bin: str = "onchainos",
) -> dict[str, Any]:
    """Fetch OHLCV bars and persist to parquet. Returns a result dict."""
    sym = symbol or _symbol_from_token(token)
    out_path = Path(out) if out else (config.cache_dir() / f"{sym}-{bar}.parquet")
    if out_path.exists() and not force:
        df = pd.read_parquet(out_path)
        return {
            "ok": True,
            "cached": True,
            "path": str(out_path),
            "rows": len(df),
            "bar": bar,
            "chain": chain,
            "symbol": sym,
            "start": _iso(df.index.min()) if not df.empty else None,
            "end": _iso(df.index.max()) if not df.empty else None,
            "api_calls": 0,
        }

    bars, api_calls = _walk_kline(
        cli_bin=cli_bin, token=token, chain=chain, bar=bar,
        start=start, end=end,
    )
    df = _bars_to_df(bars)
    if start:
        df = df[df["ts_dt"] >= pd.to_datetime(start, utc=True)]
    if end:
        df = df[df["ts_dt"] <= pd.to_datetime(end, utc=True)]
    df = df.drop(columns=["ts_dt"])

    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out_path)
    return {
        "ok": True,
        "cached": False,
        "path": str(out_path),
        "rows": len(df),
        "bar": bar,
        "chain": chain,
        "symbol": sym,
        "token": token,
        "start": _iso(df.index.min()) if not df.empty else None,
        "end": _iso(df.index.max()) if not df.empty else None,
        "api_calls": api_calls,
    }


# ---------------------------------------------------------------------------
# Subprocess driver
# ---------------------------------------------------------------------------


def _walk_kline(
    *,
    cli_bin: str,
    token: str,
    chain: str,
    bar: str,
    start: str | None,
    end: str | None,
) -> tuple[list[dict[str, Any]], int]:
    """Page through `onchainos market kline` until we hit the cap or no new bars.

    Returns (deduped_bars, api_calls).
    """
    bars: list[dict[str, Any]] = []
    seen_ts: set[str] = set()
    api_calls = 0
    after_cursor: str | None = None  # ts (string) — bars older than this

    while len(bars) < KLINE_HARD_CAP:
        argv = [
            cli_bin, "market", "kline",
            "--chain", chain,
            "--address", token,
            "--bar", bar,
            "--limit", str(KLINE_PAGE_SIZE),
        ]
        if after_cursor is not None:
            argv.extend(["--after", after_cursor])

        api_calls += 1
        payload = _run_json(argv)
        new_bars = _candles_from_payload(payload)
        if not new_bars:
            break

        added = 0
        for b in new_bars:
            if b["ts"] in seen_ts:
                continue
            seen_ts.add(b["ts"])
            bars.append(b)
            added += 1
        if added == 0:
            # API returned only duplicates — we've drained the window.
            break

        # Move cursor to the OLDEST ts we just received so the next page
        # walks further back in time.
        oldest = min(new_bars, key=lambda b: b["ts"])
        after_cursor = oldest["ts"]

        # Early exit: if --start was provided and we've crossed it, stop.
        if start and oldest["ts"] < _to_ms_string(start):
            break

    return bars, api_calls


def _run_json(argv: list[str], timeout: int = 30) -> Any:
    try:
        res = subprocess.run(
            argv, capture_output=True, text=True, check=False, timeout=timeout
        )
    except FileNotFoundError as e:
        raise DataFetchError(f"data_fetch_failed cli_not_found {e.filename}") from e
    except subprocess.TimeoutExpired as e:
        raise DataFetchError(f"data_fetch_failed cli_timeout {' '.join(argv)}") from e
    if res.returncode != 0:
        tail = (res.stderr or res.stdout).strip().splitlines()[-1:] or [""]
        if "OK-ACCESS-KEY" in tail[0] or "auth" in tail[0].lower():
            raise DataFetchError(
                "data_fetch_failed wallet_not_logged_in (set OKX_API_KEY/SECRET_KEY/PASSPHRASE)"
            )
        raise DataFetchError(f"data_fetch_failed {tail[0]}")
    try:
        return json.loads(res.stdout)
    except json.JSONDecodeError as e:
        raise DataFetchError(f"data_fetch_failed cli_output_invalid {e.msg}") from e


# ---------------------------------------------------------------------------
# Payload adapters (kept in sync with PM's market_data.py)
# ---------------------------------------------------------------------------


def _candles_from_payload(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    raw = payload.get("data") if "data" in payload else payload
    if isinstance(raw, dict):
        for key in ("candles", "data", "events", "items"):
            if key in raw and isinstance(raw[key], list):
                raw = raw[key]
                break
    if not isinstance(raw, list):
        return []
    out: list[dict[str, Any]] = []
    for item in raw:
        bar = _normalize_bar(item)
        if bar is not None:
            out.append(bar)
    return out


def _normalize_bar(item: Any) -> dict[str, Any] | None:
    if isinstance(item, dict):
        ts = item.get("ts") or item.get("timestamp") or item.get("time")
        if ts is None:
            return None
        try:
            return {
                "ts": _coerce_ts(ts),
                "o": float(item.get("o", item.get("open", 0))),
                "h": float(item.get("h", item.get("high", 0))),
                "l": float(item.get("l", item.get("low", 0))),
                "c": float(item.get("c", item.get("close", 0))),
                "vol": float(item.get("vol", item.get("volume", 0))),
                "volUsd": float(item.get("volUsd", item.get("volumeUsd", 0))),
            }
        except (TypeError, ValueError):
            return None
    if isinstance(item, list) and len(item) >= 6:
        try:
            return {
                "ts": _coerce_ts(item[0]),
                "o": float(item[1]), "h": float(item[2]),
                "l": float(item[3]), "c": float(item[4]),
                "vol": float(item[5]),
                "volUsd": float(item[6]) if len(item) > 6 else 0.0,
            }
        except (TypeError, ValueError):
            return None
    return None


def _coerce_ts(value: Any) -> str:
    """Coerce kline ts (ms-string, int, or ISO 8601) to ISO UTC."""
    if isinstance(value, str):
        s = value.strip()
        if s.lstrip("-").isdigit():
            ms = int(s)
            seconds = ms / 1000 if abs(ms) > 1e12 else ms
            return datetime.fromtimestamp(seconds, tz=timezone.utc).isoformat()
        try:
            return pd.to_datetime(s, utc=True).isoformat()
        except (TypeError, ValueError):
            return s
    if isinstance(value, (int, float)):
        ms = int(value)
        seconds = ms / 1000 if abs(ms) > 1e12 else ms
        return datetime.fromtimestamp(seconds, tz=timezone.utc).isoformat()
    return str(value)


def _to_ms_string(iso: str) -> str:
    """Convert ISO 8601 → ms-since-epoch string (matches OKX cursor format)."""
    return pd.to_datetime(iso, utc=True).isoformat()


def _bars_to_df(bars: list[dict[str, Any]]) -> pd.DataFrame:
    if not bars:
        return pd.DataFrame(columns=["ts", "o", "h", "l", "c", "vol", "volUsd"])
    df = pd.DataFrame(bars)
    df["ts_dt"] = pd.to_datetime(df["ts"], utc=True, errors="coerce")
    df = df.dropna(subset=["ts_dt"]).sort_values("ts_dt").reset_index(drop=True)
    df = df.set_index("ts_dt", drop=False)
    df.index.name = None
    return df


def _symbol_from_token(token: str) -> str:
    return token[:8]


def _iso(ts: Any) -> str:
    if isinstance(ts, str):
        return ts
    try:
        return pd.to_datetime(ts, utc=True).isoformat()
    except (TypeError, ValueError):
        return str(ts)
