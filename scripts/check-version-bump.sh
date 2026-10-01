#!/usr/bin/env bash
# Refuse a change that ships without a version number of its own.
#
#   scripts/check-version-bump.sh <head> <ref> [<ref>...]
#
# `__version__` in webapp/__init__.py is what the release-tags workflow tags,
# what the owner's Settings page compares, and what deploy.sh and rollback.sh
# name — so every change that reaches main must carry a number no other change
# has. Two things broke that before this existed (audit 2026-09-30, B-F2): two
# PRs each bumping 0.492.4 → 0.492.5 (an identical hunk, a clean merge, and the
# second one never tagged), and a PR bumped from a stale checkout of main.
#
# For each <ref> (the PR's recorded base, and — because that base SHA can be
# stale — main as it is *now*), with M = merge-base(<ref>, <head>):
#   * a change that touches anything outside docs/ (M..head) must change the
#     version (head vs M): "code changed, version didn't" is an error;
#   * a changed version must be strictly greater than <ref>'s own — so it never
#     goes backwards and never reuses a number already on main;
#   * a changed version must not already be a tag, unless that tag is on <head>
#     itself (the release-tags run of this very push).
# A change that leaves the version alone is judged only on whether it needed one.
#
# Run by .github/workflows/ci.yml on every PR and every push to main. Exit 1 on
# any refusal (each printed as a ::error:: line), 2 on a revision it cannot read.
set -euo pipefail

[ "$#" -ge 2 ] || { sed -n '2,25p' "$0"; exit 2; }
head="$1"; shift

version_at() {
  # No output when the ref or the file is unreadable — the caller decides.
  git show "$1:webapp/__init__.py" 2>/dev/null | grep -oP '__version__\s*=\s*"\K[^"]+' || true
}
# 0 when $1 sorts strictly before $2 as version numbers.
older() { [ "$1" != "$2" ] && [ "$(printf '%s\n%s\n' "$1" "$2" | sort -V | head -1)" = "$1" ]; }
err() { echo "::error::$*" >&2; }

git rev-parse -q --verify "$head^{commit}" >/dev/null || { echo "cannot read head revision $head" >&2; exit 2; }
head_v="$(version_at "$head")"
[ -n "$head_v" ] || { err "no __version__ readable at $head"; exit 1; }

bad=0
for ref in "$@"; do
  git rev-parse -q --verify "$ref^{commit}" >/dev/null || { echo "cannot read revision $ref" >&2; exit 2; }
  base="$(git merge-base "$ref" "$head")" || { echo "no merge base between $ref and $head" >&2; exit 2; }
  ref_v="$(version_at "$ref")"; base_v="$(version_at "$base")"
  echo "$ref: v${ref_v:-none} (merge base $(git rev-parse --short "$base"), v${base_v:-none}) -> head v$head_v"

  # Everything the change touches that is not documentation.
  code="$(git diff --name-only "$base" "$head" -- . ':!docs/' ':!docs/**')"
  if [ "$head_v" = "$base_v" ]; then
    if [ -n "$code" ]; then
      err "__version__ is still $head_v but this change touches code ($(echo "$code" | head -3 | tr '\n' ' ')…) — bump it in webapp/__init__.py (AGENTS.md §5), from the latest main"
      bad=1
    fi
    continue    # unchanged and docs-only: nothing to judge against $ref
  fi
  if [ -n "$ref_v" ] && ! older "$ref_v" "$head_v"; then
    if [ "$ref_v" = "$head_v" ]; then
      err "__version__ $head_v is already on $ref — another change shipped under it; bump again from the latest main"
    else
      err "__version__ went backwards against $ref ($ref_v -> $head_v)"
    fi
    bad=1
  fi
done

if git rev-parse -q --verify "refs/tags/v$head_v" >/dev/null; then
  at="$(git rev-parse "refs/tags/v$head_v^{commit}")"
  if [ "$at" != "$(git rev-parse "$head^{commit}")" ]; then
    # Only a *new* number is judged here; a change that leaves the version alone
    # naturally carries a tagged one (its base's) and is judged above instead.
    changed=0
    for ref in "$@"; do
      [ "$(version_at "$(git merge-base "$ref" "$head")")" = "$head_v" ] || changed=1
    done
    if [ "$changed" = 1 ]; then
      err "v$head_v is already a released version (tagged at $(git rev-parse --short "$at")) — bump from the latest main"
      bad=1
    fi
  fi
fi

[ "$bad" = 0 ] && echo "version v$head_v is sane" || exit 1
