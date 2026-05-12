"""Tests for data_fetcher — subprocess-mocked onchainos kline calls."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest

from scripts import data_fetcher
from scripts.data_fetcher import DataFetchError


def _completed(stdout: str, returncode: int = 0, stderr: str = "") -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(
        args=["onchainos"], returncode=returncode, stdout=stdout, stderr=stderr
    )


def _kline_payload(prices: list[float], start_ms: int = 1735689600000) -> str:
    """Build an onchainos market kline-shaped payload (ms-string ts, daily bars)."""
    return json.dumps({
        "ok": True,
        "data": [
            {
                "ts": str(start_ms + i * 86_400_000),
                "o": p - 1, "h": p + 2, "l": p - 2, "c": p,
                "vol": 100.0, "volUsd": 100.0 * p,
            }
            for i, p in enumerate(prices)
        ],
    })


@pytest.fixture(autouse=True)
def isolated_cache(tmp_path, monkeypatch):
    monkeypatch.setenv("BACKTESTER_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("BACKTESTER_STATE_DIR", str(tmp_path / "state"))
    yield tmp_path


# ---------------------------------------------------------------------------
# Single-call fetch
# ---------------------------------------------------------------------------


class TestFetchSingleCall:
    def test_fetch_writes_parquet(self):
        with patch("subprocess.run", return_value=_completed(_kline_payload([100, 101, 102]))):
            result = data_fetcher.fetch(
                token="So11111111111111111111111111111111111111112",
                chain="solana", bar="1D", symbol="WSOL",
            )
        assert result["ok"] is True
        assert result["rows"] == 3
        assert result["api_calls"] == 2  # one to get bars, one that returned dupes (loop end)
        assert Path(result["path"]).exists()
        df = pd.read_parquet(result["path"])
        assert list(df["c"]) == [100.0, 101.0, 102.0]

    def test_cache_hit_no_subprocess(self):
        # First call: writes parquet
        with patch("subprocess.run", return_value=_completed(_kline_payload([100, 101]))):
            r1 = data_fetcher.fetch(token="X", chain="solana", bar="1D", symbol="X1")
        assert r1["cached"] is False

        # Second call: hits cache, no subprocess
        with patch("subprocess.run") as mock_run:
            r2 = data_fetcher.fetch(token="X", chain="solana", bar="1D", symbol="X1")
            assert mock_run.call_count == 0
        assert r2["cached"] is True
        assert r2["api_calls"] == 0
        assert r2["path"] == r1["path"]

    def test_force_bypasses_cache(self):
        with patch("subprocess.run", return_value=_completed(_kline_payload([100]))):
            data_fetcher.fetch(token="X", chain="solana", bar="1D", symbol="X1")
        with patch("subprocess.run", return_value=_completed(_kline_payload([200]))) as mock_run:
            r2 = data_fetcher.fetch(
                token="X", chain="solana", bar="1D", symbol="X1", force=True
            )
            assert mock_run.call_count >= 1
        df = pd.read_parquet(r2["path"])
        assert list(df["c"]) == [200.0]


# ---------------------------------------------------------------------------
# Pagination + dedup
# ---------------------------------------------------------------------------


class TestPagination:
    def test_paginates_until_duplicates(self):
        # First call: 3 fresh bars. Second call: same bars again (dedup → 0 added → loop exits).
        responses = iter([
            _completed(_kline_payload([100, 101, 102], start_ms=1735689600000)),
            _completed(_kline_payload([100, 101, 102], start_ms=1735689600000)),
        ])
        with patch("subprocess.run", side_effect=lambda *a, **k: next(responses)):
            result = data_fetcher.fetch(token="X", chain="solana", bar="1D", symbol="X1")
        assert result["rows"] == 3
        assert result["api_calls"] == 2

    def test_paginates_through_multiple_windows(self):
        # First call: Jan 2, 3, 4 (closes [110, 111, 112]).
        # Second call: Jan 1, 2, 3 (closes [100, 101, 102]) — Jan 2/3 are dups
        # (older Jan 1 is the only addition). Third call: same → 0 added,
        # loop exits.
        responses = iter([
            _completed(_kline_payload([110, 111, 112], start_ms=1735776000000)),
            _completed(_kline_payload([100, 101, 102], start_ms=1735689600000)),
            _completed(_kline_payload([100, 101, 102], start_ms=1735689600000)),
        ])
        with patch("subprocess.run", side_effect=lambda *a, **k: next(responses)):
            result = data_fetcher.fetch(token="X", chain="solana", bar="1D", symbol="X1")
        df = pd.read_parquet(result["path"])
        # 4 unique timestamps total (Jan 1, 2, 3, 4)
        assert len(df) == 4
        # First-occurrence-wins: Jan 2/3 keep first call's prices (110/111),
        # Jan 1 picked up from second call (100), Jan 4 from first (112).
        assert sorted(df["c"]) == [100.0, 110.0, 111.0, 112.0]


# ---------------------------------------------------------------------------
# Failure modes
# ---------------------------------------------------------------------------


class TestFailures:
    def test_auth_error_surfaces(self):
        with patch("subprocess.run",
                   return_value=_completed("", returncode=1,
                                           stderr="OK-ACCESS-KEY missing\n")):
            with pytest.raises(DataFetchError, match="wallet_not_logged_in"):
                data_fetcher.fetch(token="X", chain="solana", bar="1D", symbol="X1")

    def test_cli_not_found(self):
        with patch("subprocess.run", side_effect=FileNotFoundError(2, "ENOENT", "onchainos")):
            with pytest.raises(DataFetchError, match="cli_not_found"):
                data_fetcher.fetch(token="X", chain="solana", bar="1D", symbol="X1")

    def test_timeout_surfaces(self):
        with patch("subprocess.run",
                   side_effect=subprocess.TimeoutExpired(cmd=["onchainos"], timeout=30)):
            with pytest.raises(DataFetchError, match="cli_timeout"):
                data_fetcher.fetch(token="X", chain="solana", bar="1D", symbol="X1")

    def test_invalid_json(self):
        with patch("subprocess.run", return_value=_completed("not-json")):
            with pytest.raises(DataFetchError, match="cli_output_invalid"):
                data_fetcher.fetch(token="X", chain="solana", bar="1D", symbol="X1")


# ---------------------------------------------------------------------------
# Range filter
# ---------------------------------------------------------------------------


class TestRangeFilter:
    def test_start_bound_drops_earlier_bars(self):
        # 5 bars from 2024-12-31 forward; ask for bars on/after 2025-01-02.
        with patch("subprocess.run",
                   return_value=_completed(_kline_payload([100, 101, 102, 103, 104]))):
            result = data_fetcher.fetch(
                token="X", chain="solana", bar="1D", symbol="X1",
                start="2025-01-02T00:00:00Z",
            )
        df = pd.read_parquet(result["path"])
        # 2025-01-01 is the start; with the filter we should keep only bars >= 2025-01-02.
        # Bars 0,1 = 2025-01-01, 2025-01-02. Filter keeps 1..4.
        assert len(df) == 4
