# strategy-backtester

**Drives [`portfolio-manager`](https://github.com/paulomcg/portfolio-manager)
through historical OHLCV from OnChainOS `market kline`.** The
user/agent authors a Python `decide()` callback (same shape PM uses in
live mode); the backtester replays bars one at a time, feeds PM the
same data shapes it normally consumes from a wallet adapter, captures
fills back into a simulated wallet, then runs `pm report` for Sharpe /
Sortino / max DD / win rate / equity chart.

**The strategy `.py` you write here is the same `.py` you deploy live.**
One artifact, two execution contexts.

---

## What you can do with it

### Backtest a momentum strategy on real Solana OHLCV

```sh
# 1. Pull a year of WSOL daily bars from OKX kline (cached to parquet)
backtester fetch-data \
  --token So11111111111111111111111111111111111111112 \
  --chain solana --bar 1D \
  --start 2025-05-12 --end 2026-05-12 \
  --symbol WSOL \
  --out ./examples/ohlcv/wsol-1y.parquet

# 2. Replay your strategy against it
backtester replay \
  --ohlcv ./examples/ohlcv/wsol-1y.parquet \
  --strategy examples/strategies/momentum_threshold.py \
  --rules examples/rules/conservative.yaml \
  --initial-usd 1000 --symbol WSOL \
  --fees-bps 30 --slippage-bps 50
```

Output — one JSON record per replay run, with every fill captured:

```json
{"ok": true, "result": {
  "run_id": "20260520T125805Z-1ccf95",
  "bars_processed": 299,
  "fills_total": 23,
  "pm_call_failures": 0,
  "final_equity_usd": 961.02,
  "report_summary": {
    "metrics_summary": {
      "total_return_pct": -3.61,
      "sharpe": -3.36,
      "max_drawdown_pct": 8.98
    }
  },
  "report_path": "./state/runs/20260520T125805Z-1ccf95/report/report.json"
}}
```

### Backtest multi-asset portfolios with intersection-of-timestamps replay

```sh
backtester replay \
  --ohlcv ./cache/JTO-1H.parquet,./cache/JUP-1H.parquet \
  --symbol JTO,JUP \
  --strategy ./mtf_momentum.py \
  --rules examples/rules/conservative.yaml \
  --initial-usd 5000 \
  --fees-bps 30 --slippage-bps 50
```

The replayer walks the intersection of all asset timestamps so the
strategy gets a consistent multi-asset cross-section every bar.

### Open the interactive HTML report

Every run writes a self-contained `report.html` to the output dir:

```sh
open ./state/runs/20260520T125805Z-1ccf95/report/report.html
```

React + Recharts single-file bundle — equity curve with drawdown
shade, fills timeline with color-coded buy/sell badges, per-asset
realized-PnL attribution, the full per-cycle decision trace. No
server, no build step, opens in any browser.

A committed demo lives at
[`examples/demo-run/report.html`](examples/demo-run/report.html) so
you can preview without running anything.

### Compare a strategy to a hold-baseline

```sh
# Strategy run
backtester replay --strategy ./my-dca.py --rules rules.yaml \
  --ohlcv wsol-1y.parquet --initial-usd 1000 \
  --out ./runs/dca

# Buy-and-hold reference
backtester replay --strategy examples/strategies/buy_and_hold_wsol.py \
  --rules examples/rules/conservative.yaml \
  --ohlcv wsol-1y.parquet --initial-usd 1000 \
  --out ./runs/hold

# Diff the metrics
diff <(jq .metrics_summary ./runs/dca/report.json) \
     <(jq .metrics_summary ./runs/hold/report.json)
```

### Use the SAME strategy live without re-authoring

```sh
# BACKTEST
backtester replay --strategy ./dca-wsol.py --rules ./rules.yaml \
                  --ohlcv ./wsol-1y.parquet --initial-usd 1000

# LIVE (same .py + .yaml)
pm watch --strategy ./dca-wsol.py --rules ./rules.yaml \
         --wallet <real-addr> --live --max-loss-usd 50
```

The strategy file doesn't know it's running against historical or live
data. PM doesn't know whose wallet snapshot it's reading. The
backtester is just a smart driver.

### Inspect + manage the OHLCV cache

```sh
backtester cache stats
```

```json
{"ok": true, "result": {
  "count": 4,
  "total_rows": 1798,
  "total_size_bytes": 122_456,
  "entries": [
    {"symbol": "WSOL", "bar": "1H", "rows": 720, "ts_min": "...", "ts_max": "..."}
  ]
}}
```

Re-render an interactive HTML report for an older run without re-running:

```sh
backtester report-html --run-dir ./state/runs/20260520T125805Z-1ccf95
```

### Use it from Claude Code / Codex / a custom agent

| Method | Path |
|---|---|
| Drop into Claude Code's skills dir | `cp -r . ~/.claude/skills/strategy-backtester/` then restart Claude |
| Point a custom agent at SKILL.md | parse YAML frontmatter; shell out to `bin/backtester` per command |
| Register with the OKX Plugin Store | `plugin.yaml` schema_version: 1 |

Every command emits `{"ok": bool, "result": {...}}` JSON on stdout.
Errors print `FAILED: <category> <detail>` to stderr with stable
machine-parseable categories.

---

## Install

```sh
# 1. Install portfolio-manager first (the backtester subprocess-drives it)
git clone https://github.com/paulomcg/portfolio-manager.git ~/Projects/portfolio-manager
cd ~/Projects/portfolio-manager && ./install.sh
echo 'export PATH="$HOME/Projects/portfolio-manager/bin:$PATH"' >> ~/.bashrc

# 2. Then the backtester
git clone https://github.com/paulomcg/strategy-backtester.git ~/Projects/strategy-backtester
cd ~/Projects/strategy-backtester && ./install.sh
echo 'export PATH="$HOME/Projects/strategy-backtester/bin:$PATH"' >> ~/.bashrc

# 3. Verify the companion pm is reachable
backtester pm-check
```

For `fetch-data` against real OKX kline:

```sh
export OKX_API_KEY=... OKX_SECRET_KEY=... OKX_PASSPHRASE=...
```

The backtester itself never reads those env vars — they're consumed by
the underlying `onchainos market kline` CLI when `fetch-data` invokes
it.

---

## Architecture

```
        ┌──────────────────────────────────────────────────────┐
        │  strategy.py + rules.yaml                            │
        │  (agent-authored artifacts; same files for           │
        │   backtest AND live)                                 │
        └──────────────────────────────────────────────────────┘
                   │                                  │
        ┌──────────┘                                  └──────────┐
        ▼                                                        ▼
┌─────────────────────────────┐                       ┌──────────────────┐
│  backtester replay loop     │                       │  pm watch (live) │
│  (this skill)               │                       │  poll wallet on  │
│                             │                       │  a schedule, run │
│  for bar in parquet:        │                       │  decide() per    │
│    sim_wallet.update_mark   │                       │  cycle           │
│    write wallet+pnl+market  │                       └──────────────────┘
│      JSON snapshots         │
│    subprocess `pm watch`    │  ←── same `pm watch` cycle code
│      --iterations 1         │      path as live mode
│      --executor synthetic   │
│    apply fills →            │
│      sim_wallet             │
│  rewrite audit ts to bar ts │
│  subprocess `pm report`     │
└─────────────────────────────┘
```

### Core invariants

- **PM does the heavy lifting.** PM owns the strategy hook, rule
  engine, executor abstraction, audit log, and metrics. The backtester
  only does what PM doesn't: stream historical OHLCV in, capture
  fills out, rewrite audit timestamps to bar timestamps so annualized
  metrics use the right cadence.
- **PM doesn't know it's in a backtest.** Same `pm watch` binary,
  same code path, same audit format. The only difference is the
  `--executor synthetic` flag (which PM already supports for paper
  trading) and the synthesized wallet/market snapshots fed in via
  PM's existing `--positions-source` / `--pnl-source` /
  `--market-data-source` flags.
- **OHLCV cache is parquet on disk.** Subsequent `fetch-data` calls
  with the same `(token, chain, bar)` triple hit the cache. Override
  with `--force` to re-fetch.

### Failure vocabulary

| Situation | Token |
|---|---|
| `pm` not installed / not on PATH | `pm_not_installed` |
| Bad parquet / strategy / rules path | `replay_input_invalid` |
| OKX kline auth error | `data_fetch_failed wallet_not_logged_in` |
| onchainos CLI missing | `data_fetch_failed cli_not_found` |
| onchainos CLI timeout | `data_fetch_failed cli_timeout` |
| onchainos returned non-JSON / errored | `data_fetch_failed cli_output_invalid` |
| PM watch subprocess timed out | `pm_call_timeout cycle=<idx>` |
| Catch-all | `internal_error <ExceptionName>: <msg>` |

PM-side failures (mid-cycle errors) bubble up to
`<run-dir>/run.json::cycles[].error`. A single bad bar never kills
the run — the loop keeps going across them.

### Files

| File | Role |
|---|---|
| `scripts/backtester.py` | CLI dispatcher (`replay`, `fetch-data`, `cache stats/clear`, `report-html`, `pm-check`) |
| `scripts/replay.py` | Replay loop — drives PM per bar, captures fills, rewrites audit timestamps |
| `scripts/data_fetcher.py` | `onchainos market kline` → parquet cache |
| `scripts/sim_wallet.py` | In-memory ledger that mimics OnChainOS wallet responses |
| `scripts/html_report.py` | Renders the interactive single-file HTML report |
| `scripts/config.py` | Paths overridable via env vars |
| `examples/demo-run/` | Pre-rendered demo report (open `report.html` in a browser) |
| `examples/ohlcv/` | Sample parquet files (SOL/JTO/JUP) for offline runs |
| `examples/rules/` | Sample rule configs to drive PM with |

### Tests

```sh
PATH="$HOME/Projects/portfolio-manager/bin:$PATH" .venv/bin/pytest tests/
```

Covers data-fetcher subprocess invocation, simulated-wallet fill
semantics (buy aggregates, sell pro-rata cost basis, mark-to-market),
input validation, audit-ts rewriting, and end-to-end against a real
`pm` binary (skipped if pm isn't on PATH).

---

## License

MIT — see [`LICENSE`](LICENSE).

## Disclaimer

Backtest results are simulations. Past performance is not predictive
of future results. Validate strategies in monitor mode AND across
multiple regimes before going live with real capital. Use
`--max-loss-usd` aggressively. The authors disclaim all liability.
