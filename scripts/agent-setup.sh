#!/usr/bin/env bash
# Idempotent environment bootstrap for autonomous agent runs (Builder & Scout).
#
# The container is ephemeral, so a run may start with no venv / node_modules.
# This script is safe to run repeatedly — it skips work that's already done —
# so every run can start with `source scripts/agent-setup.sh` and be productive
# immediately instead of spending part of the run rebuilding the toolchain.
#
# Usage:  source scripts/agent-setup.sh   (leaves the .venv activated)
#     or: bash scripts/agent-setup.sh
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]:-$0}")/.."

# 1. System libs PySide6/pytest-qt need at import time (headless container).
#    Non-fatal if unavailable — fall back to the Qt-skip pytest run (AGENTS.md §7).
if ! ldconfig -p 2>/dev/null | grep -q 'libEGL\.so\.1'; then
  if ! { apt-get update && apt-get install -y libegl1 libgl1 libxkbcommon0; }; then
    echo "warn: could not install Qt system libs (libEGL missing)."
    echo "      Without libEGL the pytest-qt plugin crashes collection with an"
    echo "      INTERNALERROR, so you MUST disable it — ignoring the 3 GUI files"
    echo "      alone is not enough. Use the Qt-skip fallback (AGENTS.md §7):"
    echo "      python -m pytest tests/ -p no:pytest-qt \\"
    echo "        --ignore=tests/test_compare_dialog.py \\"
    echo "        --ignore=tests/test_end_to_end.py \\"
    echo "        --ignore=tests/test_footprint_view.py -q"
    QT_LIBS_MISSING=1
  fi
fi

# 2. Python engine + webapp. pyproject pins >=3.12,<3.13 — prefer python3.12.
PY=python3.12
command -v "$PY" >/dev/null 2>&1 || PY=python3
[ -d .venv ] || "$PY" -m venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate
pip install -q -e ".[dev,web]"

# 3. Frontend deps (only when the tree is present and not yet installed).
if [ -d frontend ] && [ ! -d frontend/node_modules ]; then
  (cd frontend && npm install)
fi

echo "agent env ready: $(python --version 2>&1)"
if [ "${QT_LIBS_MISSING:-0}" = "1" ]; then
  echo "  tests:    python -m pytest tests/ -p no:pytest-qt \\"
  echo "              --ignore=tests/test_compare_dialog.py \\"
  echo "              --ignore=tests/test_end_to_end.py \\"
  echo "              --ignore=tests/test_footprint_view.py -q   (Qt libs unavailable)"
else
  echo "  tests:    QT_QPA_PLATFORM=offscreen python -m pytest -q"
fi
echo "  frontend: (cd frontend && npx tsc --noEmit && npx vitest run && npx vite build)"
