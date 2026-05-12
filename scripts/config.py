"""Defaults + path resolution for the strategy-backtester skill.

Most paths can be overridden via environment variables so tests + users can
isolate state.
"""

from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Default location for the PM CLI binary.  When unset we fall back to the
# user's PATH ("pm" must already be installed).
PM_BIN_DEFAULT = "pm"

# Default chain for fetch / replay.  The contest is Solana + XLayer.
CHAIN_DEFAULT = "solana"

# Default candle bar — daily is the sweet spot given OKX DEX kline pagination.
BAR_DEFAULT = "1D"

# Where pre-warmed parquet cache + per-run state lives.
def state_dir() -> Path:
    p = Path(os.environ.get("BACKTESTER_STATE_DIR", ROOT / "state"))
    p.mkdir(parents=True, exist_ok=True)
    return p


def cache_dir() -> Path:
    p = Path(os.environ.get("BACKTESTER_CACHE_DIR", ROOT / "examples" / "ohlcv"))
    p.mkdir(parents=True, exist_ok=True)
    return p


def runs_dir() -> Path:
    p = Path(os.environ.get("BACKTESTER_RUNS_DIR", state_dir() / "runs"))
    p.mkdir(parents=True, exist_ok=True)
    return p


def pm_bin() -> str:
    return os.environ.get("BACKTESTER_PM_BIN", PM_BIN_DEFAULT)
