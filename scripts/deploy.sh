#!/usr/bin/env bash
# Upgrade the running AstroStack to an exact, known version — safely.
#
#   sudo scripts/deploy.sh            # deploy the `stable` branch (or main, if none yet)
#   sudo scripts/deploy.sh v0.479.2   # deploy an exact release tag
#   sudo scripts/deploy.sh -y ...     # skip the confirmation prompt
#
# Why not `git pull && docker compose up --build`: `main` moves several times an
# hour, so a pull deploys whatever it happens to be at that second (it moved
# twice during one deploy on 2026-09-17); and a backup taken while the app is up
# copies SQLite files mid-write. This script pins one commit, STOPS the app,
# snapshots your data, then builds and health-checks. If anything fails, it
# prints the exact rollback command.
#
# Runs from the repository folder on the NAS, as root (Docker and ZFS need it).
# Git itself runs as the user who owns the clone, via sudo -u.
set -euo pipefail

YES=0; REF=""
for a in "$@"; do case "$a" in -y|--yes) YES=1 ;; -h|--help) sed -n '2,15p' "$0"; exit 0 ;; *) REF="$a" ;; esac; done

cd "$(dirname "$0")/.."
die() { echo "ERROR: $*" >&2; exit 1; }
[ "$(id -u)" = 0 ] || die "run with sudo: sudo scripts/deploy.sh ${REF}"
[ -f .env ] || die "no .env here — run this from your astrostack clone."

OWNER="${SUDO_USER:-$(stat -c %U .)}"
g() { if [ "$OWNER" != root ]; then sudo -u "$OWNER" git "$@"; else git "$@"; fi; }
COMPOSE=(docker compose --env-file .env -f docker/docker-compose.yml)
STATE_DIR="$(eval echo "~$OWNER")/.astrostack-deploy"; mkdir -p "$STATE_DIR"; chown "$OWNER" "$STATE_DIR" 2>/dev/null || true

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
echo "$CUR_SHA v$CUR_VER $STAMP" > "$STATE_DIR/last-good"   # what rollback.sh returns to by default

echo "Stopping the app…"; "${COMPOSE[@]}" stop

SNAP=""
if command -v zfs >/dev/null 2>&1; then
  DATASET="$(zfs list -H -o name,mountpoint 2>/dev/null | awk -v m="$ASTRO_DATA" '$2==m {print $1; exit}')"
  if [ -n "$DATASET" ]; then
    SNAP="$DATASET@astrostack-pre-v$NEW_VER-$STAMP"
    zfs snapshot "$SNAP" && echo "Snapshot: $SNAP"
  fi
fi
if [ -z "$SNAP" ]; then
  # Not a dataset of its own: back up what an upgrade can change — the databases and settings.
  BK="$STATE_DIR/backup-pre-v$NEW_VER-$STAMP.tar.gz"
  ( cd "$ASTRO_DATA" && find library state \( -name '*.sqlite*' -o -name 'config.json' \) -print0 \
      | tar --null -czf "$BK" --files-from=- )
  N="$(tar tzf "$BK" | wc -l)"; [ "$N" -gt 0 ] || die "backup came out empty — NOT deploying. The app is stopped; start it with: ${COMPOSE[*]} start"
  echo "Backup: $BK ($N files)"; SNAP="$BK"
fi
echo "$SNAP" > "$STATE_DIR/last-backup"

echo "Checking out v$NEW_VER…"; g -c advice.detachedHead=false checkout --quiet --detach "$TARGET"
echo "Building and starting (a few minutes)…"
"${COMPOSE[@]}" up -d --build

echo -n "Waiting for the app to report healthy"
for _ in $(seq 60); do
  s="$(docker inspect -f '{{.State.Health.Status}}' astrostack 2>/dev/null || echo missing)"
  [ "$s" = healthy ] && break; echo -n "."; sleep 5
done; echo
if [ "$s" != healthy ]; then
  echo "The app did not come up healthy (status: $s). Logs: docker logs --tail 80 astrostack"
  echo "Roll back with:  sudo scripts/rollback.sh"
  exit 1
fi
echo "Done: running $(docker exec astrostack python -c 'import webapp;print(webapp.__version__)'). Backup: $SNAP"
echo "If anything looks wrong:  sudo scripts/rollback.sh"
