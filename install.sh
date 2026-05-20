#!/usr/bin/env bash
# One-shot installer for strategy-backtester.
#
# Creates a local .venv, installs runtime + test deps, verifies the
# CLI is callable, and checks that the companion `pm` CLI is on PATH
# (strategy-backtester drives portfolio-manager). Idempotent.

set -e

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

if [ ! -d .venv ]; then
  echo "  creating .venv..."
  python3 -m venv .venv
fi

echo "  installing runtime + test deps..."
.venv/bin/pip install -q --upgrade pip
.venv/bin/pip install -q -r requirements.txt pytest

echo "  verifying backtester CLI..."
PYTHONPATH="$ROOT" .venv/bin/python3 -m scripts.backtester --version >/dev/null

echo "  verifying companion pm CLI on PATH..."
PYTHONPATH="$ROOT" .venv/bin/python3 -m scripts.backtester pm-check 2>&1 | head -1 || \
  echo "  (warning: pm CLI not found on PATH — install portfolio-manager first)"

echo
echo "  done. invoke via:"
echo "    $ROOT/bin/backtester <subcommand> [args...]"
echo "  for backtests to actually run, install portfolio-manager and ensure"
echo "  its bin/ dir is on PATH so backtester can subprocess-drive it."
