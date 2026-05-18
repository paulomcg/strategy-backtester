import { Badge } from "@/components/ui/badge"
import { Separator } from "@/components/ui/separator"
import type { RunMeta } from "@/types"
import { fmtTs, shortAddr } from "@/lib/format"

interface RunHeaderProps {
  meta: RunMeta
}

export function RunHeader({ meta }: RunHeaderProps) {
  return (
    <header className="border-b border-border bg-background sticky top-0 z-10 backdrop-blur-md">
      <div className="mx-auto flex max-w-[1400px] flex-wrap items-center gap-x-6 gap-y-3 px-6 py-4">
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2">
            <span className="inline-block size-2 rounded-full bg-accent shadow-[0_0_0_4px_color-mix(in_oklab,var(--accent)_20%,transparent)]" />
            <span className="font-semibold tracking-tight text-base">
              strategy-backtester
            </span>
            <Badge
              variant="secondary"
              className="font-mono text-[10px] uppercase tracking-wider"
            >
              backtest
            </Badge>
          </div>
        </div>

        <Separator
          orientation="vertical"
          className="hidden h-6 sm:block"
        />

        <div className="text-sm tabular-nums">
          <span className="text-muted-foreground">{meta.asset}</span>
          <span className="text-muted-foreground mx-1.5">·</span>
          <span className="text-muted-foreground">{meta.chain}</span>
          {meta.address && (
            <>
              <span className="text-muted-foreground mx-1.5">·</span>
              <span className="font-mono text-xs text-muted-foreground">
                {shortAddr(meta.address)}
              </span>
            </>
          )}
        </div>

        <div className="ms-auto flex flex-col items-end text-right">
          <div className="text-xs text-muted-foreground tabular-nums">
            {fmtTs(meta.generated_at_utc)}
          </div>
          <div className="font-mono text-[10px] text-muted-foreground/70 tabular-nums">
            run · {meta.run_id}
          </div>
        </div>
      </div>
    </header>
  )
}
