#!/usr/bin/env bash
# One git tag per released version (`v0.479.2` → the merge that shipped it), so a
# deploy or a rollback can name an exact build, and a version number can never
# be used twice without the run going red.
#
#   scripts/release-tags.sh [--push] [--backfill] [<before>]
#
# Walks main's first-parent line from HEAD back and tags the first commit that
# carries each version number, stopping at the first one already tagged (or, with
# --backfill, at the root). Every run therefore tags every transition since the
# last tag, not just the tip — so a run that never happened (a cancelled queue, a
# lost delivery) is made up for by the next one, in whatever order the runs land,
# and running it twice is a no-op. --push pushes the tags it made; without it
# they are local (tests).
#
# <before> is main as it was before this push (`github.event.before`), or
# HEAD^1 when that is missing or unknown. Against it, this push is refused —
# exit 1, nothing tagged — when its version:
#   * stayed the same while the push touched anything outside docs/ (two changes
#     shipped under one number — v0.448.0 and v0.453.3 each were, and both PRs
#     of the 2026-09-30 audit's B-F2 bumped to the same 0.492.5), or
#   * went backwards (sort -V).
# A tag that already exists for a version but points at a commit that is not
# on this line is the same refusal.
#
# Run by .github/workflows/release-tags.yml on every push to main.
set -euo pipefail

PUSH=0; BACKFILL=0; BEFORE=""
for a in "$@"; do case "$a" in --push) PUSH=1 ;; --backfill) BACKFILL=1 ;; -h|--help) sed -n '2,26p' "$0"; exit 0 ;; *) BEFORE="$a" ;; esac; done

version_at() { git show "$1:webapp/__init__.py" 2>/dev/null | grep -oP '__version__\s*=\s*"\K[^"]+' || true; }
older() { [ "$1" != "$2" ] && [ "$(printf '%s\n%s\n' "$1" "$2" | sort -V | head -1)" = "$1" ]; }
err() { echo "::error::$*" >&2; }
short() { git rev-parse --short "$1"; }

now="$(version_at HEAD)"
[ -n "$now" ] || { err "no __version__ readable at HEAD"; exit 1; }

# ---- this push against the main it landed on -------------------------------------
if [ "$BACKFILL" = 0 ]; then
  prior="HEAD^1"
  if [ -n "$BEFORE" ] && git cat-file -e "$BEFORE^{commit}" 2>/dev/null; then prior="$BEFORE"; fi
  if git cat-file -e "$prior^{commit}" 2>/dev/null; then
    before="$(version_at "$prior")"
    if [ -n "$before" ]; then
      if [ "$now" = "$before" ]; then
        code="$(git diff --name-only "$prior" HEAD -- . ':!docs/' ':!docs/**')"
        if [ -n "$code" ]; then
          err "this push changed code ($(echo "$code" | head -3 | tr '\n' ' ')…) but __version__ is still $now — a second change shipped under one version number. Bump it on the next change; nothing was tagged."
          exit 1
        fi
        echo "Version unchanged by this push ($now, documentation only)."
      elif older "$now" "$before"; then
        err "__version__ went backwards ($before -> $now); nothing was tagged."
        exit 1
      fi
    fi
  fi
fi

# ---- every version transition on the first-parent line, newest first -------------
# Bounded unless --backfill: a fresh fork without tags must not tag its whole
# history on the first push; the backfill dispatch exists for that.
limit=(); [ "$BACKFILL" = 1 ] || limit=(-n 200)
mapfile -t line < <(git rev-list --first-parent "${limit[@]}" HEAD)
made=(); kept=0
for i in "${!line[@]}"; do
  c="${line[$i]}"
  v="$(version_at "$c")"
  [ -n "$v" ] || continue
  parent="${line[$((i + 1))]:-}"
  if [ -n "$parent" ] && [ "$(version_at "$parent")" = "$v" ]; then continue; fi   # not a transition
  if [ "$parent" = "" ] && [ "$BACKFILL" = 0 ] && [ "$i" -ge 199 ]; then break; fi   # ran out of window, not of history
  tag="v$v"
  if git rev-parse -q --verify "refs/tags/$tag" >/dev/null; then
    at="$(git rev-parse "refs/tags/$tag^{commit}")"
    if [ "$at" = "$c" ]; then
      kept=$((kept + 1))
      [ "$BACKFILL" = 1 ] && continue
      break                       # everything older was tagged by an earlier run
    fi
    if [ "$(version_at "$at")" = "$v" ] && git merge-base --is-ancestor "$at" HEAD; then
      kept=$((kept + 1))          # tagged at another commit of the same stretch (a backfill's pick)
      [ "$BACKFILL" = 1 ] && continue
      break
    fi
    err "$tag already exists at $(short "$at") — that number was used for a different change. Bump the version again on the next change; the existing tag is left where it is."
    exit 1
  fi
  git tag "$tag" "$c"
  made+=("refs/tags/$tag")
  echo "Tagged $tag at $(short "$c")"
done

if [ "${#made[@]}" -gt 0 ] && [ "$PUSH" = 1 ]; then
  git push origin "${made[@]}"
fi
echo "Created ${#made[@]} tags; $kept already existed."
