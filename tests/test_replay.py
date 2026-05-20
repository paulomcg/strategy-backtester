"""End-to-end + unit tests for the replay loop.

The end-to-end test invokes the real `pm` binary — needs PM installed and
on PATH (set via PATH env when invoking pytest).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pandas as pd
import pytest

from scripts import replay
from scripts.replay import ReplayError


FIXTURES = Path(__file__).parent / "fixtures"
EXAMPLES = Path(__file__).parent.parent / "examples"

PM_AVAILABLE = shutil.which("pm") is not None


def _make_synthetic_parquet(tmp_path: Path, prices: list[float]) -> Path:
    rows = []
    for i, p in enumerate(prices):
        ts = pd.Timestamp("2025-01-01", tz="UTC") + pd.Timedelta(days=i)
        rows.append({
            "ts": ts.isoformat(), "o": p - 1, "h": p + 2, "l": p - 2, "c": p,
            "vol": 1000.0, "volUsd": 1000.0 * p,
        })
    df = pd.DataFrame(rows)
    df.index = pd.to_datetime(df["ts"], utc=True)
    out = tmp_path / "synthetic.parquet"
    df.to_parquet(out)
    return out


# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------


class TestInputValidation:
    def test_missing_ohlcv_raises(self, tmp_path):
        with pytest.raises(ReplayError, match="ohlcv not found"):
            replay.run_replay(
                ohlcv_paths=[tmp_path / "nope.parquet"],
                strategy_path=EXAMPLES / "strategies" / "buy_and_hold_wsol.py",
                rules_path=EXAMPLES / "rules" / "conservative.yaml",
            )

    def test_missing_strategy_raises(self, tmp_path):
        ohlcv = _make_synthetic_parquet(tmp_path, [100, 101])
        with pytest.raises(ReplayError, match="strategy not found"):
            replay.run_replay(
                ohlcv_paths=[ohlcv],
                strategy_path=tmp_path / "nope.py",
                rules_path=EXAMPLES / "rules" / "conservative.yaml",
            )

    def test_missing_rules_raises(self, tmp_path):
        ohlcv = _make_synthetic_parquet(tmp_path, [100, 101])
        with pytest.raises(ReplayError, match="rules not found"):
            replay.run_replay(
                ohlcv_paths=[ohlcv],
                strategy_path=EXAMPLES / "strategies" / "buy_and_hold_wsol.py",
                rules_path=tmp_path / "nope.yaml",
            )


# ---------------------------------------------------------------------------
# Audit ts rewrite
# ---------------------------------------------------------------------------


class TestAuditTsRewrite:
    def test_rewrite_uses_bar_index_in_order(self, tmp_path):
        audit = tmp_path / "audit.jsonl"
        audit.write_text(
            "\n".join([
                json.dumps({"event": "watch.cycle", "ts_utc": "2026-01-01T00:00:00Z"}),
                json.dumps({"event": "watch.cycle", "ts_utc": "2026-01-01T00:00:01Z"}),
                json.dumps({"event": "watch.cycle", "ts_utc": "2026-01-01T00:00:02Z"}),
            ]) + "\n"
        )
        idx = pd.DatetimeIndex(pd.date_range("2025-06-01", periods=3, freq="D", tz="UTC"))
        replay._rewrite_audit_ts_to_bars(audit, idx, asset="WSOL")
        rows = [json.loads(l) for l in audit.read_text().splitlines() if l.strip()]
        assert rows[0]["ts_utc"].startswith("2025-06-01")
        assert rows[1]["ts_utc"].startswith("2025-06-02")
        assert rows[2]["ts_utc"].startswith("2025-06-03")

    def test_rewrite_skips_non_cycle_rows(self, tmp_path):
        audit = tmp_path / "audit.jsonl"
        audit.write_text(
            "\n".join([
                json.dumps({"event": "position.add", "ts_utc": "x"}),
                json.dumps({"event": "watch.cycle", "ts_utc": "x"}),
            ]) + "\n"
        )
        idx = pd.DatetimeIndex([pd.Timestamp("2025-06-01", tz="UTC")])
        replay._rewrite_audit_ts_to_bars(audit, idx, asset="WSOL")
        rows = [json.loads(l) for l in audit.read_text().splitlines()]
        assert rows[0]["ts_utc"] == "x"           # untouched
        assert rows[1]["ts_utc"].startswith("2025-06-01")


# ---------------------------------------------------------------------------
# End-to-end against real PM
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not PM_AVAILABLE, reason="pm binary not on PATH")
class TestEndToEndAgainstPM:
    def test_buy_and_hold_replay(self, tmp_path):
        ohlcv = _make_synthetic_parquet(
            tmp_path, [100, 102, 105, 108, 106, 110, 113, 109, 115, 112,
                       118, 120, 117, 122, 125, 121, 128, 130, 127, 133]
        )
        out_dir = tmp_path / "run"
        result = replay.run_replay(
            ohlcv_path=ohlcv,
            strategy_path=EXAMPLES / "strategies" / "buy_and_hold_wsol.py",
            rules_path=EXAMPLES / "rules" / "conservative.yaml",
            initial_usd=1000.0, symbol="WSOL",
            out_dir=out_dir,
        )
        assert result["bars_processed"] == 20
        assert result["pm_call_failures"] == 0
        assert result["fills_total"] >= 1
        # Report files exist
        assert (out_dir / "report" / "report.json").exists()
        assert (out_dir / "report" / "report.md").exists()
        assert (out_dir / "report" / "equity.png").exists()
        # Audit ts was rewritten to bar timestamps → periods_per_year sane
        report = json.loads((out_dir / "report" / "report.json").read_text())
        assert report["metrics"]["periods_per_year"] == 365
