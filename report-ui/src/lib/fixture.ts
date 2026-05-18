import type { ReportPayload } from "@/types"

/** Synthetic fixture so the UI renders during `npm run dev` without a real run. */
function genEquity(n: number, start: number) {
  const out: { ts_utc: string; equity_usd: number; drawdown_pct: number }[] = []
  let v = start
  let hwm = start
  const t0 = new Date("2026-05-01T00:00:00Z").getTime()
  for (let i = 0; i < n; i++) {
    const drift = Math.sin(i / 9) * 12 + (Math.random() - 0.45) * 18
    v = Math.max(50, v + drift)
    hwm = Math.max(hwm, v)
    const dd = ((v - hwm) / hwm) * 100
    out.push({
      ts_utc: new Date(t0 + i * 6 * 3600_000).toISOString(),
      equity_usd: Number(v.toFixed(2)),
      drawdown_pct: Number(dd.toFixed(3)),
    })
  }
  return out
}

const equity = genEquity(80, 1000)

export const fixtureReport: ReportPayload = {
  schema_version: "1",
  meta: {
    run_id: "20260518T112233Z-7af19c",
    generated_at_utc: "2026-05-18T11:24:01Z",
    asset: "WSOL",
    address: "So11111111111111111111111111111111111111112",
    chain: "solana",
    initial_usd: 1000,
    bars_processed: 80,
    fills_total: 14,
    pm_call_failures: 0,
    final_equity_usd: equity[equity.length - 1].equity_usd,
    strategy_path: "examples/strategies/buy_and_hold_wsol.py",
    rules_path: "examples/rules/conservative.yaml",
    ohlcv_path: "tests/fixtures/synthetic_wsol_20d.parquet",
    mode: "backtest",
    title: "Backtest WSOL · synthetic 20d",
  },
  metrics: {
    schema_version: "1",
    bars: 80,
    periods_per_year: 1460,
    initial_equity_usd: 1000,
    final_equity_usd: equity[equity.length - 1].equity_usd,
    total_return_pct: ((equity[equity.length - 1].equity_usd - 1000) / 1000) * 100,
    cagr_pct: 142.7,
    sharpe: 1.84,
    sortino: 2.61,
    calmar: 3.12,
    max_drawdown_pct: -8.45,
    max_drawdown_peak_ts: "2026-05-08T18:00:00Z",
    max_drawdown_trough_ts: "2026-05-10T06:00:00Z",
    trades: {
      trades: 7,
      winners: 5,
      losers: 2,
      win_rate: 0.7142857,
      expectancy_usd: 21.43,
      total_pnl_usd: 150.04,
    },
    per_asset_pnl_usd: { WSOL: 150.04 },
  },
  equity,
  fills: Array.from({ length: 14 }).map((_, i) => {
    const side = i % 2 === 0 ? "buy" : "sell"
    const price = 145 + Math.sin(i) * 12 + i * 0.5
    const qty = side === "buy" ? 0.5 + i * 0.05 : 0.5 + (i - 1) * 0.05
    return {
      ts_utc: new Date(
        new Date("2026-05-01T00:00:00Z").getTime() + (i * 4 + 3) * 6 * 3600_000,
      ).toISOString(),
      asset: "WSOL",
      side,
      qty,
      price_usd: Number(price.toFixed(4)),
      value_usd: Number((price * qty).toFixed(2)),
      fees_usd: Number((price * qty * 0.003).toFixed(2)),
      slippage_usd: Number((price * qty * 0.0005).toFixed(2)),
      rule: i === 9 ? "trailing_stop" : null,
      decision: i % 4 === 0 ? "strategy.decide" : null,
    }
  }),
}
