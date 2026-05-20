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

## What you can ask the agent to do

Natural-language prompts the user says, and what the agent does with
them.

---

> **"Backtest my momentum strategy on a year of WSOL data."**

The agent grabs the user's strategy `.py` + rules `.yaml`, fetches
a year of WSOL 1H bars via OnChainOS kline (cached to parquet so
the next backtest is free), runs the replay loop bar-by-bar through
`pm watch`, captures every fill into a simulated wallet, then runs
the metrics engine against the resulting audit. The user gets back
the headline numbers — Sharpe, Sortino, max DD, win rate, total
return, CAGR, expectancy — plus the per-cycle decision trace if
they want to drill in.

---

> **"How does buy-and-hold compare to my DCA on the same window?"**

Two replay runs against the same OHLCV parquet — one with the
user's DCA strategy, one with the bundled `buy_and_hold_wsol.py`.
The agent diffs the metrics from each `report.json` and surfaces
the head-to-head: total return, max DD, Sharpe, fills count. No
human-readable report-shuffling — the agent eats its own JSON.

---

> **"Show me what happened in that backtest."**

The agent reads the per-cycle JSONL audit produced by the run and
walks the user through it: every fill (action, asset, qty, price,
realized PnL), every rule that fired, the equity at each cycle,
and the drawdown path. All structured data — the agent can summarize
at any altitude the user asks for.

---

> **"Backtest a multi-asset rotation on JTO + JUP."**

User provides one `.py` strategy that consumes
`market_data['JTO']` + `market_data['JUP']`; the agent points the
backtester at two parquet files in parallel. The replay loop walks
the intersection of timestamps so the strategy sees a consistent
cross-section each bar.

---

> **"Run this same strategy live."**

The strategy `.py` the user backtested IS the artifact for live
deployment. The agent hands it to the companion
[`portfolio-manager`](https://github.com/paulomcg/portfolio-manager)
skill. PM doesn't know it was backtested; the backtester didn't
know it was simulated. One artifact, two execution contexts.

---

> **"Fetch a year of historical kline for WBTC on Base."**

The agent invokes `backtester fetch-data`, which streams the kline
data via OnChainOS `market kline` into a parquet on disk.
Subsequent backtests on the same `(token, chain, bar)` triple hit
the cache (zero API calls). The user can ask for parquet stats
anytime: *"how much kline do I have cached?"*

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

### Wiring into an agent (Claude Code, Codex, custom harness)

| Method | Path |
|---|---|
| Drop into Claude Code's skills dir | `cp -r . ~/.claude/skills/strategy-backtester/` then restart Claude |
| Point a custom agent at SKILL.md | parse YAML frontmatter; shell out to `bin/backtester` per command |
| Register with the OKX Plugin Store | `plugin.yaml` schema_version: 1 |

Every command emits `{"ok": bool, "result": {...}}` JSON on stdout.
Errors print `FAILED: <category> <detail>` to stderr with stable
machine-parseable categories. The companion `portfolio-manager`
skill must be installed first — the backtester subprocess-drives
`pm` per bar, so its `bin/` must be on PATH.

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
| `scripts/backtester.py` | CLI dispatcher (`replay`, `fetch-data`, `cache stats/clear`, `pm-check`) |
| `scripts/replay.py` | Replay loop — drives PM per bar, captures fills, rewrites audit timestamps |
| `scripts/data_fetcher.py` | `onchainos market kline` → parquet cache |
| `scripts/sim_wallet.py` | In-memory ledger that mimics OnChainOS wallet responses |
| `scripts/config.py` | Paths overridable via env vars |
| `examples/demo-run/` | Pre-computed demo run output (run summary + per-cycle audit) |
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
