# Submission — OKX Agentic Trading Contest, Skill Quality Award Track

**Skill name:** `strategy-backtester`
**Submitted by:** Paulo Goncalves
**OnChainOS as primary data source:** ✅ (`onchainos market kline` for OHLCV; companion `portfolio-manager` skill uses `onchainos wallet` + `onchainos swap`)
**Status:** v0.1.0, paired with `portfolio-manager`

The thesis: **the strategy `.py` you backtest is the same `.py` you deploy
live.** This skill is the deterministic-replay companion to
`portfolio-manager` — one strategy artifact, two execution contexts. This
document maps each of the contest's five evaluation criteria to a concrete
feature, file, and verification path.

---

## 1. Strategy completeness

The backtester does not own a strategy framework — it drives PM's strategy
framework against historical data. That means:

| What | Where |
|---|---|
| `decide(state, market_data) → list[Action]` lives in PM, runs unchanged here | PM's `scripts/strategy.py` |
| Multi-asset replay — intersection-of-timestamps replay across N parquets | `scripts/replay.py` |
| Fees + slippage propagated to PM's synthetic executor for honest results | `scripts/replay.py`, `--fees-bps` / `--slippage-bps` |
| Per-bar cycle audit including positions, decisions, fills, equity | Audit JSONL emitted by PM, consumed at end-of-run |
| Same rule engine (trailing_stop, halt_on_drawdown, max_position_pct) as live | PM `scripts/risk_rules.py` — backtester runs PM, not a reimplementation |

**Evidence — multi-asset replay command:**
```sh
backtester replay \
  --ohlcv cache/JTO-1H.parquet,cache/JUP-1H.parquet \
  --symbol JTO,JUP \
  --strategy ../portfolio-manager/examples/strategies/momentum.py \
  --rules ../portfolio-manager/examples/rules/conservative.yaml \
  --initial-usd 1000 \
  --fees-bps 30 --slippage-bps 50
```

---

## 2. Risk control framework

By design, the backtester inherits PM's full risk-control surface — every
rule, kill-switch, and audit feature available at runtime is available in
the backtest. The synthetic-executor path makes risk-control demos
zero-risk to run repeatedly.

| Control | Inherited from | Notes |
|---|---|---|
| `halt_on_drawdown` | PM `risk_rules.py` | Tested via backtest against rugged-token OHLCV |
| `trailing_stop` | PM `risk_rules.py` | Per-position HWM tracking persists across bars |
| `max_position_pct` | PM `risk_rules.py` | Size-cap behavior identical to live |
| `--max-loss-usd` | PM watch loop | Enforces in synthetic mode too |
| `--max-wallet-loss-usd` | PM watch loop (NEW) | Wallet-equity kill, available in backtest |
| Cost-basis P&L accounting | PM `positions.py` | Same math as live |

**Why this matters for judging:** a strategy that passes the backtest with
risk controls active passes them in the same way at runtime. There is no
"backtest-only" rule that quietly disappears in production.

---

## 3. Execution reliability

The backtester is the place to validate reliability without burning
capital. It exercises PM's full subprocess-driven cycle, including swap
execution, error handling, and ledger updates.

| What | Where |
|---|---|
| Deterministic timestamp rewriting so `pm report` annualized metrics use bar cadence | `scripts/replay.py` (audit ts rewrite step) |
| Subprocess-driven PM at `--iterations 1` per bar — same code path as live | `scripts/replay.py` |
| `SimulatedWallet` in-memory ledger that mimics OnChainOS wallet responses | `scripts/sim_wallet.py` |
| Synthetic-executor path that simulates fills with configurable fees/slippage | PM `scripts/executor.py` (synthetic mode) |
| Graceful handling of OnChainOS API failures during `fetch-data` (`wallet_not_logged_in`, etc.) | `scripts/data_fetcher.py:150-160` |
| OHLCV parquet cache so backtests don't re-pay for the same data | `scripts/data_fetcher.py`, `cache_stats`, `cache_clear` |

---

## 4. User safety + onboarding experience

| What | Where |
|---|---|
| Quickstart in README: install → `backtester pm-check` → `backtester fetch-data` → `backtester replay` | `README.md` |
| `pm-check` subcommand — verifies the companion PM CLI is installed + functional before any other operation | `scripts/backtester.py:108-134` |
| Clear error vocabulary: `pm_not_installed`, `data_fetch_failed wallet_not_logged_in`, `cache_clear_no_target`, `run_dir_not_found` | `scripts/backtester.py`, `scripts/data_fetcher.py` |
| No live capital required to evaluate — backtests are read-only against the OHLCV cache | core design |
| `cache stats` / `cache clear` subcommands — operators can introspect + manage their data | `scripts/backtester.py:138-216` |
| `report-html` subcommand — regenerate the interactive report for any existing run dir without re-running the backtest | `scripts/backtester.py:225-239` |
| Plugin manifest for skill registry | (in repo root if/when published to plugin store) |

---

## 5. Observability

The single highest-leverage observability artifact is the interactive HTML
report — one file you can open in any browser, with equity curve,
drawdown, fills timeline, per-position attribution, and the cycle-by-cycle
log.

| What | Where |
|---|---|
| Single-file HTML report (React + shadcn + Recharts) — equity, drawdown, fills, per-position attribution | `scripts/html_report.py`, `scripts/report_template.html` |
| `report-html` regen path so old runs can use the latest template | `scripts/backtester.py:225-239` |
| `cache stats` — list all cached parquets, row counts, time ranges, disk size | `scripts/backtester.py:138-181` |
| Per-cycle JSONL audit (inherited from PM) | PM `scripts/audit.py` |
| Run output dir with `run.json` (config + summary), `report/report.json` (computed metrics), `report/report.html` (interactive) | `scripts/replay.py` |
| JSON result envelope (`{"ok": true, "result": ...}`) on every command for programmatic consumers | `scripts/backtester.py:25-30` |

**Evidence:** every backtest run writes a self-contained dir at
`state/runs/<run-id>/` with `report.html` openable in any modern browser
— no server, no build step.

---

## Companion skill

This backtester is the deterministic-replay sibling of `portfolio-manager`.
The PM submission's `SUBMISSION.md` covers the live execution side; this
one covers the historical validation side. Together they let an agent
author a strategy ONCE and exercise it in both contexts.

## License

MIT.
