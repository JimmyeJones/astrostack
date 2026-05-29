#!/usr/bin/env bash
# Install the ASTAP headless plate solver + a star database into /opt/astap.
#
# Designed for the Docker build, but safe to run standalone. It tries several
# download sources in turn and *verifies the binary actually runs* before
# declaring success — so a broken/expired URL fails the build loudly instead
# of producing a silently solver-less image.
#
# Override behaviour with env vars:
#   ASTAP_DEST        install dir                      (default /opt/astap)
#   ASTAP_DB          star database to fetch: d05|d20|d50|d80  (default d05)
#   ASTAP_SKIP_VERIFY set to 1 to skip the run check (not recommended)
set -euo pipefail

DEST="${ASTAP_DEST:-/opt/astap}"
DB="${ASTAP_DB:-d05}"
SF="https://sourceforge.net/projects/astap-program/files"
SF_DL="https://downloads.sourceforge.net/project/astap-program"

log()  { printf '\033[36m[astap]\033[0m %s\n' "$*"; }
warn() { printf '\033[33m[astap] WARN:\033[0m %s\n' "$*" >&2; }
die()  { printf '\033[31m[astap] ERROR:\033[0m %s\n' "$*" >&2; exit 1; }

mkdir -p "$DEST" /tmp/astap-work
cd /tmp/astap-work

# Download $1 -> $2, retrying with backoff. Returns non-zero on failure.
fetch() {
  local url="$1" out="$2" tries=3 delay=2 i
  for i in $(seq 1 "$tries"); do
    if curl -fsSL --connect-timeout 20 --retry 2 -o "$out" "$url"; then
      [ -s "$out" ] && return 0
      warn "downloaded empty file from $url"
    fi
    warn "fetch failed ($i/$tries): $url"
    sleep "$delay"; delay=$(( delay * 2 ))
  done
  return 1
}

# Pull the `astap` executable out of whatever archive we managed to fetch.
extract_binary() {
  local f="$1"
  case "$f" in
    *.zip)
      unzip -o -j "$f" -d "$DEST" >/dev/null
      # the CLI build ships as `astap_cli`; the GUI build as `astap`
      [ -f "$DEST/astap_cli" ] && mv -f "$DEST/astap_cli" "$DEST/astap"
      ;;
    *.deb)
      rm -rf /tmp/astap-work/deb && mkdir -p /tmp/astap-work/deb
      dpkg-deb -x "$f" /tmp/astap-work/deb
      local bin
      bin="$(find /tmp/astap-work/deb -type f \( -name astap -o -name astap_cli \) | head -n1)"
      [ -n "$bin" ] && cp -f "$bin" "$DEST/astap"
      ;;
    *)
      # assume a raw executable
      cp -f "$f" "$DEST/astap"
      ;;
  esac
  [ -f "$DEST/astap" ] || return 1
  chmod +x "$DEST/astap"
}

# ---------------------------------------------------------------------------
# 1) ASTAP binary — try the headless CLI zip, then mirror, then the full .deb.
# ---------------------------------------------------------------------------
declare -a BIN_SOURCES=(
  "$SF/linux_installer/astap_command-line_version_Linux_amd64.zip/download|astap.zip"
  "$SF_DL/linux_installer/astap_command-line_version_Linux_amd64.zip|astap.zip"
  "$SF/linux_installer/astap_amd64.deb/download|astap.deb"
  "$SF_DL/linux_installer/astap_amd64.deb|astap.deb"
)

got_binary=0
for src in "${BIN_SOURCES[@]}"; do
  url="${src%%|*}"; out="${src##*|}"
  log "trying ASTAP binary: $url"
  if fetch "$url" "$out" && extract_binary "$out"; then
    log "extracted ASTAP -> $DEST/astap"
    got_binary=1
    break
  fi
  warn "source failed, trying next…"
done
[ "$got_binary" = 1 ] || die "could not obtain an ASTAP binary from any source"

# ---------------------------------------------------------------------------
# 2) Star database (default d05 — ample for the Seestar's ~1.3° FOV).
#
# ASTAP databases ship in two band formats: older `.290` (g/h/v/w series) and
# newer `.1476` (d series, e.g. d05). Either works — we collect both. The d05
# `.deb` and `.zip` are both offered on SourceForge; we try `.deb` first, then
# fall back to the `.zip` (which holds the database files directly).
# ---------------------------------------------------------------------------
declare -a DB_SOURCES=(
  "$SF/star_databases/${DB}_star_database.deb/download|db.deb"
  "$SF_DL/star_databases/${DB}_star_database.deb|db.deb"
  "$SF/star_databases/${DB}_star_database.zip/download|db.zip"
  "$SF_DL/star_databases/${DB}_star_database.zip|db.zip"
)

# Copy any ASTAP database files (.290 or .1476) found under $1 into $DEST.
# Returns 0 if at least one was copied.
collect_db_files() {
  local from="$1" n
  find "$from" -type f \( -name '*.290' -o -name '*.1476' \) -exec cp -f {} "$DEST/" \; 2>/dev/null || true
  n=$(find "$DEST" -maxdepth 1 -type f \( -name '*.290' -o -name '*.1476' \) | wc -l)
  [ "$n" -gt 0 ]
}

got_db=0
for src in "${DB_SOURCES[@]}"; do
  url="${src%%|*}"; out="${src##*|}"
  log "trying star database ($DB): $url"
  if ! fetch "$url" "$out"; then warn "download failed, trying next…"; continue; fi

  rm -rf /tmp/astap-work/db && mkdir -p /tmp/astap-work/db
  # Validate + extract by real archive type (guards against an HTML interstitial
  # page being saved as if it were the archive).
  case "$(file -b "$out" 2>/dev/null)" in
    *Debian*|*"Debian binary package"*) dpkg-deb -x "$out" /tmp/astap-work/db 2>/dev/null || true ;;
    *Zip*|*"Zip archive"*)              unzip -o -q "$out" -d /tmp/astap-work/db 2>/dev/null || true ;;
    *) warn "downloaded file is not a .deb/.zip (got: $(file -b "$out" 2>/dev/null)); trying next…"; continue ;;
  esac

  if collect_db_files /tmp/astap-work/db; then
    log "installed $(find "$DEST" -maxdepth 1 -type f \( -name '*.290' -o -name '*.1476' \) | wc -l) star DB file(s) -> $DEST"
    got_db=1
    break
  fi
  warn "archive extracted but contained no .290/.1476 files; contents were:"
  find /tmp/astap-work/db -type f -printf '  %p (%s bytes)\n' 2>/dev/null | head -20 >&2 || true
done

# A solver-less image is useless for this app, so a missing database is fatal.
if [ "$got_db" != 1 ]; then
  die "could not install the '$DB' star database from any source. Plate solving
       requires it. Check the ASTAP_DB build arg (d05|d20|d50|d80) and that
       SourceForge is reachable from the build."
fi

# ---------------------------------------------------------------------------
# 3) Verify the binary actually RUNS (catches missing libs / bad arch / a
#    truncated download that happens to be the right size on disk).
# ---------------------------------------------------------------------------
if [ "${ASTAP_SKIP_VERIFY:-0}" != 1 ]; then
  log "verifying $DEST/astap is runnable…"
  # ASTAP prints its version/usage and may exit non-zero on no-op invocations;
  # we only care that the loader can start it. A missing shared library yields
  # exit 127 or an "error while loading shared libraries" message.
  set +e
  output="$(timeout 30 "$DEST/astap" -h 2>&1)"; rc=$?
  set -e
  [ "$rc" = 124 ] && die "ASTAP binary hung during verification (timed out)."
  if [ "$rc" = 127 ] || printf '%s' "$output" | grep -qi 'error while loading shared libraries\|cannot execute\|no such file'; then
    printf '%s\n' "$output" >&2
    die "ASTAP binary downloaded but will not run (missing libs / bad arch)."
  fi
  ver="$(printf '%s' "$output" | grep -io 'version[^,]*' | head -n1)"
  log "ASTAP runs OK${ver:+ ($ver)}."
fi

rm -rf /tmp/astap-work
log "done. SEESTACK_ASTAP_PATH should point at $DEST/astap"
