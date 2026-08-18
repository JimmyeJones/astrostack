#!/usr/bin/env bash
# Boot a REAL AstroStack with REAL data, so "dogfood the app" (AGENTS.md §2)
# means running it instead of re-reading its route files.
#
# Why this exists: the three bugs fixed in v0.263.2–v0.263.4 had all survived
# months of code-level audits, and not one of them was findable by reading — the
# planner's "cut its noise about 100 %" needed a zero-integration target actually
# rendered, the sample's "0 of 0 frames" needed the library row and the project
# DB compared at runtime, and the clipped "Edit imag" needed a browser measuring
# a box. Every run used to reinvent how to get to that point, so in practice the
# pass degraded back into reading code. This is that setup, once.
#
# Usage (from the repo root, after scripts/agent-setup.sh):
#
#   scripts/agent-dogfood.sh                 # boot + sample + stack + probe, then stop
#   scripts/agent-dogfood.sh --serve         # boot and STAY UP (Ctrl-C to stop)
#   scripts/agent-dogfood.sh --no-stack      # skip the (slow) stack of the sample
#   scripts/agent-dogfood.sh --no-probe      # boot only, don't drive a browser
#
# Everything it writes goes under a scratch directory ($DOGFOOD_DIR, default
# ${TMPDIR:-/tmp}/astrostack-dogfood) — NEVER the repo, and never a real library.
# `webapp/static/` is a build artifact and stays gitignored.
#
# The browser half needs Playwright. The container already ships the browsers at
# $PLAYWRIGHT_BROWSERS_PATH (do NOT run `playwright install`), but the npm
# package is installed on demand into the scratch dir — never into
# frontend/package.json. If that install can't happen (no network), the script
# says so and still leaves you a running app to poke by hand, which is most of
# the value.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]:-$0}")/.."
REPO="$PWD"

DOGFOOD_DIR="${DOGFOOD_DIR:-${TMPDIR:-/tmp}/astrostack-dogfood}"
PORT="${ASTROSTACK_PORT:-8811}"
BASE="http://127.0.0.1:${PORT}"
DO_SERVE=0; DO_STACK=1; DO_PROBE=1; DO_BUILD=0
for arg in "$@"; do
  case "$arg" in
    --serve) DO_SERVE=1 ;;
    --no-stack) DO_STACK=0 ;;
    --no-probe) DO_PROBE=0 ;;
    --build) DO_BUILD=1 ;;
    -h|--help) sed -n '1,32p' "$0"; exit 0 ;;
    *) echo "unknown flag: $arg" >&2; exit 2 ;;
  esac
done

DATA="$DOGFOOD_DIR/data"
SHOTS="$DOGFOOD_DIR/shots"
mkdir -p "$DATA" "$SHOTS"
echo "dogfood scratch: $DOGFOOD_DIR"

# 1. The SPA. webapp/ serves whatever is in webapp/static, so a stale build
#    would have you dogfooding last week's frontend.
if [ "$DO_BUILD" = 1 ] || [ ! -f webapp/static/index.html ]; then
  echo "-- building the frontend (npx vite build)"
  (cd frontend && npx vite build >/dev/null)
fi

# 2. The server. Its own scratch data root, its own port.
[ -d .venv ] && source .venv/bin/activate
echo "-- starting the app on $BASE (data: $DATA)"
ASTROSTACK_DATA="$DATA" ASTROSTACK_PORT="$PORT" \
  python -m webapp.main > "$DOGFOOD_DIR/server.log" 2>&1 &
SERVER_PID=$!
cleanup() {
  if kill -0 "$SERVER_PID" 2>/dev/null; then
    kill "$SERVER_PID" 2>/dev/null || true
    wait "$SERVER_PID" 2>/dev/null || true
  fi
}
trap cleanup EXIT

for _ in $(seq 1 60); do
  if curl -sf "$BASE/api/system" >/dev/null 2>&1; then break; fi
  if ! kill -0 "$SERVER_PID" 2>/dev/null; then
    echo "server died on boot — $DOGFOOD_DIR/server.log:" >&2
    tail -20 "$DOGFOOD_DIR/server.log" >&2
    exit 1
  fi
  sleep 1
done
curl -sf "$BASE/api/system" >/dev/null || { echo "server never answered" >&2; exit 1; }

# 3. Real data. The bundled sample is a genuine target with frames, so the app
#    is exercised the way a user's is rather than through empty states.
if [ "$(curl -sf "$BASE/api/targets" | tr -d '[:space:]')" = "[]" ]; then
  echo "-- loading the bundled sample target"
  curl -sf -X POST "$BASE/api/sample" >/dev/null || echo "warn: sample load failed"
fi
SAFE="$(curl -sf "$BASE/api/targets" \
        | python -c 'import json,sys; t=json.load(sys.stdin); print(t[0]["safe_name"] if t else "")' \
        2>/dev/null || true)"
echo "-- target: ${SAFE:-<none>}"

# 4. A finished picture, so the picture-shaped surfaces (hero card, Gallery,
#    History, the editor) have something real to render rather than self-hiding.
if [ "$DO_STACK" = 1 ] && [ -n "$SAFE" ]; then
  if [ "$(curl -sf "$BASE/api/targets/$SAFE/stack-runs" | tr -d '[:space:]')" = "[]" ]; then
    echo "-- stacking the sample (this is the slow part; --no-stack skips it)"
    JOB="$(curl -sf -X POST "$BASE/api/targets/$SAFE/process" \
           | python -c 'import json,sys; print(json.load(sys.stdin).get("job_id",""))' 2>/dev/null || true)"
    for _ in $(seq 1 180); do
      STATE="$(curl -sf "$BASE/api/jobs/$JOB" \
               | python -c 'import json,sys; print(json.load(sys.stdin).get("state",""))' 2>/dev/null || true)"
      # The engine's own terminal set (`webapp/jobs.py::_TERMINAL`). A success is
      # "done", never "finished" — waiting on the wrong word costs the whole
      # 180×2s budget on every run, long after the picture is on disk.
      case "$STATE" in
        done|error|cancelled|interrupted) echo "-- process job: $STATE"; break ;;
      esac
      sleep 2
    done
  fi
fi

# 5. The browser probe: full-page screenshots at desktop AND phone widths, plus
#    the overflow check that found the clipped Gallery button. A finder, not a
#    test — anything it turns up still needs a real regression test in the suite.
if [ "$DO_PROBE" = 1 ]; then
  PW_DIR="$DOGFOOD_DIR/pw"
  if [ ! -d "$PW_DIR/node_modules/playwright" ]; then
    echo "-- installing playwright into $PW_DIR (not into frontend/)"
    mkdir -p "$PW_DIR"
    (cd "$PW_DIR" && PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1 \
       npm install --silent --no-fund --no-audit playwright >/dev/null 2>&1) \
      || echo "warn: could not install playwright — skipping the browser probe"
  fi
  if [ -d "$PW_DIR/node_modules/playwright" ]; then
    echo "-- probing the running app"
    # Copied in rather than run from the repo: an ESM `import "playwright"`
    # resolves from the *script's* directory, and NODE_PATH doesn't apply.
    cp "$REPO/scripts/dogfood_probe.mjs" "$PW_DIR/probe.mjs"
    RUN_ID="$(curl -sf "$BASE/api/targets/$SAFE/stack-runs" \
              | python -c 'import json,sys; r=json.load(sys.stdin); print(r[0]["id"] if r else "")' \
              2>/dev/null || true)"
    (cd "$PW_DIR" && BASE_URL="$BASE" SHOTS_DIR="$SHOTS" TARGET_SAFE="$SAFE" \
       TARGET_RUN_ID="$RUN_ID" node probe.mjs) || echo "warn: probe failed"
    echo "-- screenshots: $SHOTS"
  fi
fi

if [ "$DO_SERVE" = 1 ]; then
  echo
  echo "app is up at $BASE — Ctrl-C to stop"
  wait "$SERVER_PID"
fi
