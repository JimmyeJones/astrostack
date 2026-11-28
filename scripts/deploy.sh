#!/usr/bin/env bash
# Upgrade the running AstroStack to an exact, known version — safely.
#
#   sudo bash scripts/deploy.sh            # deploy the `stable` branch (or main, if none yet)
#   sudo bash scripts/deploy.sh v0.479.2   # deploy an exact release tag
#   sudo bash scripts/deploy.sh -y ...     # skip the confirmation prompt
#
# (`bash scripts/…` rather than `scripts/…`: some NAS datasets are mounted
# no-exec, which turns the plain form into "Permission denied".)
#
# Why not `git pull && docker compose up --build`: `main` moves several times an
# hour, so a pull deploys whatever it happens to be at that second (it moved
# twice during one deploy on 2026-09-17); and a backup taken while the app is up
# copies SQLite files mid-write. This script pins one commit and BUILDS it while
# the old version keeps running; only then does it STOP the app, snapshot your
# data, start the new version and health-check it. A failed build (one network
# blip during pip/npm/ASTAP download) leaves the old version running and the
# checkout where it was; a failure after the stop starts the old version again
# by itself. If the new version starts but is unhealthy, it prints the rollback
# command -- and `last-good`, what rollback returns to, is the version that was
# actually running before, never the one that just failed (2026-11-26 audit:
# a retry used to record the never-started version, so rollback "restored" it).
#
# Runs from the repository folder on the NAS, as root (Docker and ZFS need it).
# Git itself runs as the user who owns the clone, via sudo -u.
set -euo pipefail

YES=0; REF=""
for a in "$@"; do case "$a" in -y|--yes) YES=1 ;; -h|--help) sed -n '2,15p' "$0"; exit 0 ;; *) REF="$a" ;; esac; done

cd "$(dirname "$0")/.."
die() { echo "ERROR: $*" >&2; exit 1; }

# Nothing may end this script silently -- least of all after it has stopped the
# app (2026-10-04: a failed `zfs list` pipe did exactly that, with stderr hidden).
# And nothing may end it with the app stopped: until the new version has been
# started, any exit puts the checkout back and starts the old container again.
APP_STOPPED=0; NEW_STARTED=0; CHECKED_OUT=0; FINISHED=0; CUR_SHA=""
on_err() {
  local rc=$? line=$1
  echo >&2
  echo "ERROR: the deploy stopped unexpectedly (line $line of scripts/deploy.sh, exit $rc)." >&2
}
on_exit() {
  [ "$FINISHED" = 1 ] && return 0
  [ "$NEW_STARTED" = 1 ] && return 0          # the new version is up; rollback.sh is the way back
  if [ "$CHECKED_OUT" = 1 ] && [ -n "$CUR_SHA" ]; then
    g -c advice.detachedHead=false checkout --quiet --detach "$CUR_SHA" 2>/dev/null \
      && echo "The checkout is back on the version you had." >&2
  fi
  if [ "$APP_STOPPED" = 1 ]; then
    echo "Starting the previous version again…" >&2
    if docker start astrostack >/dev/null 2>&1; then
      echo "Started again: $(docker exec astrostack python -c 'import webapp;print(webapp.__version__)' 2>/dev/null || echo 'version not readable yet'). Your data was not changed." >&2
    else
      echo "Could not start it. Start it again, as it was, with:" >&2
      echo "  sudo docker start astrostack" >&2
    fi
  elif [ "$CHECKED_OUT" = 1 ]; then
    echo "The app was not stopped: the previous version is still running. Nothing was changed." >&2
  fi
}
trap 'on_err $LINENO' ERR
trap on_exit EXIT

[ "$(id -u)" = 0 ] || die "run with sudo: sudo bash scripts/deploy.sh ${REF}"
[ -f .env ] || die "no .env here — run this from your astrostack clone."

OWNER="${SUDO_USER:-$(stat -c %U .)}"
g() { if [ "$OWNER" != root ]; then sudo -u "$OWNER" git "$@"; else git "$@"; fi; }
COMPOSE=(docker compose --env-file .env -f docker/docker-compose.yml)
STATE_DIR="${ASTROSTACK_DEPLOY_STATE:-$(eval echo "~$OWNER")/.astrostack-deploy}"; mkdir -p "$STATE_DIR"; chown "$OWNER" "$STATE_DIR" 2>/dev/null || true

ASTRO_DATA="$(sed -n 's/^ASTRO_DATA=//p' .env | tail -1 | tr -d '"'"'")"
[ -n "$ASTRO_DATA" ] && [ -d "$ASTRO_DATA" ] || die "ASTRO_DATA in .env ('$ASTRO_DATA') is not a folder."
[ -z "$(g status --porcelain --untracked-files=no)" ] || die "this clone has local edits; deploy needs a clean checkout (git status)."

echo "Fetching…"; g fetch --quiet --tags origin
if [ -z "$REF" ]; then
  if g rev-parse -q --verify origin/stable >/dev/null; then REF=origin/stable
  else REF=origin/main; echo "note: no 'stable' branch yet — using origin/main."; fi
fi
TARGET="$(g rev-parse -q --verify "$REF^{commit}")" || die "unknown version '$REF'."
ver_at() { g show "$1:webapp/__init__.py" | grep -oP '__version__\s*=\s*"\K[^"]+'; }
schema_at() { echo "$(g show "$1:seestack/io/project.py" | grep -oP '^SCHEMA_VERSION = \K\d+')/$(g show "$1:seestack/io/library.py" | grep -oP '^LIBRARY_SCHEMA_VERSION = \K\d+')"; }
NEW_VER="$(ver_at "$TARGET")"; NEW_SCHEMA="$(schema_at "$TARGET")"
CUR_SHA="$(g rev-parse HEAD)"; CUR_VER="$(ver_at "$CUR_SHA")"
RUNNING="$(docker exec astrostack python -c 'import webapp;print(webapp.__version__)' 2>/dev/null || echo 'not running')"

echo
echo "  running now : $RUNNING   (checkout: v$CUR_VER, $(g rev-parse --short "$CUR_SHA"))"
echo "  deploying   : v$NEW_VER ($REF → $(g rev-parse --short "$TARGET")), schema project/library $NEW_SCHEMA"
echo "  data folder : $ASTRO_DATA"
echo
if [ "$YES" != 1 ]; then read -r -p "Stop the app, back up, and deploy v$NEW_VER? [y/N] " ok; [ "$ok" = y ] || [ "$ok" = Y ] || die "cancelled."; fi

STAMP="$(date -u +%Y%m%dT%H%MZ)"

# What rollback.sh returns to: the version RUNNING now, found by its release tag
# (every version on main is tagged). Only when that cannot be read does the
# checkout stand in -- and never when it is the version being deployed, which
# is what a retry after a failed deploy would otherwise record.
PREV_SHA=""
if [ "$RUNNING" != "not running" ]; then
  if [ "$RUNNING" != "$NEW_VER" ]; then
    PREV_SHA="$(g rev-parse -q --verify "v$RUNNING^{commit}" 2>/dev/null || true)"
    [ -n "$PREV_SHA" ] || { [ "$RUNNING" = "$CUR_VER" ] && PREV_SHA="$CUR_SHA"; } || true
  fi
elif [ "$CUR_SHA" != "$TARGET" ]; then
  PREV_SHA="$CUR_SHA"
fi
[ "$PREV_SHA" = "$TARGET" ] && PREV_SHA=""

echo "Checking out v$NEW_VER…"; CHECKED_OUT=1; g -c advice.detachedHead=false checkout --quiet --detach "$TARGET"
echo "Building v$NEW_VER while the app keeps running (a few minutes)…"
if ! "${COMPOSE[@]}" build; then
  echo >&2
  echo "ERROR: building v$NEW_VER failed (often a network hiccup while downloading — try again later)." >&2
  exit 1
fi

if [ -n "$PREV_SHA" ]; then
  echo "$PREV_SHA v$(ver_at "$PREV_SHA") $STAMP" > "$STATE_DIR/last-good"
else
  echo "note: keeping the recorded rollback point ($(cut -d' ' -f2 "$STATE_DIR/last-good" 2>/dev/null || echo none)) — v$NEW_VER is not the version to go back to."
fi

echo "Stopping the app…"; "${COMPOSE[@]}" stop
APP_STOPPED=1

# A snapshot when the data folder is its own dataset; otherwise -- or if the
# snapshot fails -- a copy of the databases and settings. Never no backup.
SNAP=""
DATASET="$(bash scripts/lib/zfs-dataset.sh "$ASTRO_DATA")"
if [ -n "$DATASET" ]; then
  if zfs snapshot "$DATASET@astrostack-pre-v$NEW_VER-$STAMP"; then
    SNAP="$DATASET@astrostack-pre-v$NEW_VER-$STAMP"
    echo "Snapshot: $SNAP"
  else
    echo "The ZFS snapshot failed — backing up the databases and settings instead."
  fi
fi
if [ -z "$SNAP" ]; then
  # Not a dataset of its own: back up what an upgrade can change — the databases and settings.
  BK="$STATE_DIR/backup-pre-v$NEW_VER-$STAMP.tar.gz"
  ( cd "$ASTRO_DATA" && find library state \( -name '*.sqlite*' -o -name 'config.json' \) -print0 \
      | tar --null -czf "$BK" --files-from=- )
  N="$(tar tzf "$BK" | wc -l)"; [ "$N" -gt 0 ] || die "backup came out empty — NOT deploying."
  echo "Backup: $BK ($N files)"; SNAP="$BK"
fi
echo "$SNAP" > "$STATE_DIR/last-backup"

echo "Starting v$NEW_VER…"
"${COMPOSE[@]}" up -d --no-build
NEW_STARTED=1

echo -n "Waiting for the app to report healthy"
for _ in $(seq 60); do
  s="$(docker inspect -f '{{.State.Health.Status}}' astrostack 2>/dev/null || echo missing)"
  [ "$s" = healthy ] && break; echo -n "."; sleep 5
done; echo
if [ "$s" != healthy ]; then
  echo "The app did not come up healthy (status: $s). Logs: docker logs --tail 80 astrostack"
  echo "Roll back with:  sudo bash scripts/rollback.sh"
  exit 1
fi
FINISHED=1

# Keep the newest KEEP_BACKUPS backups this script made and delete the older
# ones (owner's decision 2026-11-28: "keep only the newest 3"). Before this,
# every update added one and nothing ever removed any. Only after the new
# version is up and healthy, only names this script itself writes
# (DATASET@astrostack-pre-v<ver>-<stamp> and backup-pre-v<ver>-<stamp>.tar.gz
# in STATE_DIR), never the backup just taken (it is in last-backup), never a
# recursive destroy, and a failure here is a note, never a failed update.
KEEP_BACKUPS="${ASTROSTACK_KEEP_BACKUPS:-3}"
prune_backups() {
  local keep="$KEEP_BACKUPS" current old n
  current="$(cat "$STATE_DIR/last-backup" 2>/dev/null || true)"
  if [ -n "$DATASET" ] && command -v zfs >/dev/null 2>&1; then
    old="$(zfs list -H -t snapshot -o name -s creation -d 1 "$DATASET" 2>/dev/null \
      | grep -E '@astrostack-pre-v[0-9][0-9.]*-[0-9]{8}T[0-9]{4}Z$' \
      | awk -v p="$DATASET@" 'index($0, p) == 1' || true)"
    n="$(printf '%s\n' "$old" | grep -c . || true)"
    if [ "$n" -gt "$keep" ]; then
      printf '%s\n' "$old" | head -n "$((n - keep))" | while read -r snap; do
        [ -n "$snap" ] && [ "$snap" != "$current" ] || continue
        if zfs destroy "$snap"; then echo "Removed an old backup: $snap"
        else echo "note: could not remove the old backup $snap — it stays."; fi
      done
    fi
  fi
  old="$(ls -1tr "$STATE_DIR" 2>/dev/null \
    | grep -E '^backup-pre-v[0-9][0-9.]*-[0-9]{8}T[0-9]{4}Z\.tar\.gz$' || true)"
  n="$(printf '%s\n' "$old" | grep -c . || true)"
  if [ "$n" -gt "$keep" ]; then
    printf '%s\n' "$old" | head -n "$((n - keep))" | while read -r f; do
      [ -n "$f" ] && [ "$STATE_DIR/$f" != "$current" ] || continue
      rm -f -- "$STATE_DIR/$f" && echo "Removed an old backup: $STATE_DIR/$f"
    done
  fi
}
prune_backups || echo "note: tidying old backups did not finish — nothing else is affected."

echo "Done: running $(docker exec astrostack python -c 'import webapp;print(webapp.__version__)'). Backup: $SNAP"
echo "If anything looks wrong:  sudo bash scripts/rollback.sh"
