## Overview

`strategy-backtester` is a thin OKX environment mock that drives
[`portfolio-manager`](https://github.com/paulomcg/portfolio-manager) (v0.2.0+)
through historical OHLCV. The user converses with their agent (Claude Code,
Hermes, etc.) to draft a Python `decide()` callback. The backtester replays
historical bars one at a time, synthesizes the same wallet + per-token PnL +
market data snapshots PM normally consumes from `okx-wallet-portfolio` /
`okx-dex-market` in live mode, captures the fills PM emits back into a
simulated wallet, and at the end runs `pm report` against the accumulated
audit log to produce Sharpe / Sortino / max DD / win rate / equity curve.

**PM doesn't know it's in a backtest.** The whole interface is the same
synthetic-source flags PM v0.1.0 already exposes (`--positions-source`,
`--pnl-source`, `--market-data-source`, `--executor synthetic`, `--live`).

The same `strategy.py` + `rules.yaml` work in live mode (`pm watch --strategy
... --wallet ... --live ...`) and backtest mode — one artifact, two
execution contexts.

Core operations:

- `backtester fetch-data` — pull OHLCV from `onchainos market kline`,
  paginate via `--after` cursors, dedup by ts, cache to parquet.
- `backtester replay` — for each bar: refresh sim_wallet marks, write
  wallet+pnl+market snapshots, subprocess `pm watch --iterations 1`,
  apply returned fills back into the wallet. After loop: `pm report`.
- `backtester pm-check` — verify `pm` is on PATH and functional.
- `backtester cache stats` / `clear` — manage the parquet cache.

Tags: `backtest` `paper-trading` `solana` `onchainos` `portfolio-manager`
`strategy-validation` `sharpe`

## Prerequisites

- Supported chain (v1): **Solana**.
- `onchainos` CLI installed (`onchainos --version`) — needed only for
  `fetch-data`. Replays against a committed parquet need no API access.
- `portfolio-manager` v0.2.0+ installed and on PATH (`pm --version` reports
  `pm 0.2.0`). The replay loop subprocess-shells `pm watch` and `pm report`.
- Python 3.10+ + pandas, numpy, pyarrow, matplotlib, pytest, pyyaml
  (auto-installed by the venv when you `pip install` this repo).

## Quick Start

1. **Install both skills** (if not already):
   ```
   npx skills add okx/plugin-store --skill portfolio-manager
   npx skills add okx/plugin-store --skill strategy-backtester
   ```
2. **Smoke check that PM is reachable**:
   ```
   backtester pm-check
   ```
3. **Replay a buy-and-hold strategy against the bundled 20-day synthetic
   WSOL parquet** (no keys needed):
   ```
   backtester replay \
     --ohlcv tests/fixtures/synthetic_wsol_20d.parquet \
     --strategy examples/strategies/buy_and_hold_wsol.py \
     --rules examples/rules/conservative.yaml \
     --initial-usd 1000 --symbol WSOL \
     --out ./run1
   ```
4. **Open** `./run1/report/report.md` for metrics + embedded equity chart.
5. **Iterate**: agent + user tweak the `.py` file (or rules YAML), re-run,
   compare report.md.
6. **When happy, deploy live**: same `.py` works under `pm watch --strategy
   <file> --wallet <addr> --live --max-loss-usd N`.
