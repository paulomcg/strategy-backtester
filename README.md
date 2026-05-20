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

Every replay run writes a self-contained interactive HTML report
(React + Recharts, single file, no server, no build step). The
agent opens it directly in the user's browser — or serves it on
the tailnet so the user can view from any device.

Equity curve with drawdown shading, fills timeline with color-coded
buy/sell/exit badges, per-asset realized-PnL attribution, full
per-cycle decision trace. See the [Reports](#reports) section below
for a walkthrough, and the bundled
[`examples/demo-run/`](examples/demo-run/) for a pre-computed run
you can preview without running anything.

---

> **"Backtest a multi-asset rotation on JTO + JUP."**

User provides one `.py` strategy that consumes
`market_data['JTO']` + `market_data['JUP']`; the agent points the
backtester at two parquet files in parallel. The replay loop walks
the intersection of timestamps so the strategy sees a consistent
cross-section each bar.

---

> **"Re-render the HTML report for last week's run."**

The agent finds the run dir and re-renders the single-file bundle
against the current report template. Useful when the template has
improved since the original run — no need to re-burn the OHLCV.

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

## Reports

<img width="1376" height="1032" alt="report" src="https://github.com/user-attachments/assets/c44d1266-862f-4c9d-b2d3-35e6d2d1ae73" />

Every replay run writes its output to a self-contained dir at
`state/runs/<run-id>/report/`:

```
report/
├── report.html      ← interactive single-file React bundle (~700KB)
├── report.json      ← computed metrics + every fill + cycle equity series
├── report.md        ← human-readable summary
└── equity.png       ← static equity curve with drawdown shading
```

`report.html` is the headline artifact. Open it in any browser:

```sh
open state/runs/<run-id>/report/report.html
# or serve over tailnet:
python3 -m http.server 7778 --directory state/runs/
```

What you see:

- **Headline metrics card** — initial / final equity, total return,
  CAGR, Sharpe, Sortino, Calmar, max drawdown, win rate, expectancy.
- **Equity curve** — line chart with shaded drawdown regions; hover
  for the value + drawdown at any timestamp.
- **Fills timeline** — chronological list of every buy / sell /
  exit / trim with action color-coding, qty, fill price, and
  realized PnL.
- **Per-asset attribution** — breaks total realized PnL down by
  asset so you see which legs of a multi-asset strategy actually
  contributed.
- **Per-cycle decision trace** — what the rule engine evaluated
  on each bar, which rules fired (or didn't), which fills happened.
  Drill-down for debugging why a backtest behaved the way it did.

A pre-computed demo lives at
[`examples/demo-run/`](examples/demo-run/) — 299 bars of 1H WSOL
under buy-and-hold with a 25% trailing stop. Open the `report.html`
to see the full report shape without running anything yourself.

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
| `scripts/backtester.py` | CLI dispatcher (`replay`, `fetch-data`, `cache stats/clear`, `report-html`, `pm-check`) |
| `scripts/replay.py` | Replay loop — drives PM per bar, captures fills, rewrites audit timestamps |
| `scripts/data_fetcher.py` | `onchainos market kline` → parquet cache |
| `scripts/sim_wallet.py` | In-memory ledger that mimics OnChainOS wallet responses |
| `scripts/html_report.py` | Renders the interactive single-file HTML report (React + Recharts) |
| `scripts/config.py` | Paths overridable via env vars |
| `examples/demo-run/` | Pre-computed demo report.html + report.json + equity.png |
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
