#!/usr/bin/env bash
# Career Pipeline Quick Runner for macOS & Linux
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export PYTHONPATH="$SCRIPT_DIR/src:${PYTHONPATH:-}"

if command -v uv >/dev/null 2>&1; then
    uv run --project "$SCRIPT_DIR" python3 -m career_pipeline.cli "$@"
else
    python3 -m career_pipeline.cli "$@"
fi
