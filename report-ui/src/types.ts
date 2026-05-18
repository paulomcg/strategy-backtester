/**
 * Shape of the data injected by the Python backtester into the static report.
 * The HTML template has a single global `window.__RUN_DATA__` populated at
 * write-time so the report.html file is fully self-contained.
 */

export type Side = "buy" | "sell"

export interface Fill {
  ts_utc: string
  asset: string
  side: Side
  qty: number
  price_usd: number
  value_usd: number
  fees_usd?: number
  slippage_usd?: number
  rule?: string | null
  decision?: string | null
}

export interface TradeStats {
  trades: number
  winners: number
  losers: number
  win_rate: number
  expectancy_usd: number
  total_pnl_usd: number
}

export interface Metrics {
  schema_version: string
  bars: number
  periods_per_year?: number
  initial_equity_usd: number
  final_equity_usd: number
  total_return_pct: number
  cagr_pct: number
  sharpe: number
  sortino: number
  calmar: number
  max_drawdown_pct: number
  max_drawdown_peak_ts?: string | null
  max_drawdown_trough_ts?: string | null
  trades: TradeStats
  per_asset_pnl_usd: Record<string, number>
  warning?: string
}

export interface EquityPoint {
  ts_utc: string
  equity_usd: number
  drawdown_pct: number
}

export interface RunMeta {
  run_id: string
  generated_at_utc: string
  asset: string
  address?: string | null
  chain: string
  initial_usd: number
  bars_processed: number
  fills_total: number
  pm_call_failures: number
  final_equity_usd: number
  strategy_path: string
  rules_path: string
  ohlcv_path: string
  mode: "backtest"
  title?: string
}

export interface ReportPayload {
  schema_version: string
  meta: RunMeta
  metrics: Metrics
  equity: EquityPoint[]
  fills: Fill[]
}

declare global {
  interface Window {
    __RUN_DATA__?: ReportPayload
  }
}
