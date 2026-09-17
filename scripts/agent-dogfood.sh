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
#   scripts/agent-dogfood.sh --empty         # probe a FIRST-RUN app: no data at all
#   scripts/agent-dogfood.sh --editor        # ALSO drive the editor (adds every op)
#   scripts/agent-dogfood.sh --mosaic        # ALSO load/stack/probe a 2x2 MOSAIC sample
#   scripts/agent-dogfood.sh --big           # ALSO a FULL-SIZE mosaic: the editor's preview is decimated
#   scripts/agent-dogfood.sh --no-site       # leave the scratch install with no observing site
#   scripts/agent-dogfood.sh --incoming-lag  # ALSO leave subs in incoming/ the library never imported
#                                           #   (one of them damaged, and scanned, so the
#                                           #    "these can't be read" note is reachable too)
#   scripts/agent-dogfood.sh --calibration   # ALSO build a master dark + flat and stack WITH them
#
# --no-site turns OFF something a normal pass now does by default. Every pass
# before 2026-09-12 left the scratch install with no site at all: the bundled
# samples' FITS carry no SITELAT/SITELONG (deliberately — a demo that claimed a
# location would silently plan a real owner's night from it), and no site means
# `_resolve_observer` answers "none", which means **Tonight, the Sky Map's
# placement, the life list's "Up tonight" chip, the wishlist's "the Tonight page
# will tell you when", /api/plan/closing, /api/plan/week and
# /api/life-list/nearly-there are ALL in their empty state**. So every "dogfood
# CLEAN" ever recorded was a statement about the half of the app that does not
# need a site, while v0.426.0, v0.430.0 and v0.433.0 all shipped into the half
# that does. The fix stays out of the shipped data: the script PUTs a site into
# its own scratch install's Settings, which is exactly what a real owner's
# install supplies, and nothing about the sample changes. Override the location
# with DOGFOOD_SITE="lat,lon"; --empty never sets one (a first-run app has no
# site, and that empty state is what that pass exists to measure).
#
# --editor exists because the page probe only ever *photographs* the editor, in
# the one state it opens in. Priority 1 is the editor and the owner's complaints
# about it are all about what happens after a click, so `dogfood_editor.mjs` adds
# every op the Add menu offers and checks the live preview actually re-renders,
# with no console error and no failed request. It is off by default only because
# it costs a few minutes on top of a pass that already stacks the sample — run it
# on any run that touches the editor.
#
# --incoming-lag exists because the scratch `incoming/` is EMPTY on every pass:
# the sample arrives through `POST /api/sample`, which writes straight into the
# library, so the drop folder this whole app is built around has never held a
# file while a browser was looking. Anything that reads it — v0.442.0's "N subs
# haven't been imported yet" note first — is therefore structurally invisible,
# which is the missing-observing-site hole (v0.436.1) and the unreachable
# Split/Blink modes (v0.440.2) a third time. It writes a few subs with the app's
# own sample writer, dates them eleven days ago (the observer's own measurement,
# and past the note's "has this folder stopped moving?" rule), and stretches the
# watcher's quiet period so the batch is not handed off and imported mid-pass.
# A flag, not the default, and the line is deliberate: an observing site is data
# a real install *has*, while unimported subs are a *fault* — seeding one by
# default would put a warning banner in every Dashboard screenshot and every
# page-height baseline, and make "CLEAN" mean less rather than more.
#
# --mosaic exists because AGENTS.md §1 judges every Auto/editor claim on a tiled
# mosaic at the owner's scale, never on the 6-frame single field — and until now
# the tooling could not produce one, so every "dogfood CLEAN" was still measured
# on the field. It loads a second, generated sample (`POST /api/sample` with
# {"shape":"mosaic"}): four overlapping panels of one shared sky, uneven depth,
# one panel shot through haze, and a ragged union canvas with genuinely uncovered
# pixels — so the surfaces gated on NaN "no coverage" (the union canvas, coverage
# levelling, per-panel photometry, the uncovered-fraction note, the depth map,
# Auto's border trim) are finally in front of a browser. It stacks it, prints the
# trim Auto would apply to it (a trim above ~15 % of the canvas is a BUG, not a
# ragged edge — AGENTS.md §1), prints **every sentence the app says about that
# mosaic side by side** (the panel map's and the health panel's — see step 4c:
# three runs running, the finding was in the *gap between* two of them, and every
# one of those passes reported CLEAN), and writes its shots to $SHOTS/mosaic/ so
# the page-height baselines measured on the field sample are not disturbed. With
# --editor, the editor is driven on the mosaic run too. Opt-in because the field
# sample is what keeps a standard pass fast.
#
# --big exists because BOTH samples above fit inside the editor's preview proxy,
# so the whole of its decimated-proxy surface has never been drawn in a browser.
# `seestack/edit/proxy.py` strides only above PROXY_MAX_PX (1500); the field
# sample is 480 px wide and the mosaic's union canvas ~907, so `get_proxy` hands
# both back at proxy_scale == 1.0. Everything gated on a *shrunk* preview is
# therefore structurally unreachable — the five preview<->export advisories
# (sharpen, deconvolution, denoise, hot pixels, star reduction), the
# preview-scale caption, and the whole of "Check it at full size": its button,
# its modal, its navigator, its X-Loupe-Window marker and its split comparison,
# ~250 lines of the PRIORITY-1 screen, pinned by jsdom alone. Even --editor,
# which clicks every op in the Add menu, could not reach any of it. The owner's
# own mosaics are ~3494x2470 and up, i.e. that is his everyday state.
# --big loads a third sample (`POST /api/sample` with {"shape":"big"}): the same
# 2x2 mosaic — same grid, same 82 % step, same uneven depth, same hazy panel,
# same ragged corners — shot with 900x600 panels, so its union canvas is
# 1694x1150 and the editor's preview is decimated by exactly 2. That is the
# *smallest* canvas that reaches this surface at all, chosen because stacking
# cost grows with the pixels and a pass nobody runs finds nothing: it adds about
# a minute over --mosaic. It prints what the app answers about the shrunk
# preview (`/editor/loupe-info`) and, with --editor, drives the editor on it.
#
# --calibration exists because NO PASS HAS EVER HELD A MASTER. The scratch
# install's calibration registry is empty on every run ever recorded, so the
# Calibration page's masters list, `/api/calibration/incoming`'s one-click
# "you already have darks, shall I build one?" offer, `/api/calibration/defects`
# and its repair offer, the per-target `calibration-suggestions`,
# `auto_bind_calibration`, and the "darks were applied" half of the stack-health
# vocabulary have only ever been photographed in their EMPTY state — while the
# health card tells the owner, on every single stack, that adding master darks is
# the biggest cleanup available to him. The app has been pushing him toward a
# state its own tooling had never once occupied. That is the same shape of hole as
# the missing observing site, the empty `incoming/` and the click-only Compare
# modes, and every one of those found a real bug on its first run; this one found
# v0.455.0 before it was even finished (a folder of darks under `incoming/` was
# being ingested as a target of lights).
#
# It writes generated dark and flat frames into the scratch `incoming/` with the
# app's own `webapp.sample_data.write_sample_calibration_frames` — matching the
# sample lights' sensor size, EXPTIME, GAIN and CCD-TEMP, so the master is a
# *matching* one and the registry does not quietly refuse it — then lets the app
# **discover and build them itself** through the endpoints a beginner would use,
# turns on `auto_bind_calibration`, and stacks after that so the calibrated branch
# of every downstream sentence is the one on screen.
#
# ⚠ READ THIS BEFORE BELIEVING A CALIBRATED SAMPLE PICTURE. The sample's *lights*
# carry no hot pixels and no vignette — their pixels are pinned bit-identical by
# the baselines every earlier pass was measured on — so the darks' planted hot
# pixels are not in the lights, and repairing them costs a few interpolated
# pixels and gains nothing. That is fine for what the flag is for (putting the
# defect census and its repair offer in front of a browser) and dishonest if read
# as "calibration improved this picture". The flat's vignette is deliberately
# gentle for the same reason. It is a flag, not the default, because an install
# with masters is a *further along* install, not a more representative one, and
# turning it on by default would move every page-height baseline at once.
#
# --empty exists because every measurement this script has ever taken was of the
# sample-loaded app, so the screens a beginner meets *first* — an empty Dashboard,
# Library, Gallery, life list — had never been in front of a browser. It boots a
# second app on its own empty data root (port 8812, its own $DOGFOOD_DIR/empty/
# scratch) and runs the same probe with no target, so it can follow a normal pass
# without disturbing it. Roughly a minute once playwright is installed.
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
DO_SERVE=0; DO_STACK=1; DO_PROBE=1; DO_BUILD=0; DO_EMPTY=0; DO_EDITOR=0; DO_MOSAIC=0
DO_BIG=0
DO_SITE=1; DO_LAG=0; DO_CAL=0
# How many aged subs --incoming-lag leaves in the scratch incoming/, and how old
# it makes them. Eleven days is the observer's own measurement; the count is
# small on purpose (this seeds a *state*, not a workload).
DOGFOOD_LAG_SUBS="${DOGFOOD_LAG_SUBS:-7}"
DOGFOOD_LAG_DAYS="${DOGFOOD_LAG_DAYS:-11}"
# …and how many of the seeded files are ones the app CANNOT READ. A sub that
# will not parse never becomes a frame row, so it waits for ever and the note has
# to say so instead of offering a scan (v0.452.1). That branch is reachable only
# by a file that is damaged AND a whole-library scan that has recorded it, so
# seeding the file alone would leave the new sentence as unphotographable as the
# empty `incoming/` this flag exists to fix. 0 skips the scan and gives the
# pre-v0.452.1 shape exactly.
DOGFOOD_LAG_DAMAGED="${DOGFOOD_LAG_DAMAGED:-1}"
# Where the scratch install pretends to observe from. A round mid-northern
# latitude: obviously synthetic, and the band most Seestar owners are in, so the
# planner's answers are representative rather than polar or equatorial. It is
# the SCRATCH install's setting, never the sample's data — nothing shipped
# claims to have been shot here.
DOGFOOD_SITE="${DOGFOOD_SITE:-40.0,-2.0}"
for arg in "$@"; do
  case "$arg" in
    --serve) DO_SERVE=1 ;;
    --no-stack) DO_STACK=0 ;;
    --no-probe) DO_PROBE=0 ;;
    --build) DO_BUILD=1 ;;
    --empty) DO_EMPTY=1 ;;
    --editor) DO_EDITOR=1 ;;
    --mosaic) DO_MOSAIC=1 ;;
    --big) DO_BIG=1 ;;
    --no-site) DO_SITE=0 ;;
    --incoming-lag) DO_LAG=1 ;;
    --calibration) DO_CAL=1 ;;
    # The whole header block, found rather than hard-coded: a fixed line count
    # silently truncates -h every time the header grows, which it has.
    -h|--help) sed -n '2,/^[^#]/p' "$0" | sed '$d'; exit 0 ;;
    *) echo "unknown flag: $arg" >&2; exit 2 ;;
  esac
done

if [ "$DO_EMPTY" = 1 ]; then
  # Its own root, its own port and its own shots, so an --empty pass can follow a
  # normal one (or run beside a --serve'd one) without clobbering either. The data
  # root is wiped first: "first run" means first run, not "whatever was left here".
  DEFAULT_PORT=8812
  DATA="$DOGFOOD_DIR/empty/data"
  SHOTS="$DOGFOOD_DIR/empty/shots"
  SERVER_LOG="$DOGFOOD_DIR/server-empty.log"
  rm -rf "$DOGFOOD_DIR/empty"
  DO_STACK=0
  # A first-run app has no observing site, and the screens that say so are
  # exactly what this pass exists to photograph.
  DO_SITE=0
else
  DEFAULT_PORT=8811
  DATA="$DOGFOOD_DIR/data"
  SHOTS="$DOGFOOD_DIR/shots"
  SERVER_LOG="$DOGFOOD_DIR/server.log"
fi
PORT="${ASTROSTACK_PORT:-$DEFAULT_PORT}"
BASE="http://127.0.0.1:${PORT}"
mkdir -p "$DATA" "$SHOTS"
echo "dogfood scratch: $DOGFOOD_DIR"
if [ "$DO_EMPTY" = 1 ]; then
  echo "-- FIRST-RUN pass: no sample, no stack, no targets"
fi

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
  python -m webapp.main > "$SERVER_LOG" 2>&1 &
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
    echo "server died on boot — $SERVER_LOG:" >&2
    tail -20 "$SERVER_LOG" >&2
    exit 1
  fi
  sleep 1
done
curl -sf "$BASE/api/system" >/dev/null || { echo "server never answered" >&2; exit 1; }

# 3. Real data. The bundled sample is a genuine target with frames, so the app
#    is exercised the way a user's is rather than through empty states — except
#    under --empty, where the empty states ARE the thing being measured.
if [ "$DO_EMPTY" = 0 ] && \
   [ "$(curl -sf "$BASE/api/targets" | tr -d '[:space:]')" = "[]" ]; then
  echo "-- loading the bundled sample target"
  curl -sf -X POST "$BASE/api/sample" >/dev/null || echo "warn: sample load failed"
fi
# The FIELD sample by name, not `/api/targets`' first row. That list is ordered
# by activity, so the moment a second demo is loaded and stacked the "sample"
# leg below can silently become the mosaic — which is not a cosmetic mix-up: the
# §1 page-height baselines in docs/PROCESS-NOTES.md were all measured on the
# field sample, and its $SHOTS would then hold a mosaic's numbers under the same
# filenames, with both editor drives running twice on one target. Observed on a
# `--big` pass, 2026-09-14. Falls back to the first row so a library with no
# sample (a --serve against real data) behaves exactly as before.
SAFE="$(curl -sf "$BASE/api/sample" \
        | python -c 'import json,sys; print(json.load(sys.stdin).get("safe") or "")' \
        2>/dev/null || true)"
if [ -z "$SAFE" ]; then
  SAFE="$(curl -sf "$BASE/api/targets" \
          | python -c 'import json,sys; t=json.load(sys.stdin); print(t[0]["safe_name"] if t else "")' \
          2>/dev/null || true)"
fi
echo "-- target: ${SAFE:-<none>}"

# 3b. The mosaic sample (--mosaic): a second target, four overlapping panels of
#     one shared sky, uneven depth, one hazy panel, a ragged union canvas. It is
#     the only data this script can produce on which a mosaic-scale Auto/editor
#     claim means anything (AGENTS.md §1).
MOSAIC_SAFE=""
if [ "$DO_MOSAIC" = 1 ] && [ "$DO_EMPTY" = 0 ]; then
  echo "-- loading the bundled MOSAIC sample (2x2 panels)"
  curl -sf -X POST "$BASE/api/sample" -H 'Content-Type: application/json' \
       -d '{"shape":"mosaic"}' >/dev/null || echo "warn: mosaic sample load failed"
  MOSAIC_SAFE="$(curl -sf "$BASE/api/sample" \
                 | python -c 'import json,sys; print(json.load(sys.stdin).get("mosaic_safe") or "")' \
                 2>/dev/null || true)"
  echo "-- mosaic target: ${MOSAIC_SAFE:-<none>}"
fi

# 3c. The full-size mosaic sample (--big): the same 2x2, shot with 900x600
#     panels, so the union canvas is past the editor's 1500 px proxy cap and the
#     live preview is finally a *decimated* one. It is the only data this script
#     can produce on which the editor's whole shrunk-preview surface — the five
#     preview<->export advisories and "Check it at full size" — exists at all.
BIG_SAFE=""
if [ "$DO_BIG" = 1 ] && [ "$DO_EMPTY" = 0 ]; then
  echo "-- loading the bundled FULL-SIZE mosaic sample (900x600 panels)"
  curl -sf -X POST "$BASE/api/sample" -H 'Content-Type: application/json' \
       -d '{"shape":"big"}' >/dev/null || echo "warn: big sample load failed"
  BIG_SAFE="$(curl -sf "$BASE/api/sample" \
              | python -c 'import json,sys; print(json.load(sys.stdin).get("big_safe") or "")' \
              2>/dev/null || true)"
  echo "-- full-size target: ${BIG_SAFE:-<none>}"
fi

# 4. A finished picture, so the picture-shaped surfaces (hero card, Gallery,
#    History, the editor) have something real to render rather than self-hiding.
stack_target() {  # $1 = safe name, $2 = what to call it in the log
  local safe="$1" label="$2"
  [ -n "$safe" ] || return 0
  [ "$(curl -sf "$BASE/api/targets/$safe/stack-runs" | tr -d '[:space:]')" = "[]" ] || return 0
  echo "-- stacking the $label (this is the slow part; --no-stack skips it)"
  local job state
  job="$(curl -sf -X POST "$BASE/api/targets/$safe/process" \
         | python -c 'import json,sys; print(json.load(sys.stdin).get("job_id",""))' 2>/dev/null || true)"
  for _ in $(seq 1 180); do
    state="$(curl -sf "$BASE/api/jobs/$job" \
             | python -c 'import json,sys; print(json.load(sys.stdin).get("state",""))' 2>/dev/null || true)"
    # The engine's own terminal set (`webapp/jobs.py::_TERMINAL`). A success is
    # "done", never "finished" — waiting on the wrong word costs the whole
    # 180×2s budget on every run, long after the picture is on disk.
    case "$state" in
      done|error|cancelled|interrupted) echo "-- process job ($label): $state"; break ;;
    esac
    sleep 2
  done
}

# 3c. An observing site, in the SCRATCH install's Settings — see --no-site in the
#     header. Without it the whole "plan a night" half of the app is in its empty
#     state, so no dogfood pass had ever seen those screens with data. It goes in
#     Settings rather than into the sample's FITS on purpose: a header location is
#     something the planner *plans from*, so a sample claiming a site would tell a
#     real owner elsewhere in the world which targets are up, computed for the
#     wrong hemisphere. The sample's generated pixels stay bit-identical.
if [ "$DO_SITE" = 1 ]; then
  SITE_LAT="${DOGFOOD_SITE%%,*}"
  SITE_LON="${DOGFOOD_SITE##*,}"
  echo "-- setting the scratch install's observing site to ${SITE_LAT}, ${SITE_LON}"
  echo "   (Settings only — nothing about the sample data changes; --no-site skips)"
  curl -sf -X PUT "$BASE/api/settings" -H 'Content-Type: application/json' \
       -d "{\"site_lat\": ${SITE_LAT}, \"site_lon\": ${SITE_LON}}" >/dev/null \
    || echo "warn: could not set the site — the plan pages will stay in their empty state"
  # …and say whether it actually took, plus what the planner now has to show. A
  # pass that silently failed here would look exactly like the coverage hole it
  # is meant to close. Printed, never asserted — a finder, like everything else
  # this script prints.
  curl -sf "$BASE/api/plan/tonight" \
    | python -c '
import json, sys
d = json.load(sys.stdin) or {}
src = d.get("location_source")
rows = d.get("targets") or []
print("   [tonight] location_source=%s, %d row(s) to show" % (src, len(rows)))
if src != "settings":
    print("   [tonight] the site did NOT take — the plan half is still empty")
' 2>/dev/null || echo "   [tonight] could not read /api/plan/tonight"
fi

# 3d. Subs in `incoming/` that never reached the library (--incoming-lag). Every
#     pass ever recorded left the scratch `incoming/` EMPTY — the sample arrives
#     through `POST /api/sample`, which writes straight into the library — so no
#     screen that depends on that folder holding files has ever been in front of
#     a browser. That is the same shape of hole as the missing observing site
#     (v0.436.1) and the unreachable Split/Blink modes (v0.440.2), and the lesson
#     AGENTS.md §7 keeps re-learning: a state you can only reach by *putting the
#     app into it* is a state no route table will ever photograph.
#
#     It is a FLAG rather than the default, and the distinction is worth keeping:
#     an observing site is data a real install *has*, so a pass without one was
#     measuring an unrepresentative app. Eleven-day-old unimported subs are a
#     *fault*. Photographing one by default would put a warning banner into every
#     Dashboard screenshot and into every page-height baseline, and would make
#     "CLEAN" a weaker statement rather than a stronger one.
#
#     The subs are written with the app's own `_write_sample_fits`, so they are
#     the same shape as everything else the scratch install holds, and they are
#     aged so the note's own "has this folder stopped moving?" rule is satisfied
#     (`webapp.incominglag.LAG_MIN_AGE_S`). The quiet period is stretched for the
#     same reason it is stretched nowhere else: the watcher would otherwise hand
#     the batch off mid-pass and import the very state this is seeding.
#
#     One of the seeded files is deliberately UNREADABLE, and is scanned once
#     before the rest land. A sub whose FITS header will not parse never becomes
#     a frame row, so it waits for ever: the note stops being about a delay and
#     says so instead of offering a scan (v0.452.1). Reaching that sentence needs
#     BOTH a damaged file and a whole-library scan that has recorded it, so
#     seeding the file alone would leave the new copy exactly as unphotographable
#     as the empty `incoming/` this flag exists to fix. Scanning first is what
#     leaves the folder MIXED — mostly waiting, partly damaged — which is the
#     state a real install is in and the one where the two sentences have to sit
#     beside each other and still read as one paragraph. `DOGFOOD_LAG_DAMAGED=0`
#     gives the pre-v0.452.1 shape back.
if [ "$DO_LAG" = 1 ]; then
  echo "-- seeding ${DOGFOOD_LAG_SUBS} sub(s) into incoming/ that the library has no row for"
  echo "   (a FAULT state, on purpose — --incoming-lag only; the default pass stays healthy)"
  curl -sf -X PUT "$BASE/api/settings" -H 'Content-Type: application/json' \
       -d '{"watch_poll_interval_s": 5, "watch_quiet_period_s": 900}' >/dev/null \
    || echo "warn: could not retune the watcher — it may import the seeded subs mid-pass"
  # The damaged sub goes in FIRST and is scanned, because the "these can't be
  # read" branch needs both halves: a file that will not parse, and a
  # whole-library scan that has recorded it (only a whole-library scan may write
  # that record — see webapp/unreadablesubs.py). Doing it before the good subs
  # land is what leaves the folder in the MIXED state, which is the one a real
  # install is in: mostly waiting, partly damaged.
  if [ "$DOGFOOD_LAG_DAMAGED" -gt 0 ] 2>/dev/null; then
    INCOMING="$DATA/incoming/IC 360_sub" python - "$DOGFOOD_LAG_DAMAGED" "$DOGFOOD_LAG_DAYS" <<'PY'
import os, pathlib, sys, time

n, days = int(sys.argv[1]), float(sys.argv[2])
d = pathlib.Path(os.environ["INCOMING"])
d.mkdir(parents=True, exist_ok=True)
when = time.time() - days * 86400
for i in range(n):
    # The shape the owner's six damaged subs really have: a healthy sub's worth
    # of bytes with no SIMPLE card in them, so neither the zero-byte
    # "still copying" skip nor any size check can see it — only parsing can.
    p = d / f"damaged_{i:03d}.fit"
    p.write_bytes(b"\x00" * 4_152_960)
    os.utime(p, (when, when))
print(f"   wrote {n} UNREADABLE sub(s) into {d} — a file with no FITS header")
PY
    # One whole-library scan, so the app actually opens them and writes down what
    # it found. Bounded and fail-soft: a pass that could not scan should say so
    # and carry on, not die on a side note.
    LAG_JOB="$(curl -sf -X POST "$BASE/api/scan" -H 'Content-Type: application/json' \
                 -d '{}' | python -c 'import json,sys; print(json.load(sys.stdin).get("job_id",""))' \
               2>/dev/null || true)"
    if [ -n "$LAG_JOB" ]; then
      for _ in $(seq 1 60); do
        LAG_STATE="$(curl -sf "$BASE/api/jobs/$LAG_JOB" \
                     | python -c 'import json,sys; print(json.load(sys.stdin).get("state",""))' \
                     2>/dev/null || true)"
        case "$LAG_STATE" in done|error|cancelled|interrupted) break ;; esac
        sleep 2
      done
      echo "   scanned them once so the app has read them (job $LAG_STATE)"
    else
      echo "   warn: could not start the scan — the damaged subs will read as merely waiting"
    fi
  fi
  INCOMING="$DATA/incoming/IC 360_sub" python - "$DOGFOOD_LAG_SUBS" "$DOGFOOD_LAG_DAYS" <<'PY'
import os, pathlib, sys, time
from webapp.sample_data import _write_sample_fits

n, days = int(sys.argv[1]), float(sys.argv[2])
d = pathlib.Path(os.environ["INCOMING"])
d.mkdir(parents=True, exist_ok=True)
when = time.time() - days * 86400
for i in range(n):
    p = d / f"frame_{i:03d}.fit"
    _write_sample_fits(p, index=i, star_shift=(0.0, 0.0))
    os.utime(p, (when, when))
print(f"   wrote {n} sub(s) into {d}, dated {days:g} days ago")
PY
  # Say what the app now reports, the way the site step does — a pass that
  # silently seeded nothing would look exactly like the coverage hole it closes.
  for _ in $(seq 1 24); do
    LAG_JSON="$(curl -sf "$BASE/api/incoming-lag" || true)"
    case "$LAG_JSON" in *'"n_waiting":0'*|"") sleep 3 ;; *) break ;; esac
  done
  printf '%s' "$LAG_JSON" | python -c '
import json, sys
raw = sys.stdin.read()
d = json.loads(raw) if raw.strip() else {}
if not d.get("checked"):
    print("   [incoming-lag] the watcher has no listing yet — the note will stay silent")
print("   [incoming-lag] %d sub(s) waiting across %d folder(s): %s"
      % (d.get("n_waiting", 0), d.get("n_folders", 0),
         ", ".join("%s +%d" % (i.get("folder") or "(loose)", i.get("n_waiting", 0))
                   for i in d.get("items", [])) or "none"))
# Of those, the ones nothing can ever import. A seeded damaged file that reads as
# 0 here means the record was not written, and the note is back to offering a
# scan that cannot help — which is the whole thing this seeding exists to show.
print("   [incoming-lag] %d of them cannot be read at all"
      % d.get("n_unreadable", 0))
' 2>/dev/null || echo "   [incoming-lag] could not read /api/incoming-lag"
fi

wait_job() {  # wait_job <job_id> [tries] -> prints the final state
  [ -n "${1:-}" ] || { echo "(no job)"; return 0; }
  local state=""
  for _ in $(seq 1 "${2:-90}"); do
    state="$(curl -sf "$BASE/api/jobs/$1" \
             | python -c 'import json,sys; print(json.load(sys.stdin).get("state",""))' \
             2>/dev/null || true)"
    case "$state" in done|error|cancelled|interrupted) break ;; esac
    sleep 2
  done
  echo "${state:-unknown}"
}

# 3e. Master darks and flats (--calibration). See the header block: the scratch
#     install's calibration registry has been EMPTY on every pass ever recorded,
#     so every surface built around a master has only been photographed in its
#     empty state — on an app that tells the owner, on every stack, that adding
#     darks is the single biggest cleanup available to him.
#
#     The frames go into `incoming/` and the app is then asked to find them
#     ITSELF, through `/api/calibration/incoming` and its one-click build, rather
#     than through the manual build form: that is the path a beginner takes, it is
#     the path with the most machinery behind it, and driving it end to end is what
#     makes the pass evidence about the feature rather than about a fixture. Since
#     v0.455.0 those folders are also the ones the scan deliberately leaves alone,
#     so the same seeding exercises that skip as a side effect.
if [ "$DO_CAL" = 1 ] && [ "$DO_EMPTY" = 0 ]; then
  echo "-- seeding generated darks and flats into incoming/, for the app to find"
  echo "   (NB the sample's lights carry no hot pixels and no vignette, so these"
  echo "    masters reach the SURFACES without improving the picture — see --help)"
  INCOMING="$DATA/incoming" python - <<'PY'
import os, pathlib
from webapp.sample_data import write_sample_calibration_frames

root = pathlib.Path(os.environ["INCOMING"])
for name, kind in (("Darks 10s", "dark"), ("Flats", "flat")):
    n = write_sample_calibration_frames(root / name, kind)
    print(f"   wrote {n} {kind} frame(s) into {name}/")
PY
  # What the app makes of them on its own. A pass where this lists nothing has
  # seeded frames the discovery cannot see, and every surface below it is still
  # unreached — the same silent failure the observing site's `location_source`
  # line and --big's `proxy_scale` line exist to stop.
  CAL_OFFER="$(curl -sf "$BASE/api/calibration/incoming" || echo '{}')"
  printf '%s' "$CAL_OFFER" | python -c '
import json, sys
raw = sys.stdin.read()
d = json.loads(raw) if raw.strip() else {}
rows = d.get("folders") or []
if not rows:
    print("   [offer] NOTHING FOUND — the seeded frames are invisible to the app,")
    print("   [offer] so every calibration surface below is STILL unreached")
for f in rows:
    print("   [offer] %s -> %s master, %d frame(s), %s  (have one already: %s)"
          % (f.get("name"), f.get("kind"), f.get("n_frames", 0),
             f.get("suggested_name"), bool(f.get("have_master"))))
' 2>/dev/null || echo "   [offer] could not read /api/calibration/incoming"
  # Only the folders the app says it has no master for. Building the rest would
  # duplicate a master on every re-run against the same scratch root — the offer
  # already answers this (`have_master`), and ignoring its answer would make the
  # pass a worse witness of the feature than the feature deserves.
  CAL_IDS="$(printf '%s' "$CAL_OFFER" | python -c '
import json, sys
raw = sys.stdin.read()
d = json.loads(raw) if raw.strip() else {}
print(" ".join(str(f["id"]) for f in (d.get("folders") or [])
               if not f.get("have_master")))
' 2>/dev/null || true)"
  for cid in $CAL_IDS; do
    CAL_JOB="$(curl -sf -X POST "$BASE/api/calibration/incoming/$cid/build" \
                 | python -c 'import json,sys; print(json.load(sys.stdin).get("job_id",""))' \
               2>/dev/null || true)"
    echo "   built $cid: $(wait_job "$CAL_JOB")"
  done
  # …and what the registry holds now, plus the census the whole defect-repair
  # offer is built on. Printed, never asserted — a finder, like everything else.
  curl -sf "$BASE/api/calibration/masters" | python -c '
import json, sys
rows = json.load(sys.stdin) or []
print("   [masters] %d in the registry" % len(rows))
for m in rows:
    print("   [masters] %s · %s · %sx%s · %s frame(s)"
          % (m.get("kind"), m.get("name"), m.get("width_px"), m.get("height_px"),
             m.get("n_frames")))
' 2>/dev/null || echo "   [masters] could not read /api/calibration/masters"
  curl -sf "$BASE/api/calibration/defects" | python -c '
import json, sys
d = json.load(sys.stdin) or {}
print("   [defects] offer=%s · %s" % (d.get("offer_repair"), d.get("summary") or d))
' 2>/dev/null || echo "   [defects] could not read /api/calibration/defects"
  # Auto-bind, so the stack below actually APPLIES them. It is off by default in
  # the product (§9) and turning it on is the whole point here: the "darks were
  # applied" branch of the health vocabulary, and the auto-bind path itself, are
  # otherwise as unreachable as the registry was.
  curl -sf -X PUT "$BASE/api/settings" -H 'Content-Type: application/json' \
       -d '{"auto_bind_calibration": true}' >/dev/null \
    && echo "   auto_bind_calibration: on (so the stack below is a calibrated one)" \
    || echo "   warn: could not turn on auto_bind_calibration — the stack stays raw"
  # …and a target that ALREADY has a run must be re-processed, or this whole
  # flag silently measures the uncalibrated stack a previous pass left in the
  # scratch root. `stack_target` returns early on any existing run (right for
  # every other flag, wrong for this one, and the failure is invisible: the
  # health note simply keeps saying "no darks or flats were applied", which is
  # exactly the empty state --calibration exists to escape). Found on this
  # flag's own first run.
  if [ "$DO_STACK" = 1 ] && [ -n "$SAFE" ] \
     && [ "$(curl -sf "$BASE/api/targets/$SAFE/stack-runs" | tr -d '[:space:]')" != "[]" ]; then
    echo "   the sample already has a run from an earlier pass — re-processing it"
    echo "   so the newest picture is a CALIBRATED one (this is the slow part)"
    CAL_STACK_JOB="$(curl -sf -X POST "$BASE/api/targets/$SAFE/process" \
                       | python -c 'import json,sys; print(json.load(sys.stdin).get("job_id",""))' \
                     2>/dev/null || true)"
    echo "   re-process: $(wait_job "$CAL_STACK_JOB" 180)"
  fi
fi

run_id_of() {  # newest stack run id for a target, or empty
  [ -n "$1" ] || return 0
  curl -sf "$BASE/api/targets/$1/stack-runs" \
    | python -c 'import json,sys; r=json.load(sys.stdin); print(r[0]["id"] if r else "")' \
    2>/dev/null || true
}

if [ "$DO_STACK" = 1 ]; then
  stack_target "$SAFE" "sample"
  stack_target "$MOSAIC_SAFE" "mosaic sample"
  stack_target "$BIG_SAFE" "full-size mosaic sample"
fi

# 4a-bis. What the app says about the *shrunk* preview — the question only the
#     full-size sample can ask. `available: false` here with proxy_scale 1 would
#     mean the sample is not big enough after all and every surface below it is
#     still unreached, which is exactly the silent failure --big exists to stop
#     (the same trap the observing site's `location_source` line closed).
if [ -n "$BIG_SAFE" ]; then
  BIG_RUN="$(run_id_of "$BIG_SAFE")"
  if [ -n "$BIG_RUN" ]; then
    curl -sf "$BASE/api/targets/$BIG_SAFE/stack-runs/$BIG_RUN/editor/loupe-info" \
      | python -c '
import json, sys
d = json.load(sys.stdin)
scale = d.get("proxy_scale") or 1.0
canvas = "%sx%s" % (d.get("canvas_width"), d.get("canvas_height"))
if scale <= 1.0:
    print("-- full-size preview: proxy_scale %.1f on a %s canvas <-- NOT decimated:"
          % (scale, canvas))
    print("   the sample is too small, and every proxy-gated surface is STILL unreached")
else:
    print("-- full-size preview: canvas %s, shrunk to 1/%.0f for the editor"
          % (canvas, scale))
    print("   [full-size check] available=%s%s"
          % (d.get("available"), "  reason: %s" % d["reason"] if d.get("reason") else ""))
    print("   so the five preview<->export advisories and the loupe are all live here")
' 2>/dev/null || echo "-- full-size preview: could not read /editor/loupe-info"
  fi
fi

# 4b. What Auto would trim off the mosaic. AGENTS.md §1: on a mosaic canvas a
#     trim above ~15 % of the canvas is a BUG (it is cropping to the panel
#     overlaps), not a ragged edge — and it is invisible on the single field,
#     whose canvas has no uncovered pixel to trim. Printed, not asserted: this
#     script is a finder, and anything it turns up still needs a real test.
if [ -n "$MOSAIC_SAFE" ]; then
  MOSAIC_RUN="$(run_id_of "$MOSAIC_SAFE")"
  if [ -n "$MOSAIC_RUN" ]; then
    curl -sf "$BASE/api/targets/$MOSAIC_SAFE/stack-runs/$MOSAIC_RUN/editor/trim-suggestion" \
      | python -c '
import json, sys
d = json.load(sys.stdin)
crop = d.get("crop")
if not d.get("is_mosaic"):
    print("-- mosaic trim: the run does NOT read as a mosaic (that is itself a bug)")
elif not crop:
    print("-- mosaic trim: none suggested (nothing worth trimming)")
else:
    kept = (crop["x1"] - crop["x0"]) * (crop["y1"] - crop["y0"])
    trimmed = 1.0 - kept
    flag = "  <-- ABOVE ~15%: this is D1-shaped, look at it" if trimmed > 0.15 else ""
    print(f"-- mosaic trim: Auto would cut {trimmed:.1%} of the canvas{flag}")
' 2>/dev/null || echo "-- mosaic trim: could not read the trim suggestion"

    # 4c. …and everything the app SAYS about that same mosaic, printed together.
    #     Three runs in a row have now found their bug in the gap between two of
    #     these sentences rather than in any one of them — a "flat" seam number
    #     answering a question about the *level* to someone looking at a
    #     difference in *depth* (v0.406.0), the History chip repeating it
    #     (v0.406.1), and the panel map drawing a hole where the thin panel was
    #     and writing "no part of the picture is being held back" over it while
    #     the health panel called a quarter of the same picture 1.4x grainier
    #     (v0.406.2). Every one of those passes reported CLEAN, because a clean
    #     pass is a statement about console errors, not about sentences.
    #     So: read these as one paragraph and ask whether a beginner could hold
    #     all of them at once. Printed, never asserted — a finder, as above.
    echo "-- what the app SAYS about this mosaic (read them together — the last"
    echo "   three findings were all two of these disagreeing, not one of them wrong):"
    echo "   [NB] these two are the SERVER-side half. The Target page's own"
    echo "   prescriptive cards (readiness goal, grain projection, next best move,"
    echo "   plateau verdict) are computed in the frontend, so the browser probe"
    echo "   prints them — look for \"what the Target page SAYS\" further down."
    curl -sf "$BASE/api/targets/$MOSAIC_SAFE/mosaic-map" \
      | python -c '
import json, sys
d = json.load(sys.stdin)
if not d:
    print("   [panel map] nothing at all (the target does not read as a mosaic)")
else:
    rows, cols = d["rows"], d["cols"]
    cells = {(p["row"], p["col"]) for p in d["panels"]}
    holes = [(r, c) for r in range(rows) for c in range(cols) if (r, c) not in cells]
    n, thin, text = len(d["panels"]), d["thin"] is not None, d["text"]
    where = ", holes at %s" % holes if holes else ""
    print("   [panel map] %d panels on a %dx%d grid%s, thin=%s"
          % (n, rows, cols, where, thin))
    print("   [panel map] %s" % text)
' 2>/dev/null || echo "   [panel map] could not read it"
    curl -sf "$BASE/api/targets/$MOSAIC_SAFE/stack-health" \
      | python -c '
import json, sys
d = json.load(sys.stdin) or {}
for note in d.get("notes", []):
    print("   [health/%s] %s" % (note.get("kind"), note.get("message")))
' 2>/dev/null || echo "   [health] could not read it"
  fi
fi

# 4d. What a CALIBRATED install says about itself (--calibration). The health
#     card's calibration note is the one sentence every pass has ever seen in its
#     "no darks or flats were applied" form, because no pass has ever had any —
#     so read it here as the paragraph it now belongs to, beside the per-target
#     advice that is supposed to have gone quiet.
if [ "$DO_CAL" = 1 ] && [ -n "$SAFE" ]; then
  echo "-- what a CALIBRATED install SAYS (the branch no pass has ever reached):"
  # First, unambiguously: did the newest run actually USE a master? The health
  # note going quiet is consistent with "applied" *and* with "this surface never
  # speaks", and a pass that cannot tell them apart is the empty state wearing a
  # better hat. `/options` reverse-maps the run's server-resolved calibration
  # paths back to master ids, so this is the run's own provenance.
  CAL_RUN="$(run_id_of "$SAFE")"
  if [ -n "$CAL_RUN" ]; then
    curl -sf "$BASE/api/targets/$SAFE/stack-runs/$CAL_RUN/options" \
      | python -c '
import json, sys
o = (json.load(sys.stdin) or {}).get("options") or {}
used = {k: o[k] for k in
        ("dark_master_id", "flat_master_id", "flat_dark_master_id",
         "bias_master_id") if o.get(k)}
print("   [run %s] masters actually applied: %s"
      % (sys.argv[1], used or "NONE — the stack never saw them"))
' "$CAL_RUN" 2>/dev/null \
      || echo "   [run $CAL_RUN] could not read its stack options"
  fi
  curl -sf "$BASE/api/targets/$SAFE/stack-health" \
    | python -c '
import json, sys
d = json.load(sys.stdin) or {}
notes = d.get("notes", [])
cal = [n for n in notes if "calib" in str(n.get("kind", ""))]
if not cal:
    print("   [health/calibration] SILENT — the note withdrew. Read the [run] line")
    print("   [health/calibration] above for which reason: masters applied (right),")
    print("   [health/calibration] or NONE applied and this surface never speaks.")
for n in cal:
    print("   [health/%s] %s" % (n.get("kind"), n.get("message")))
' 2>/dev/null || echo "   [health] could not read it"
  curl -sf "$BASE/api/targets/$SAFE/calibration-suggestions" \
    | python -c '
import json, sys
d = json.load(sys.stdin) or {}
print("   [suggestions] %s" % json.dumps(d)[:600])
' 2>/dev/null || echo "   [suggestions] could not read it"
fi

# 5. The browser half. Two independent drives share one playwright install and
#    one shots dir, so the install is hoisted out of both: `--editor --no-probe`
#    has to mean "drive the editor, skip the page sweep", not "do nothing".
#      5a. the page probe — full-page screenshots at desktop AND phone widths,
#          plus the overflow check that found the clipped Gallery button;
#      5b. the editor drive (--editor) — 5a *photographs* the editor in the one
#          state it opens in; this one clicks (adds every op, checks the live
#          preview re-renders).
#    Both are finders, not tests: anything either turns up still needs a real
#    regression test in the suite.
if [ "$DO_PROBE" = 1 ] || [ "$DO_EDITOR" = 1 ]; then
  PW_DIR="$DOGFOOD_DIR/pw"
  if [ ! -d "$PW_DIR/node_modules/playwright" ]; then
    echo "-- installing playwright into $PW_DIR (not into frontend/)"
    mkdir -p "$PW_DIR"
    (cd "$PW_DIR" && PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1 \
       npm install --silent --no-fund --no-audit playwright >/dev/null 2>&1) \
      || echo "warn: could not install playwright — skipping the browser probe"
  fi
  if [ -d "$PW_DIR/node_modules/playwright" ]; then
    RUN_ID="$(run_id_of "$SAFE")"
    if [ "$DO_PROBE" = 1 ]; then
      echo "-- probing the running app"
      # Copied in rather than run from the repo: an ESM `import "playwright"`
      # resolves from the *script's* directory, and NODE_PATH doesn't apply.
      cp "$REPO/scripts/dogfood_probe.mjs" "$PW_DIR/probe.mjs"
      (cd "$PW_DIR" && BASE_URL="$BASE" SHOTS_DIR="$SHOTS" TARGET_SAFE="$SAFE" \
         TARGET_RUN_ID="$RUN_ID" node probe.mjs) || echo "warn: probe failed"
    fi
    if [ "$DO_EDITOR" = 1 ]; then
      if [ -n "$SAFE" ] && [ -n "$RUN_ID" ]; then
        echo "-- driving the editor (adding every op; this takes a few minutes)"
        cp "$REPO/scripts/dogfood_editor.mjs" "$PW_DIR/editor.mjs"
        (cd "$PW_DIR" && BASE_URL="$BASE" SHOTS_DIR="$SHOTS" TARGET_SAFE="$SAFE" \
           TARGET_RUN_ID="$RUN_ID" node editor.mjs) || echo "warn: editor drive failed"
      else
        echo "-- --editor: no stacked target to edit, skipping"
      fi
    fi
    # The same two drives again on the mosaic, into their own shots dir: the §1
    # page-height baselines were all measured on the field sample, so a mosaic
    # shot must not overwrite one and be compared against it by mistake.
    if [ -n "$MOSAIC_SAFE" ]; then
      MOSAIC_RUN="$(run_id_of "$MOSAIC_SAFE")"
      mkdir -p "$SHOTS/mosaic"
      if [ "$DO_PROBE" = 1 ]; then
        echo "-- probing the running app on the MOSAIC target"
        (cd "$PW_DIR" && BASE_URL="$BASE" SHOTS_DIR="$SHOTS/mosaic" \
           TARGET_SAFE="$MOSAIC_SAFE" TARGET_RUN_ID="$MOSAIC_RUN" node probe.mjs) \
          || echo "warn: mosaic probe failed"
      fi
      if [ "$DO_EDITOR" = 1 ] && [ -n "$MOSAIC_RUN" ]; then
        echo "-- driving the editor on the MOSAIC run (the one that matters, §1)"
        cp "$REPO/scripts/dogfood_editor.mjs" "$PW_DIR/editor.mjs"
        (cd "$PW_DIR" && BASE_URL="$BASE" SHOTS_DIR="$SHOTS/mosaic" \
           TARGET_SAFE="$MOSAIC_SAFE" TARGET_RUN_ID="$MOSAIC_RUN" node editor.mjs) \
          || echo "warn: mosaic editor drive failed"
      fi
    fi
    # …and again on the full-size mosaic, into its own shots dir. This is the
    # only one of the three whose editor preview is decimated, so it is the only
    # pass on which the shrunk-preview advisories and "Check it at full size"
    # are on the screen being photographed at all.
    if [ -n "$BIG_SAFE" ]; then
      BIG_RUN="$(run_id_of "$BIG_SAFE")"
      mkdir -p "$SHOTS/big"
      if [ "$DO_PROBE" = 1 ]; then
        echo "-- probing the running app on the FULL-SIZE target"
        (cd "$PW_DIR" && BASE_URL="$BASE" SHOTS_DIR="$SHOTS/big" \
           TARGET_SAFE="$BIG_SAFE" TARGET_RUN_ID="$BIG_RUN" node probe.mjs) \
          || echo "warn: full-size probe failed"
      fi
      if [ "$DO_EDITOR" = 1 ] && [ -n "$BIG_RUN" ]; then
        echo "-- driving the editor on the FULL-SIZE run (the only decimated preview)"
        cp "$REPO/scripts/dogfood_editor.mjs" "$PW_DIR/editor.mjs"
        (cd "$PW_DIR" && BASE_URL="$BASE" SHOTS_DIR="$SHOTS/big" \
           TARGET_SAFE="$BIG_SAFE" TARGET_RUN_ID="$BIG_RUN" node editor.mjs) \
          || echo "warn: full-size editor drive failed"
      fi
    fi
    echo "-- screenshots: $SHOTS"
  fi
fi

if [ "$DO_SERVE" = 1 ]; then
  echo
  echo "app is up at $BASE — Ctrl-C to stop"
  wait "$SERVER_PID"
fi
