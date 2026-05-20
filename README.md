# strategy-backtester

> **OKX Agentic Trading Contest, Skill Quality Award submission** — see
> [`SUBMISSION.md`](./SUBMISSION.md) for the explicit mapping of features
> to the five evaluation criteria (strategy completeness, risk control,
> execution reliability, user safety/onboarding, observability).

**A thin OKX environment mock that drives `portfolio-manager` through
historical OHLCV.** The user/agent authors a Python `decide()` callback;
the backtester replays bars one at a time, feeds PM the same data shapes
it normally consumes from `okx-wallet-portfolio` + `okx-dex-market` in
live mode, captures fills back into a simulated wallet, then runs
`pm report` for Sharpe / Sortino / max DD / win rate / equity chart.

**The strategy `.py` you write here is the same `.py` you deploy live.**
One artifact, two execution contexts.

> Status: v0.1.0 — submitted to the OKX Agentic Trading Contest (May 2026).
> Composes with [portfolio-manager](https://github.com/paulomcg/portfolio-manager)
> v0.2.0+. MIT licensed. Not investment advice. Test in monitor mode
> before going live.

---

## Why this is right

The earlier wrong-headed designs put a strategy framework, simulator,
metrics computation, and equity tracking into the backtester — duplicating
what PM already does. **PM does the heavy lifting.** PM owns:

- The strategy hook (`pm watch --strategy <py>` runs `decide()` per cycle)
- The rule engine (drawdown halts / position caps / trailing stops)
- The executor abstraction (synthetic for paper / onchainos for live)
- The audit log + `pm report` (metrics + chart + Markdown)

The backtester only does what PM doesn't:

- Streams historical OHLCV into PM's existing `--positions-source` /
  `--pnl-source` / `--market-data-source` flags
- Maintains a small in-memory `SimulatedWallet` that responds to the
  fills PM emits each cycle
- Subprocess-drives PM at `--iterations 1` per bar
- Rewrites cycle `ts_utc` fields to bar timestamps so `pm report`'s
  annualized metrics use the bar cadence
- At the end, calls `pm report` against the accumulated audit

PM doesn't know it's in a backtest. Same code path as live.

---

## Architecture

```
            ┌──────────────────────────────────────────────────────┐
            │  strategy.py + rules.yaml  (the agent-authored       │
            │  artifacts; same files work backtest AND live)       │
            └──────────────────────────────────────────────────────┘
                       │                                  │
        ┌──────────────┘                                  └──────────┐
        ▼                                                            ▼
┌────────────────────────────┐                            ┌──────────────────────┐
│  backtester replay loop    │                            │  pm watch (live)     │
│  (this skill)              │                            │  poll wallet on a    │
│                            │                            │  schedule, run       │
│  for bar in parquet:       │                            │  decide() per cycle  │
│    sim_wallet.update_mark  │                            └──────────────────────┘
│    write wallet+pnl+market │
│      JSON snapshots        │
│    subprocess pm watch     │ ◀────── exact same `pm watch` cycle code path
│      --iterations 1        │         pm v0.1.0 already runs in live monitor
│      --executor synthetic  │
│    apply fills →           │
│      sim_wallet            │
│  rewrite audit ts          │
│  subprocess pm report      │
└────────────────────────────┘
```

---

## Install

### From the OKX Plugin Store (once curated)

```sh
npx skills add okx/plugin-store --skill portfolio-manager
npx skills add okx/plugin-store --skill strategy-backtester
```

### From source (today)

```sh
# Install portfolio-manager first (the backtester depends on `pm` on PATH)
git clone https://github.com/paulomcg/portfolio-manager.git ~/Projects/portfolio-manager
cd ~/Projects/portfolio-manager
python3 -m venv .venv && .venv/bin/pip install jsonschema pyyaml pytest pandas numpy matplotlib pyarrow
echo 'export PATH="$HOME/Projects/portfolio-manager/bin:$PATH"' >> ~/.bashrc

# Then the backtester
git clone https://github.com/paulomcg/strategy-backtester.git ~/Projects/strategy-backtester
cd ~/Projects/strategy-backtester
python3 -m venv .venv && .venv/bin/pip install pandas numpy pyarrow pytest pyyaml
echo 'export PATH="$HOME/Projects/strategy-backtester/bin:$PATH"' >> ~/.bashrc

# Verify
backtester pm-check
```

For `fetch-data` against real OKX kline data, you'll also need:

```sh
export OKX_API_KEY=... OKX_SECRET_KEY=... OKX_PASSPHRASE=...
```

The backtester itself never reads those env vars — they're consumed by the
underlying `onchainos market kline` CLI when `fetch-data` invokes it.

---

## 60-second demo (no keys, no capital)

The repo ships a 20-day synthetic WSOL parquet so the demo runs offline:

```sh
backtester replay \
  --ohlcv tests/fixtures/synthetic_wsol_20d.parquet \
  --strategy examples/strategies/buy_and_hold_wsol.py \
  --rules examples/rules/conservative.yaml \
  --initial-usd 1000 --symbol WSOL \
  --out ./run-demo
```

Result on the bundled synthetic data:

```
{"ok": true, "result": {
  "run_id": "20260512T003504Z-3358ff",
  "bars_processed": 20,
  "fills_total": 15,
  "pm_call_failures": 0,
  "final_equity_usd": 1176.02,
  "report_summary": {
    "metrics_summary": {
      "bars": 20,
      "total_return_pct": 17.96,
      "cagr_pct": 2288.5,         // huge because 17.96% over 20d annualized
      "sharpe": 8.89,
      "sortino": 46.36,
      "max_drawdown_pct": 2.13
    }
  }
}}
```

Then open:

```sh
cat ./run-demo/report/report.md           # human-readable summary
open ./run-demo/report/equity.png         # equity curve + drawdown shading
```

---

## Real OHLCV walkthrough (with API keys)

```sh
# 1. Fetch 1 year of WSOL daily bars (paginates --after through OKX kline)
backtester fetch-data \
  --token So11111111111111111111111111111111111111112 \
  --chain solana --bar 1D \
  --start 2025-05-12 --end 2026-05-12 \
  --symbol WSOL \
  --out ./examples/ohlcv/wsol-1y.parquet

# 2. Replay your strategy against it
backtester replay \
  --ohlcv ./examples/ohlcv/wsol-1y.parquet \
  --strategy ./my-dca.py \
  --rules ./my-rules.yaml \
  --initial-usd 1000 --symbol WSOL \
  --out ./runs/dca-1y
```

Subsequent `fetch-data` calls hit the parquet cache — `api_calls: 0`.
Override with `--force` to re-fetch.

---

## Same artifact, two execution contexts

```sh
# BACKTEST
backtester replay --strategy ./dca-wsol.py --rules ./rules.yaml \
                  --ohlcv ./wsol-1y.parquet --initial-usd 1000

# LIVE (same .py + .yaml)
pm watch --strategy ./dca-wsol.py --rules ./rules.yaml \
         --wallet <real-addr> --live --max-loss-usd 200
```

The strategy file doesn't know it's running against historical or live
data. PM doesn't know whose wallet snapshot it's reading. The backtester
is just a smart driver.

---

## Failure vocabulary

| Situation | Canonical token |
|---|---|
| `pm` not installed / not on PATH | `pm_not_installed` |
| Bad parquet / strategy / rules path | `replay_input_invalid` |
| OKX kline auth error | `data_fetch_failed wallet_not_logged_in` |
| onchainos CLI missing | `data_fetch_failed cli_not_found` |
| onchainos CLI timeout | `data_fetch_failed cli_timeout` |
| onchainos returned non-JSON / errored | `data_fetch_failed cli_output_invalid` |
| PM watch subprocess timed out | `pm_call_timeout cycle=<idx>` |
| Catch-all | `internal_error <ExceptionName>: <msg>` |

PM-side failures (mid-cycle errors) bubble up to `<run-dir>/run.json::cycles[].error`.
The loop keeps going across them — a single bad bar never kills the run.

---

## Tests

```sh
PATH="$HOME/Projects/portfolio-manager/bin:$PATH" .venv/bin/pytest tests/
```

29 tests:
- `test_data_fetcher.py` — subprocess-mocked kline pagination, dedup,
  cache hit, force-bypass, auth/timeout/cli-not-found failures, range
  filter
- `test_sim_wallet.py` — fill application semantics (buy aggregates, sell
  pro-rata cost basis, halt no-op, mark-to-market), snapshot shapes
- `test_replay.py` — input validation, audit-ts rewrite, end-to-end
  against real `pm` binary (skipped if pm isn't on PATH)

---

## License

MIT — see [`LICENSE`](LICENSE).

---

## Disclaimer

Backtest results are synthetic. Past performance ≠ future results.
Validate strategies in monitor mode AND across multiple regimes before
going live with real capital. Use `--max-loss-usd` aggressively. The
authors disclaim all liability.
