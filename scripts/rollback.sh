#!/usr/bin/env bash
# Go back to the version that was running before the last scripts/deploy.sh.
#
#   sudo scripts/rollback.sh                      # back to what deploy.sh recorded
#   sudo scripts/rollback.sh v0.455.7             # back to an exact release tag
#   sudo scripts/rollback.sh --restore-data       # …and put the data back as it was
#   sudo scripts/rollback.sh --yes …              # no prompts (Settings → App updates)
#
# Code-only rollback is safe whenever the older version understands the newer
# database format. When it does not (older code refuses a newer schema — see
# seestack/io/project.py SCHEMA_VERSION, seestack/io/library.py
# LIBRARY_SCHEMA_VERSION), this script says so and requires --restore-data,
# which restores the backup deploy.sh took. Restoring LOSES anything the app
# wrote since that backup (new stacks, edits, imported frames' records); your
# raw subs in incoming/ are never touched either way — the restore is
# scripts/lib/restore-data.sh, which copies back only library/ and state/
# databases and never runs `zfs rollback` (that would roll incoming/ back too).
set -euo pipefail

RESTORE=0; YES=0; REF=""
for a in "$@"; do case "$a" in --restore-data) RESTORE=1 ;; -y|--yes) YES=1 ;; -h|--help) sed -n '2,17p' "$0"; exit 0 ;; *) REF="$a" ;; esac; done

cd "$(dirname "$0")/.."
die() { echo "ERROR: $*" >&2; exit 1; }
[ "$(id -u)" = 0 ] || die "run with sudo."
OWNER="${SUDO_USER:-$(stat -c %U .)}"
g() { if [ "$OWNER" != root ]; then sudo -u "$OWNER" git "$@"; else git "$@"; fi; }
COMPOSE=(docker compose --env-file .env -f docker/docker-compose.yml)
STATE_DIR="$(eval echo "~$OWNER")/.astrostack-deploy"
ASTRO_DATA="$(sed -n 's/^ASTRO_DATA=//p' .env | tail -1 | tr -d '"'"'")"

if [ -z "$REF" ]; then
  [ -f "$STATE_DIR/last-good" ] || die "no record of a previous deploy — name a version, e.g. sudo scripts/rollback.sh v0.455.7"
  REF="$(cut -d' ' -f1 "$STATE_DIR/last-good")"
fi
g fetch --quiet --tags origin || true
TARGET="$(g rev-parse -q --verify "$REF^{commit}")" || die "unknown version '$REF'."
schema() { g show "$1:seestack/io/project.py" | grep -oP '^SCHEMA_VERSION = \K\d+'; }
lschema() { g show "$1:seestack/io/library.py" | grep -oP '^LIBRARY_SCHEMA_VERSION = \K\d+'; }
ver_at() { g show "$1:webapp/__init__.py" | grep -oP '__version__\s*=\s*"\K[^"]+'; }
NOW=HEAD
echo "  now      : v$(ver_at $NOW)  schema project/library $(schema $NOW)/$(lschema $NOW)"
echo "  going to : v$(ver_at "$TARGET")  schema project/library $(schema "$TARGET")/$(lschema "$TARGET")"
NEEDS_DATA=0
{ [ "$(schema "$TARGET")" -lt "$(schema $NOW)" ] || [ "$(lschema "$TARGET")" -lt "$(lschema $NOW)" ]; } && NEEDS_DATA=1

BACKUP="$(cat "$STATE_DIR/last-backup" 2>/dev/null || true)"
if [ "$NEEDS_DATA" = 1 ] && [ "$RESTORE" != 1 ]; then
  die "v$(ver_at "$TARGET") cannot open the newer database format. Re-run with --restore-data to also restore the backup ($BACKUP), which loses changes made since it."
fi
if [ "$RESTORE" = 1 ]; then
  [ -n "$BACKUP" ] || die "no backup recorded by deploy.sh."
  if [ "$YES" != 1 ]; then
    read -r -p "Restore $BACKUP? Anything the app wrote since then is lost. Type RESTORE: " ok; [ "$ok" = RESTORE ] || die "cancelled."
  fi
fi

"${COMPOSE[@]}" stop
if [ "$RESTORE" = 1 ]; then
  scripts/lib/restore-data.sh "$ASTRO_DATA" "$BACKUP" || die "restore failed — the app is stopped. Start it again with: ${COMPOSE[*]} up -d"
fi
g -c advice.detachedHead=false checkout --quiet --detach "$TARGET"
"${COMPOSE[@]}" up -d --build
for _ in $(seq 60); do s="$(docker inspect -f '{{.State.Health.Status}}' astrostack 2>/dev/null || echo missing)"; [ "$s" = healthy ] && break; sleep 5; done
[ "$s" = healthy ] || die "not healthy after rollback (status: $s) — docker logs --tail 80 astrostack"
echo "Rolled back: running $(docker exec astrostack python -c 'import webapp;print(webapp.__version__)')"
