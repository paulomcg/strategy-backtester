import { useMemo, useState } from "react"
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip"
import { ArrowDownUp, ArrowDown, ArrowUp } from "lucide-react"
import type { Fill } from "@/types"
import { fmtNum, fmtQty, fmtTsShort, fmtUsd } from "@/lib/format"
import { cn } from "@/lib/utils"

type SortKey = "ts_utc" | "side" | "asset" | "qty" | "price_usd" | "value_usd"
type SortDir = "asc" | "desc"

interface TradesPanelProps {
  fills: Fill[]
}

const sortableHeaders: { key: SortKey; label: string; align?: "right" }[] = [
  { key: "ts_utc", label: "Timestamp" },
  { key: "side", label: "Side" },
  { key: "asset", label: "Asset" },
  { key: "qty", label: "Qty", align: "right" },
  { key: "price_usd", label: "Price", align: "right" },
  { key: "value_usd", label: "Value", align: "right" },
]

export function TradesPanel({ fills }: TradesPanelProps) {
  const [sortKey, setSortKey] = useState<SortKey>("ts_utc")
  const [sortDir, setSortDir] = useState<SortDir>("desc")

  const sorted = useMemo(() => {
    const out = [...fills]
    out.sort((a, b) => {
      const av = (a as any)[sortKey]
      const bv = (b as any)[sortKey]
      if (av === bv) return 0
      const cmp = av < bv ? -1 : 1
      return sortDir === "asc" ? cmp : -cmp
    })
    return out
  }, [fills, sortKey, sortDir])

  function toggleSort(k: SortKey) {
    if (k === sortKey) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"))
    } else {
      setSortKey(k)
      setSortDir(k === "ts_utc" ? "desc" : "asc")
    }
  }

  function sortIcon(k: SortKey) {
    if (k !== sortKey) return <ArrowDownUp className="size-3 opacity-40" />
    return sortDir === "asc" ? (
      <ArrowUp className="size-3" />
    ) : (
      <ArrowDown className="size-3" />
    )
  }

  return (
    <Card className="border-border bg-card py-0 shadow-none gap-0">
      <CardHeader className="px-5 py-4 border-b">
        <CardTitle className="text-[11px] uppercase tracking-[0.08em] text-muted-foreground font-medium">
          Fills <span className="ml-2 text-muted-foreground/60">{fills.length}</span>
        </CardTitle>
      </CardHeader>
      <CardContent className="p-0">
        {fills.length === 0 ? (
          <div className="p-8 text-center text-sm text-muted-foreground">
            no fills recorded
          </div>
        ) : (
          <div className="max-h-[420px] overflow-auto">
            <TooltipProvider delayDuration={300}>
              <Table className="sticky-head">
                <TableHeader>
                  <TableRow className="hover:bg-transparent">
                    {sortableHeaders.map((h) => (
                      <TableHead
                        key={h.key}
                        className={cn(
                          "text-[10px] uppercase tracking-wider text-muted-foreground font-medium",
                          h.align === "right" && "text-right",
                        )}
                      >
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => toggleSort(h.key)}
                          className={cn(
                            "h-7 px-2 -mx-2 text-[10px] uppercase tracking-wider gap-1 text-muted-foreground hover:text-foreground",
                            h.align === "right" && "ml-auto",
                          )}
                        >
                          {h.label}
                          {sortIcon(h.key)}
                        </Button>
                      </TableHead>
                    ))}
                    <TableHead className="text-[10px] uppercase tracking-wider text-muted-foreground font-medium text-right">
                      Trigger
                    </TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {sorted.map((f, i) => (
                    <TableRow key={i} className="border-border/60">
                      <TableCell className="text-xs tabular-nums text-muted-foreground">
                        {fmtTsShort(f.ts_utc)}
                      </TableCell>
                      <TableCell>
                        <Badge
                          variant={f.side === "buy" ? "default" : "secondary"}
                          className={cn(
                            "font-mono text-[10px] uppercase tracking-wider",
                            f.side === "buy"
                              ? "bg-positive/15 text-positive border-positive/30"
                              : "bg-destructive/15 text-destructive border-destructive/30",
                          )}
                        >
                          {f.side}
                        </Badge>
                      </TableCell>
                      <TableCell className="font-medium text-sm">{f.asset}</TableCell>
                      <TableCell className="text-right tabular-nums text-sm">
                        {fmtQty(f.qty)}
                      </TableCell>
                      <TableCell className="text-right tabular-nums text-sm">
                        {fmtUsd(f.price_usd)}
                      </TableCell>
                      <TableCell className="text-right tabular-nums text-sm font-medium">
                        {fmtUsd(f.value_usd)}
                      </TableCell>
                      <TableCell className="text-right">
                        {f.rule ? (
                          <Tooltip>
                            <TooltipTrigger asChild>
                              <Badge
                                variant="outline"
                                className="font-mono text-[10px] border-accent/40 text-accent"
                              >
                                {f.rule}
                              </Badge>
                            </TooltipTrigger>
                            <TooltipContent className="text-xs">
                              triggered by rule engine
                            </TooltipContent>
                          </Tooltip>
                        ) : f.decision ? (
                          <Tooltip>
                            <TooltipTrigger asChild>
                              <Badge
                                variant="outline"
                                className="font-mono text-[10px]"
                              >
                                strategy
                              </Badge>
                            </TooltipTrigger>
                            <TooltipContent className="text-xs">
                              from <code className="text-[10px]">{f.decision}</code>
                            </TooltipContent>
                          </Tooltip>
                        ) : (
                          <span className="text-muted-foreground/40 text-xs">—</span>
                        )}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </TooltipProvider>
          </div>
        )}
        {sorted.length > 0 && (
          <div className="px-5 py-3 border-t text-xs text-muted-foreground tabular-nums flex items-center justify-between">
            <span>
              total value:{" "}
              <span className="text-foreground font-medium">
                {fmtUsd(sorted.reduce((s, f) => s + f.value_usd, 0))}
              </span>
            </span>
            <span>
              fees:{" "}
              <span className="text-foreground font-medium">
                {fmtUsd(sorted.reduce((s, f) => s + (f.fees_usd ?? 0), 0))}
              </span>
              {" + slippage: "}
              <span className="text-foreground font-medium">
                {fmtUsd(sorted.reduce((s, f) => s + (f.slippage_usd ?? 0), 0))}
              </span>
            </span>
          </div>
        )}
      </CardContent>
    </Card>
  )
}

export { sortableHeaders as _sortableHeaders }
export type { SortKey, SortDir }

// silence unused exports for vite tree-shaking — fmtNum import keeps for value formatting if needed later
void fmtNum
