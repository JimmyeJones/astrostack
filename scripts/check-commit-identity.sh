#!/usr/bin/env bash
# Refuse commits whose author or committer email is not a no-reply address —
# or whose message mentions one.
#
# This repository is PUBLIC and every commit's author/committer email is
# published with it (any commit's `.patch` URL shows it). Agent sessions are
# sometimes handed the owner's personal email as context, and between 2026-08-26
# and 2026-09-26 22 agent commits reached `main` carrying it because a session
# ran `git config user.email` with it. History cannot be un-published, so the
# only real guard is refusing the push; CI runs the same check as a backstop.
# The message body is published the same way, and a `Co-authored-by:` trailer
# is the obvious place for the same address to land (audit 2026-09-30, B-F6),
# so every email-shaped string in the message is held to the same allowlist.
#
# An allowlist, deliberately: naming the address to block would publish it.
#
# Usage:
#   scripts/check-commit-identity.sh <rev-list args>   e.g.  origin/main..HEAD
#   scripts/check-commit-identity.sh --pre-push        (git pre-push hook stdin)
#   scripts/check-commit-identity.sh --config          (the configured identity)
# Exit 1 on a refused commit; 2 when the revisions cannot be read at all — an
# unreadable range is never a pass (audit 2026-09-30, B-F3).
set -euo pipefail

ALLOWED='^(noreply@anthropic\.com|noreply@github\.com|([0-9]+\+)?[A-Za-z0-9-]+@users\.noreply\.github\.com)$'
# What an address looks like inside prose: a dotted domain ending in letters, so
# `react@18.2.0` and `root@nas` are not addresses…
EMAIL_SHAPE='[[:alnum:]._%+-]+@[[:alnum:].-]+\.[[:alpha:]]{2,}'
# …and a match that ends in a file extension (`logo@2x.png`) is a file name.
FILE_EXT='\.(png|jpe?g|gif|svg|webp|ico|py|pyi|ts|tsx|js|jsx|mjs|cjs|json|ya?ml|toml|md|txt|sh|html?|css|fits?|xisf|tiff?|sqlite|log|csv|zip|gz|tar)$'

# Mask the local part: a CI log is as public as the commit it is complaining about.
mask() { printf '%s' "***@${1#*@}"; }

check_email() { [[ "$1" =~ $ALLOWED ]]; }

# Every email-shaped string in a message that is not an allowed address.
body_offenders() {
  local m
  while IFS= read -r m; do
    [ -n "$m" ] || continue
    [[ "${m,,}" =~ $FILE_EXT ]] && continue
    check_email "$m" || printf '%s\n' "$m"
  done < <(grep -oE "$EMAIL_SHAPE" <<< "$1" || true)
}

# 0 clean, 1 a refused commit, 2 the revisions could not be listed.
check_revs() {
  local revs h ae ce body bad=0 off m
  # Captured, not read through a process substitution: `set -e` never sees the
  # failure of a `< <(git log …)`, so a bad range used to check nothing and pass.
  revs="$(git rev-list "$@")" || { echo "cannot list revisions: $*" >&2; return 2; }
  for h in $revs; do
    ae="$(git log -1 --format=%ae "$h")"
    ce="$(git log -1 --format=%ce "$h")"
    if ! check_email "$ae" || ! check_email "$ce"; then
      echo "  $(git rev-parse --short "$h")  author=$(mask "$ae")  committer=$(mask "$ce")" >&2
      bad=1
    fi
    body="$(git log -1 --format=%B "$h")"
    off="$(body_offenders "$body")"
    if [ -n "$off" ]; then
      while IFS= read -r m; do
        echo "  $(git rev-parse --short "$h")  message mentions $(mask "$m")" >&2
      done <<< "$off"
      bad=1
    fi
  done
  return $bad
}

fail() {
  cat >&2 <<'MSG'

REFUSED: the commit(s) above carry an email that is not a no-reply address —
in the author, the committer, or the message itself (a trailer counts).
This repository is public; a pushed commit's email cannot be taken back.
Fix the identity and rewrite ONLY your unpushed commits, e.g.:
  git config user.name  "Claude"
  git config user.email "noreply@anthropic.com"
  git rebase -r <base> --exec 'git commit --amend --no-edit --reset-author'
and reword any message that mentions the address.
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
      elif git cat-file -e "$remote_sha^{commit}" 2>/dev/null; then
        check_revs "$remote_sha..$local_sha" || status=1
      else
        # The remote's tip is unknown here (a stale fetch): check everything
        # this push could add rather than nothing.
        check_revs "$local_sha" --not --remotes || status=1
      fi
    done
    [ "$status" = 0 ] || fail
    ;;
  ""|-h|--help)
    sed -n '2,23p' "$0"; exit 2
    ;;
  *)
    rc=0
    check_revs "$@" || rc=$?
    [ "$rc" = 0 ] || { [ "$rc" = 2 ] && exit 2; fail; }
    ;;
esac
