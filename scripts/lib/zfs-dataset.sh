#!/usr/bin/env bash
# Print the ZFS dataset whose mountpoint is exactly <path>, or nothing.
#
#   scripts/lib/zfs-dataset.sh <path>
#
# Used by scripts/deploy.sh to decide whether its backup can be a snapshot.
#
# It reads the WHOLE of `zfs list` before matching. The first version piped
# `zfs list` into an awk that quit at the first match; on a TrueNAS box with
# hundreds of datasets `zfs list` was still writing when awk exited, died of
# SIGPIPE, and under deploy.sh's `set -o pipefail` that killed the deploy —
# silently (zfs's stderr was hidden) and right after it had stopped the app.
# Here a missing or failing `zfs` simply prints nothing, and the caller falls
# back to copying the databases instead.
set -uo pipefail

want="${1%/}"
[ -n "$want" ] || exit 0
command -v zfs >/dev/null 2>&1 || exit 0
listing="$(zfs list -H -o name,mountpoint 2>/dev/null)" || exit 0
awk -F'\t' -v m="$want" '$2 == m && !found { print $1; found = 1 }' <<<"$listing"
exit 0
