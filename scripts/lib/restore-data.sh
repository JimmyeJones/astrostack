#!/usr/bin/env bash
# Put back the databases and settings a deploy backed up — and nothing else.
#
#   scripts/lib/restore-data.sh <ASTRO_DATA> <backup>
#
# <backup> is what scripts/deploy.sh recorded in last-backup: a ZFS snapshot
# ("pool/astro@astrostack-pre-v…") of the dataset mounted at ASTRO_DATA, or a
# .tar.gz of the databases and config.json under library/ and state/.
#
# Only files under library/ and state/ are written, and only the ones the backup
# holds (*.sqlite*, config.json). It NEVER runs `zfs rollback`: incoming/ lives in
# the same dataset, so rolling the dataset back deletes every raw sub copied in
# since the snapshot — and incoming/ holds the only copy of those subs (AGENTS.md
# §10). The snapshot is read through its own read-only view,
# <mountpoint>/.zfs/snapshot/<name>/, which works whether or not `snapdir` is
# visible.
#
# Called by scripts/rollback.sh with the app stopped.
set -euo pipefail

die() { echo "ERROR: $*" >&2; exit 1; }
[ "$#" -eq 2 ] || die "usage: $0 <ASTRO_DATA> <backup>"
DATA="$1"; BACKUP="$2"
[ -d "$DATA" ] || die "data folder '$DATA' does not exist."

TMP=""
trap '[ -n "$TMP" ] && rm -rf "$TMP"' EXIT
case "$BACKUP" in
  *@*)
    SRC="$DATA/.zfs/snapshot/${BACKUP#*@}"
    [ -d "$SRC" ] || die "snapshot $BACKUP is not readable at $SRC."
    ;;
  *.tar.gz)
    [ -f "$BACKUP" ] || die "backup file $BACKUP is missing."
    TMP="$(mktemp -d)"
    tar -xzf "$BACKUP" -C "$TMP"
    SRC="$TMP"
    ;;
  *) die "don't know how to restore '$BACKUP'." ;;
esac

FILES=()
for top in library state; do
  [ -d "$SRC/$top" ] || continue
  while IFS= read -r -d '' f; do FILES+=("$f"); done \
    < <(cd "$SRC" && find "$top" -type f \( -name '*.sqlite*' -o -name 'config.json' \) -print0)
done
[ "${#FILES[@]}" -gt 0 ] || die "the backup holds no databases — nothing restored."

# Everything under DATA was written by the app, and this runs as root: a folder the
# app replaced with a link (library/ -> /etc) must stop the restore, not be followed.
# The app is stopped for the whole restore, so checking first is enough.
no_links() {
  local d="$DATA" part
  IFS=/ read -r -a parts <<< "$1"
  for part in "${parts[@]}"; do
    d="$d/$part"
    [ -L "$d" ] && die "$d is a link, not a folder — refusing to restore through it."
  done
  return 0
}
for f in "${FILES[@]}"; do no_links "$f"; done

# An older database next to a newer write-ahead log is how SQLite corrupts one, so
# the current logs go first; the backup's own (taken with the app stopped) come back
# with it below.
for top in library state; do
  [ -d "$DATA/$top" ] && [ ! -L "$DATA/$top" ] || continue
  find "$DATA/$top" -type f \( -name '*.sqlite-wal' -o -name '*.sqlite-shm' -o -name '*.sqlite-journal' \) -delete
done

for f in "${FILES[@]}"; do
  mkdir -p "$DATA/$(dirname "$f")"
  cp -p --remove-destination "$SRC/$f" "$DATA/$f"
done
echo "Restored ${#FILES[@]} files from $BACKUP (library/ and state/ only; incoming/ untouched)."
