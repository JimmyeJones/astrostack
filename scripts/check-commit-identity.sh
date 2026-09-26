#!/usr/bin/env bash
# Refuse commits whose author or committer email is not a no-reply address.
#
# This repository is PUBLIC and every commit's author/committer email is
# published with it (any commit's `.patch` URL shows it). Agent sessions are
# sometimes handed the owner's personal email as context, and between 2026-08-26
# and 2026-09-26 22 agent commits reached `main` carrying it because a session
# ran `git config user.email` with it. History cannot be un-published, so the
# only real guard is refusing the push; CI runs the same check as a backstop.
#
# An allowlist, deliberately: naming the address to block would publish it.
#
# Usage:
#   scripts/check-commit-identity.sh <rev-list args>   e.g.  origin/main..HEAD
#   scripts/check-commit-identity.sh --pre-push        (git pre-push hook stdin)
#   scripts/check-commit-identity.sh --config          (the configured identity)
set -euo pipefail

ALLOWED='^(noreply@anthropic\.com|noreply@github\.com|([0-9]+\+)?[A-Za-z0-9-]+@users\.noreply\.github\.com)$'

# Mask the local part: a CI log is as public as the commit it is complaining about.
mask() { printf '%s' "***@${1#*@}"; }

check_email() { [[ "$1" =~ $ALLOWED ]]; }

check_revs() {
  local bad=0 h ae ce
  while IFS='|' read -r h ae ce; do
    [ -n "$h" ] || continue
    if ! check_email "$ae" || ! check_email "$ce"; then
      echo "  $h  author=$(mask "$ae")  committer=$(mask "$ce")" >&2
      bad=1
    fi
  done < <(git log --format='%h|%ae|%ce' "$@")
  return $bad
}

fail() {
  cat >&2 <<'MSG'

REFUSED: the commit(s) above carry an email that is not a no-reply address.
This repository is public; a pushed commit's email cannot be taken back.
Fix the identity and rewrite ONLY your unpushed commits, e.g.:
  git config user.name  "Claude"
  git config user.email "noreply@anthropic.com"
  git rebase -r <base> --exec 'git commit --amend --no-edit --reset-author'
Never set git user.name/user.email to anything else (AGENTS.md §10).
MSG
  exit 1
}

case "${1:-}" in
  --config)
    email="$(git config user.email || true)"
    if ! check_email "$email"; then
      echo "git user.email is $(mask "${email:-unset@unset}") — not a no-reply address." >&2
      exit 1
    fi
    ;;
  --pre-push)
    zero=0000000000000000000000000000000000000000
    status=0
    while read -r _local_ref local_sha _remote_ref remote_sha; do
      [ "$local_sha" = "$zero" ] && continue          # a branch deletion
      if [ "$remote_sha" = "$zero" ]; then
        check_revs "$local_sha" --not --remotes || status=1   # new branch: what isn't pushed yet
      else
        check_revs "$remote_sha..$local_sha" || status=1
      fi
    done
    [ "$status" = 0 ] || fail
    ;;
  ""|-h|--help)
    sed -n '2,17p' "$0"; exit 2
    ;;
  *)
    check_revs "$@" || fail
    ;;
esac
