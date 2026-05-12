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
    fd.add_argument("--start", required=True, help="ISO 8601 start ts")
    fd.add_argument("--end", required=True, help="ISO 8601 end ts")
    fd.add_argument("--symbol", default=None, help="Symbol label (default: derived from --token)")
    fd.add_argument("--out", default=None, help="Output parquet path (default: cache_dir/<symbol>-<bar>.parquet)")
    fd.add_argument("--force", action="store_true", help="Re-fetch even if cache exists")
    fd.set_defaults(_handler=cmd_stub, _stub_name="fetch-data")

    # replay — M18
    rp = sub.add_parser(
        "replay",
        help="Replay historical OHLCV through PM (cycle-by-cycle subprocess driver)",
    )
    rp.add_argument("--ohlcv", required=True, help="Parquet OHLCV path")
    rp.add_argument("--strategy", required=True, help="Path to a PM strategy .py")
    rp.add_argument("--rules", required=True, help="Path to a PM rules YAML")
    rp.add_argument("--initial-usd", dest="initial_usd", type=float, default=1000.0)
    rp.add_argument("--symbol", default=None, help="Asset symbol (default: derive from parquet)")
    rp.add_argument("--out", default=None, help="Run output dir (default: state/runs/<run-id>)")
    rp.add_argument("--fees-bps", dest="fees_bps", type=float, default=30.0)
    rp.add_argument("--slippage-bps", dest="slippage_bps", type=float, default=50.0)
    rp.set_defaults(_handler=cmd_stub, _stub_name="replay")

    # cache stats / clear — small helpers
    ca = sub.add_parser("cache", help="Inspect or clear the parquet cache")
    ca_sub = ca.add_subparsers(dest="subcmd", required=True)
    cs = ca_sub.add_parser("stats", help="List cached parquet files")
    cs.set_defaults(_handler=cmd_stub, _stub_name="cache stats")
    cc = ca_sub.add_parser("clear", help="Delete cached parquet files")
    cc.add_argument("--token", default=None)
    cc.set_defaults(_handler=cmd_stub, _stub_name="cache clear")

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
