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

# 1b. ffmpeg — the decoder behind "Stack video" (Moon/Sun captures). Bundled in
#     the Docker image; without it here the video tests skip, so install it if we
#     can. Non-fatal either way.
if ! command -v ffmpeg >/dev/null 2>&1; then
  if ! { apt-get update && apt-get install -y --no-install-recommends ffmpeg; }; then
    echo "warn: could not install ffmpeg — tests/test_video_*.py will skip."
  fi
fi

# 2. Python engine + webapp. pyproject pins >=3.12,<3.13 — prefer python3.12.
PY=python3.12
command -v "$PY" >/dev/null 2>&1 || PY=python3
[ -d .venv ] || "$PY" -m venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate
# PyPI reads over the agent proxy do time out (seen 2026-09-07: a
# `ReadTimeoutError` from files.pythonhosted.org mid-resolve), so retry once with
# a longer budget before giving up. `-q` is dropped on the retry — if the second
# attempt fails too, the run needs to see why.
pip install -q -e ".[dev,web,gui]" \
  || pip install --timeout 120 --retries 5 -e ".[dev,web,gui]" \
  || PY_DEPS_FAILED=1
# Verify rather than assume. This script is `source`d, and its `set -e` has been
# observed NOT to stop a failed `pip install` here — the run then read a cheerful
# "agent env ready" over a `.venv` containing nothing but pip, and diagnosed a
# perfectly good checkout as broken. One import is the whole check.
python -c 'import pytest, fastapi, numpy, astropy' >/dev/null 2>&1 || PY_DEPS_FAILED=1

# 3. Frontend deps (only when the tree is present and not yet installed).
if [ -d frontend ] && [ ! -d frontend/node_modules ]; then
  (cd frontend && npm install)
fi

if [ "${PY_DEPS_FAILED:-0}" = "1" ]; then
  echo "ERROR: the Python environment is NOT ready — 'pip install -e \".[dev,web,gui]\"'"
  echo "       did not leave an importable toolchain in .venv (see the output above)."
  echo "       This is an install failure, usually a PyPI read timing out — the"
  echo "       checkout is fine. Retry the install before doing anything else:"
  echo "         source .venv/bin/activate"
  echo "         pip install --timeout 120 --retries 5 -e \".[dev,web,gui]\""
  echo "       Do NOT read 'No module named pytest' as a broken repo."
  return 1 2>/dev/null || exit 1
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
# Printed because a run copies its command from here, and the obvious tool-call
# shape for it is the one that lies: `pytest … | tail -15` reports *tail's* exit
# status, so a suite that never collected a test (an unrecognised flag exits 4
# with a `rootdir:` block that looks nothing like a summary) reads as a pass.
echo "  NB:       redirect, never pipe — a pipeline's exit status is the last"
echo "            command's:  python -m pytest -q > run.log 2>&1; echo \$?"
