# Demo backtest output

This directory contains a real backtest result produced by the
`strategy-backtester` skill. **Open `report.html` in any browser** for the
interactive view — no server, no build, no extra deps.

## Reproduce

```sh
# from the strategy-backtester repo root, with the companion
# portfolio-manager skill installed and `pm` on PATH:
backtester replay \
  --ohlcv examples/ohlcv/SOL-1H.parquet \
  --symbol WSOL \
  --strategy examples/strategies/buy_and_hold_wsol.py \
  --rules examples/rules/conservative.yaml \
  --initial-usd 1000 \
  --fees-bps 30 --slippage-bps 50
```

## What this run shows

- **299 bars** of 1H WSOL OHLCV (about 12.5 days)
- **23 closed trades** — the strategy says "buy and hold," but the rule
  engine's 25% trailing-stop kept exiting and the strategy kept re-buying
  on the next cycle. This is intentional honest behavior: the trailing
  stop is too tight for hourly WSOL noise, and the report makes that
  obvious at a glance.
- **78% win rate** but **-3.61% total return** — most trades win small,
  a few lose bigger (the asymmetry of a too-tight trailing stop on a
  volatile asset).
- **Max drawdown 8.98%** — never tripped the `halt_on_drawdown` (30%) or
  per-position-cap (60%) rules.
- **Sharpe -3.36** — under-performs both buy-and-hold-flat and cash.

## Files

| File | Contents |
|---|---|
| `report.html` | Interactive single-file React+shadcn+Recharts report — equity curve, drawdown shade, fills timeline, per-asset attribution |
| `report.json` | Computed metrics, all fills, cycle-by-cycle equity series — programmatic input |
| `report.md` | Headline-metrics Markdown table |
| `equity.png` | Equity curve chart (static, for non-browser viewing) |

## What an evaluator should look at

This run is the lowest-effort end-to-end demo of the backtester. The
single most-revealing artifact is `report.html` — every metric the
`pm report` engine computes shows up there, including the fill log and
the per-cycle decision trace.
