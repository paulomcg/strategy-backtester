---
name: strategy-backtester
description: "Drives portfolio-manager (v0.2.0+) through historical OHLCV. The user/agent authors a Python decide() callback (same shape PM uses in live mode); the backtester replays bars one at a time, feeds synthesized wallet+pnl+market snapshots to PM via its existing --positions-source / --pnl-source / --market-data-source flags, captures fills back into a simulated wallet, then runs pm report at the end for Sharpe / Sortino / max DD / win rate / equity chart. Same strategy.py + rules.yaml work in backtest and live mode — one artifact, two execution contexts. Use when the user says: backtest my strategy, replay history, what would my strategy have done, simulate this on past data, sharpe of my strategy, fetch kline data, cache OHLCV parquet."
version: "0.1.0"
license: MIT
metadata:
  author: paulomcg
  homepage: "https://github.com/paulomcg/strategy-backtester"
---

# Strategy Backtester

A thin OKX environment mock for `portfolio-manager`. Drives PM through
historical bars one at a time using the same data-source flags PM already
consumes for live runs (`--positions-source`, `--pnl-source`,
`--market-data-source`, `--executor synthetic`, `--live`). PM doesn't know
it's in a backtest. The strategy `.py` you write here is the same `.py`
you deploy live — no translation step.

## Pre-flight

1. `command -v backtester` → install via `npx skills add okx/plugin-store
   --skill strategy-backtester` if missing.
2. `command -v pm` → portfolio-manager v0.2.0+ must be on PATH:
   ```
   backtester pm-check
   ```
   should print `{"ok": true, "result": {"pm_bin": "pm", "pm_version": "pm 0.2.0"}}`.
3. For `fetch-data` (real OHLCV from OKX): `OKX_API_KEY` /
   `OKX_SECRET_KEY` / `OKX_PASSPHRASE` must be set (read by `onchainos
   market kline`, never by this skill). For replays against committed
   parquets, no API access is needed.

## The agent-iteration workflow (this is the *product*)

This is what an agent + user actually do with this skill:

> **User**: "Try DCA $50 of WSOL every Monday for the last year, with a
> 25% trailing stop on the position."
>
> **Agent**: drafts `dca-wsol.py` with the `decide()` contract from PM's
> SKILL.md. Drafts a small `rules.yaml` with the trailing stop. Then:
> ```
> backtester fetch-data --token <wsol-addr> --bar 1D \
>   --start 2025-05-12 --end 2026-05-12 \
>   --out ./examples/ohlcv/wsol-1y.parquet
> backtester replay \
>   --ohlcv ./examples/ohlcv/wsol-1y.parquet \
>   --strategy ./dca-wsol.py \
>   --rules ./rules.yaml \
>   --initial-usd 1000 --symbol WSOL \
>   --out ./runs/dca-tts-25
> ```
>
> **Backtester**: loops 365 bars, drives PM through each one, captures
> fills, runs `pm report`.
>
> **Agent**: reads `./runs/dca-tts-25/report.md`, summarizes for user
> ("Sharpe 1.2, max DD 14%, ~52 trades, +18.5% return"), proposes
> tweaks ("loosen the trailing stop to 30%?").
>
> Iterate. When satisfied:
> ```
> pm watch --strategy ./dca-wsol.py --rules ./rules.yaml \
>   --wallet <real-addr> --bar 1D --live --max-loss-usd 200
> ```
> Same `.py` + `.yaml`. No translation, no rewrite.

## Commands

### `backtester fetch-data`

```
backtester fetch-data
    --token <contract-address>
    [--chain solana]
    [--bar 1D]                    # 1m / 5m / 1H / 4H / 1D / 1W
    [--start <iso>] [--end <iso>] # optional ISO 8601 bounds
    [--symbol <label>]            # default: derived from token
    [--out <parquet-path>]        # default: examples/ohlcv/<symbol>-<bar>.parquet
    [--force]                     # bypass cache
```

Walks `onchainos market kline --after <ts>` pagination cursors up to
~1440 bars (OKX DEX kline cap). Dedupes by ts (first occurrence wins).
Cache hit on subsequent calls with the same args returns the existing
parquet path with `api_calls: 0`.

### `backtester replay`

```
backtester replay
    --ohlcv <parquet-path>
    --strategy <py-file>          # PM-compatible decide(state, market_data)
    --rules <yaml-file>           # PM rule config
    --initial-usd 1000
    [--symbol <asset>]            # default: derive from parquet name
    [--chain solana]
    [--out <run-dir>]             # default: state/runs/<run-id>
    [--fees-bps 30] [--slippage-bps 50]
```

Per bar: write `wallet.json` + `pnl.json` + `market.json` snapshots to
`<run-dir>/snapshots/`, subprocess `pm watch --iterations 1` (with
`PM_STATE_DIR=<run-dir>/pm-state` so PM's audit accumulates in isolation),
parse cycle output, apply each fill back to the simulated wallet. After
the loop: rewrite cycle `ts_utc` fields in the audit to bar timestamps
(so `pm report`'s annualized metrics use the bar cadence not wall clock),
then subprocess `pm report --audit-path ... --out <run-dir>/report/`.

Output: `<run-dir>/run.json` (top-level summary), `<run-dir>/report/
{report.json,report.md,equity.png}` (PM's metrics + chart),
`<run-dir>/pm-state/audit.jsonl` (full PM audit log).

### `backtester pm-check`

Sanity-check that `pm --version` runs cleanly. Strips PYTHONPATH from
the subprocess env so PM's launcher can prepend its own root cleanly.

### `backtester cache stats` / `cache clear`

Inspect or clean the parquet cache (`examples/ohlcv/` by default,
overridable via `BACKTESTER_CACHE_DIR`).

## Strategy file (lives in PM territory; the backtester just passes the path)

The `--strategy <py>` you pass to `backtester replay` is a PM strategy file —
identical contract to what `pm watch --strategy <py>` consumes. Minimal:

```python
def decide(state, market_data):
    if state.get("cycle_index", 0) == 0:
        return [{"action": "buy", "asset": "WSOL", "amount_usd": state["cash_usd"]}]
    return []
```

`state` is PM's positions snapshot (cycle_index, cash_usd,
total_equity_usd, positions[]); `market_data` is `{symbol: {current: bar,
history: pd.DataFrame}}`. See PM's SKILL.md "Authoring a strategy" for the
full contract + helpers (`every_n_bars`, `rolling_return`,
`has_position`, etc.).

## Rules file (PM rule config — same in backtest as live)

```yaml
name: my-rules
universe:
  - { chain: solana, address: "So11...1112", symbol: WSOL }
rules:
  - id: trailing-stop
    type: trailing_stop
    pct: 25
    applies_to: "*"
    action: { type: full_exit }
```

The replay loop honors PM's halt / cap / trailing-stop rules just as live
mode does. Rule-driven fills carry `source: "rule"` in the audit; strategy
fills carry `source: "strategy"`.

## Failure vocabulary (canonical FAILED lines)

```
FAILED: pm_not_installed                              # backtester pm-check
FAILED: replay_input_invalid <field>: <reason>        # bad ohlcv / strategy / rules
FAILED: data_fetch_failed cli_not_found <bin>
FAILED: data_fetch_failed wallet_not_logged_in
FAILED: data_fetch_failed cli_timeout <argv>
FAILED: data_fetch_failed cli_output_invalid <reason>
FAILED: data_fetch_failed <generic-cli-error>
FAILED: pm_call_timeout cycle=<idx>
FAILED: not_implemented <subcommand>
FAILED: internal_error <ExceptionName>: <msg>
```

PM-side failures bubble up via `<run-dir>/run.json::cycles[].error`. The
loop continues across PM cycle errors — a bad bar doesn't kill the run.

## Audit format pass-through

The audit log PM writes during a backtest is the same `watch.cycle` v1.0.0
schema PM writes in live mode. Anything that consumes a PM audit log
(`pm report`, future tooling) works on backtest audits unchanged.

## Examples

- `examples/strategies/buy_and_hold_wsol.py` — minimal `decide()` ↔ buys
  once on cycle 0, holds.
- `examples/rules/conservative.yaml` — 30% halt-on-DD, 60% per-position
  cap, 25% trailing stop on every held position. Single-asset universe.
- `tests/fixtures/synthetic_wsol_20d.parquet` — 20 daily bars of synthetic
  WSOL data (price 100 → 133). Used by the no-keys end-to-end test.

## Tests

```
PATH="$HOME/Projects/portfolio-manager/bin:$PATH" .venv/bin/pytest tests/
```

29 tests cover data_fetcher (subprocess mocked), sim_wallet (fill
application, snapshots), and replay (input validation, audit ts rewrite,
end-to-end against the real `pm` binary).
