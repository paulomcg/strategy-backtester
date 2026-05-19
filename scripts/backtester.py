"""backtester — CLI dispatcher.

Subcommands ship in M15..M19. v0.0.1 wires the parser shape; handlers
land in their own milestones.
"""

from __future__ import annotations

import argparse
import functools
import json
import sys
from pathlib import Path
from typing import Any, Callable

# Allow `python -m scripts.backtester` (no package context) from the launcher.
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

EXIT_OK = 0
EXIT_FAILED = 1


def _ok(result: Any) -> int:
    print(json.dumps({"ok": True, "result": result}, default=str))
    return EXIT_OK


def _failed(line: str) -> int:
    print(f"FAILED: {line}", file=sys.stderr)
    return EXIT_FAILED


def _wrap(handler: Callable[..., int]) -> Callable[..., int]:
    @functools.wraps(handler)
    def _w(args: argparse.Namespace) -> int:
        try:
            return handler(args)
        except KeyboardInterrupt:
            return _failed("interrupted")
        except Exception as e:  # noqa: BLE001 — top-level safety net
            return _failed(f"internal_error {type(e).__name__}: {e}")

    return _w


@_wrap
def cmd_replay(args: argparse.Namespace) -> int:
    """Replay one or more OHLCV parquets through PM, then run pm report."""
    from scripts import replay

    # `--ohlcv` may be repeated or comma-separated to drive multi-asset runs.
    ohlcv_paths: list[Path] = []
    for raw in (args.ohlcv if isinstance(args.ohlcv, list) else [args.ohlcv]):
        for part in str(raw).split(","):
            part = part.strip()
            if part:
                ohlcv_paths.append(Path(part))

    symbols: list[str] | None = None
    if args.symbol:
        symbols = []
        for raw in (args.symbol if isinstance(args.symbol, list) else [args.symbol]):
            for part in str(raw).split(","):
                part = part.strip()
                if part:
                    symbols.append(part)

    try:
        result = replay.run_replay(
            ohlcv_paths=ohlcv_paths,
            strategy_path=args.strategy,
            rules_path=args.rules,
            initial_usd=args.initial_usd,
            symbols=symbols,
            chain=args.chain,
            out_dir=args.out,
            fees_bps=args.fees_bps,
            slippage_bps=args.slippage_bps,
        )
    except replay.ReplayError as e:
        return _failed(str(e))
    return _ok(result)


@_wrap
def cmd_fetch_data(args: argparse.Namespace) -> int:
    """Fetch OHLCV via onchainos market kline and write a parquet."""
    from scripts import data_fetcher

    try:
        result = data_fetcher.fetch(
            token=args.token,
            chain=args.chain,
            bar=args.bar,
            start=args.start,
            end=args.end,
            symbol=args.symbol,
            out=args.out,
            force=args.force,
        )
    except data_fetcher.DataFetchError as e:
        return _failed(str(e))
    return _ok(result)


@_wrap
def cmd_pm_check(args: argparse.Namespace) -> int:
    """Smoke-check that the `pm` CLI is available + functional.

    Strips PYTHONPATH from the subprocess env so PM's own launcher can prepend
    PM's repo root cleanly (otherwise our own scripts/ package leaks ahead and
    `python -m scripts.pm` resolves to the wrong package).
    """
    import os
    import subprocess

    from scripts import config

    pm = config.pm_bin()
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    try:
        res = subprocess.run(
            [pm, "--version"], capture_output=True, text=True, timeout=5, env=env
        )
    except FileNotFoundError:
        return _failed(f"pm_not_installed pm bin not found at {pm!r}")
    if res.returncode != 0:
        detail = (res.stderr or res.stdout).strip().splitlines()[-1:] or [""]
        return _failed(
            f"pm_not_installed pm --version exited {res.returncode}: {detail[0]}"
        )
    return _ok({"pm_bin": pm, "pm_version": res.stdout.strip()})


@_wrap
def cmd_cache_stats(args: argparse.Namespace) -> int:  # noqa: ARG001 — no per-cmd args
    """List cached parquet files: symbol, bar, rows, ts range, disk size."""
    from scripts import config

    cache_dir = config.cache_dir()
    entries: list[dict[str, Any]] = []
    total_bytes = 0
    total_rows = 0
    for p in sorted(cache_dir.glob("*.parquet")):
        try:
            stat = p.stat()
            size = stat.st_size
            total_bytes += size
            import pandas as pd

            df = pd.read_parquet(p)
            row_count = len(df)
            total_rows += row_count
            ts_min = ts_max = None
            if "ts" in df.columns and not df.empty:
                ts_min = str(df["ts"].min())
                ts_max = str(df["ts"].max())
            stem = p.stem
            sym, _, bar = stem.rpartition("-")
            entries.append({
                "symbol": sym or stem,
                "bar": bar or "?",
                "path": str(p),
                "rows": row_count,
                "size_bytes": size,
                "ts_min": ts_min,
                "ts_max": ts_max,
                "mtime": _iso_mtime(stat.st_mtime),
            })
        except Exception as e:  # noqa: BLE001 — corrupt parquet shouldn't kill the listing
            entries.append({"path": str(p), "error": f"{type(e).__name__}: {e}"})

    return _ok({
        "cache_dir": str(cache_dir),
        "count": len(entries),
        "total_rows": total_rows,
        "total_size_bytes": total_bytes,
        "entries": entries,
    })


@_wrap
def cmd_cache_clear(args: argparse.Namespace) -> int:
    """Delete cached parquets. Requires --all OR (--symbol [--bar]). Refuses to do nothing."""
    from scripts import config

    cache_dir = config.cache_dir()
    if not args.all and not args.symbol:
        return _failed(
            "cache_clear_no_target — pass --all, or --symbol SYM [--bar BAR]"
        )

    deleted: list[str] = []
    if args.all:
        for p in cache_dir.glob("*.parquet"):
            try:
                p.unlink()
                deleted.append(str(p))
            except OSError as e:
                return _failed(f"cache_clear_failed {p}: {e}")
    else:
        # Symbol-scoped: optionally bar-scoped too.
        pattern = (
            f"{args.symbol}-{args.bar}.parquet"
            if args.bar
            else f"{args.symbol}-*.parquet"
        )
        for p in cache_dir.glob(pattern):
            try:
                p.unlink()
                deleted.append(str(p))
            except OSError as e:
                return _failed(f"cache_clear_failed {p}: {e}")
    return _ok({"cache_dir": str(cache_dir), "deleted": deleted, "count": len(deleted)})


def _iso_mtime(mtime: float) -> str:
    import datetime as _dt

    return _dt.datetime.fromtimestamp(mtime, tz=_dt.timezone.utc).isoformat()


@_wrap
def cmd_report_html(args: argparse.Namespace) -> int:
    """Regenerate report.html for an existing run dir without re-running the backtest."""
    from scripts import html_report

    run_dir = Path(args.run_dir).expanduser().resolve()
    if not run_dir.exists():
        return _failed(f"run_dir_not_found {run_dir}")
    out = html_report.emit_html_report(run_dir)
    if out is None:
        return _failed(
            "report_html_inputs_missing — need run.json, report/report.json, "
            "and scripts/report_template.html"
        )
    return _ok({"report_html": str(out)})


@_wrap
def cmd_stub(args: argparse.Namespace) -> int:
    name = getattr(args, "_stub_name", "this command")
    return _failed(f"not_implemented {name} ships in a later milestone")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="backtester",
        description=(
            "strategy-backtester — drives PM v0.2.0 through historical OHLCV "
            "from `onchainos market kline`. Mocks the OKX environment so PM "
            "doesn't know it's in a backtest."
        ),
    )
    p.add_argument("--version", action="version", version="backtester 0.1.0")
    sub = p.add_subparsers(dest="cmd", required=True)

    # pm-check
    pc = sub.add_parser("pm-check", help="Verify the `pm` CLI is installed + functional")
    pc.set_defaults(_handler=cmd_pm_check)

    # fetch-data — M16
    fd = sub.add_parser(
        "fetch-data",
        help="Fetch OHLCV via `onchainos market kline` and cache to parquet",
    )
    fd.add_argument("--token", required=True, help="Token contract address")
    fd.add_argument("--chain", default="solana", help="Chain (default: solana)")
    fd.add_argument("--bar", default="1D", help="Bar timeframe (default: 1D)")
    fd.add_argument("--start", default=None, help="ISO 8601 lower bound (optional)")
    fd.add_argument("--end", default=None, help="ISO 8601 upper bound (optional)")
    fd.add_argument("--symbol", default=None, help="Symbol label (default: derived from --token)")
    fd.add_argument("--out", default=None, help="Output parquet path (default: cache_dir/<symbol>-<bar>.parquet)")
    fd.add_argument("--force", action="store_true", help="Re-fetch even if cache exists")
    fd.set_defaults(_handler=cmd_fetch_data)

    # replay — M18
    rp = sub.add_parser(
        "replay",
        help="Replay historical OHLCV through PM (cycle-by-cycle subprocess driver)",
    )
    rp.add_argument(
        "--ohlcv", required=True, action="append",
        help="Parquet OHLCV path. Repeat or comma-separate for multi-asset.",
    )
    rp.add_argument("--strategy", required=True, help="Path to a PM strategy .py")
    rp.add_argument("--rules", required=True, help="Path to a PM rules YAML")
    rp.add_argument("--initial-usd", dest="initial_usd", type=float, default=1000.0)
    rp.add_argument(
        "--symbol", default=None, action="append",
        help="Asset symbol. Repeat or comma-separate; defaults to each parquet's stem.",
    )
    rp.add_argument("--chain", default="solana", help="Chain (default: solana)")
    rp.add_argument("--out", default=None, help="Run output dir (default: state/runs/<run-id>)")
    rp.add_argument("--fees-bps", dest="fees_bps", type=float, default=30.0)
    rp.add_argument("--slippage-bps", dest="slippage_bps", type=float, default=50.0)
    rp.set_defaults(_handler=cmd_replay)

    # report-html — regenerate the interactive HTML report for an existing run
    rh = sub.add_parser(
        "report-html",
        help="Render report.html for an existing run dir (no replay)",
    )
    rh.add_argument("--run-dir", dest="run_dir", required=True, help="Path to an existing run output dir")
    rh.set_defaults(_handler=cmd_report_html)

    # cache stats / clear — parquet cache hygiene
    ca = sub.add_parser("cache", help="Inspect or clear the parquet cache")
    ca_sub = ca.add_subparsers(dest="subcmd", required=True)
    cs = ca_sub.add_parser("stats", help="List cached parquet files + total disk usage")
    cs.set_defaults(_handler=cmd_cache_stats)
    cc = ca_sub.add_parser(
        "clear",
        help="Delete cached parquets. --all OR --symbol [--bar].",
    )
    cc.add_argument("--all", action="store_true", help="Delete every cached parquet")
    cc.add_argument("--symbol", default=None, help="Symbol prefix to delete")
    cc.add_argument("--bar", default=None, help="Bar suffix (only with --symbol)")
    cc.set_defaults(_handler=cmd_cache_clear)

    # list-data
    ld = sub.add_parser("list-data", help="List parquet files in the cache")
    ld.set_defaults(_handler=cmd_stub, _stub_name="list-data")

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    handler = getattr(args, "_handler", None)
    if handler is None:
        parser.error("no handler for this command")
        return EXIT_FAILED
    return handler(args)


if __name__ == "__main__":
    raise SystemExit(main())
