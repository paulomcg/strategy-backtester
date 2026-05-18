import { useMemo } from "react"
import {
  Area,
  AreaChart,
  CartesianGrid,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts"
import type { EquityPoint } from "@/types"
import { fmtTsShort, fmtUsd, fmtPct } from "@/lib/format"

interface EquityChartProps {
  data: EquityPoint[]
  initialEquity: number
  maxDrawdownPeakTs?: string | null
  maxDrawdownTroughTs?: string | null
}

function ChartTooltip({ active, payload }: any) {
  if (!active || !payload || !payload.length) return null
  const p = payload[0].payload as EquityPoint
  return (
    <div className="rounded-md border border-border bg-popover/95 backdrop-blur px-3 py-2 shadow-lg">
      <div className="text-[10px] text-muted-foreground tabular-nums">
        {fmtTsShort(p.ts_utc)}
      </div>
      <div className="text-sm font-semibold tabular-nums mt-0.5">
        {fmtUsd(p.equity_usd)}
      </div>
      <div
        className={`text-[11px] tabular-nums mt-0.5 ${
          p.drawdown_pct < 0 ? "text-destructive" : "text-muted-foreground"
        }`}
      >
        DD {fmtPct(p.drawdown_pct, 2)}
      </div>
    </div>
  )
}

export function EquityChart({
  data,
  initialEquity,
  maxDrawdownPeakTs,
  maxDrawdownTroughTs,
}: EquityChartProps) {
  const last = data[data.length - 1]?.equity_usd ?? initialEquity
  const positive = last >= initialEquity
  const gradId = "equity-fill"

  const yDomain = useMemo(() => {
    if (!data.length) return [0, 1]
    const values = data.map((d) => d.equity_usd)
    const min = Math.min(...values, initialEquity)
    const max = Math.max(...values, initialEquity)
    const pad = Math.max((max - min) * 0.12, max * 0.02)
    return [Math.floor(min - pad), Math.ceil(max + pad)]
  }, [data, initialEquity])

  return (
    <div className="h-72 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart
          data={data}
          margin={{ top: 4, right: 8, left: 8, bottom: 0 }}
        >
          <defs>
            <linearGradient id={gradId} x1="0" y1="0" x2="0" y2="1">
              <stop
                offset="0%"
                stopColor={positive ? "var(--positive)" : "var(--destructive)"}
                stopOpacity={0.32}
              />
              <stop
                offset="100%"
                stopColor={positive ? "var(--positive)" : "var(--destructive)"}
                stopOpacity={0}
              />
            </linearGradient>
          </defs>
          <CartesianGrid vertical={false} strokeDasharray="2 4" />
          <XAxis
            dataKey="ts_utc"
            tickFormatter={(v) => fmtTsShort(v)}
            tickLine={false}
            axisLine={false}
            minTickGap={48}
          />
          <YAxis
            domain={yDomain}
            tickLine={false}
            axisLine={false}
            tickFormatter={(v) => fmtUsd(Number(v), true)}
            width={56}
          />
          <Tooltip content={<ChartTooltip />} cursor={{ stroke: "var(--border)" }} />
          <ReferenceLine
            y={initialEquity}
            stroke="var(--border)"
            strokeDasharray="2 4"
            label={{
              value: `initial ${fmtUsd(initialEquity, true)}`,
              position: "insideTopLeft",
              fill: "var(--muted-foreground)",
              fontSize: 10,
            }}
          />
          {maxDrawdownPeakTs && (
            <ReferenceLine x={maxDrawdownPeakTs} stroke="var(--border)" strokeDasharray="2 2" />
          )}
          {maxDrawdownTroughTs && (
            <ReferenceLine
              x={maxDrawdownTroughTs}
              stroke="var(--destructive)"
              strokeOpacity={0.5}
              strokeDasharray="2 2"
            />
          )}
          <Area
            type="monotone"
            dataKey="equity_usd"
            stroke={positive ? "var(--positive)" : "var(--destructive)"}
            strokeWidth={1.75}
            fill={`url(#${gradId})`}
            dot={false}
            isAnimationActive={false}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  )
}
