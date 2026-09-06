import { useQuery } from "@tanstack/react-query";
import { api, type Target } from "../../api/client";
import { FirstLookCard } from "../FirstLookCard";

/**
 * The target a beginner is most likely *waiting on*: subs are in and QC'd, but
 * no finished picture exists yet. Pure/testable.
 *
 * "No picture yet" is `!has_preview` — the same fact the Library tile draws its
 * placeholder from — so a target that already has a stack is never offered a
 * pre-stack peek that its own picture supersedes. Ranked by the library's own
 * `last_activity_utc` (newest first), because after a clear night the target
 * the user wants to see is the one that just gained frames.
 *
 * Ties are broken deterministically — more accepted subs, then name — so the
 * card doesn't swap between two targets on successive refreshes. A target with
 * no `last_activity_utc` at all sorts last rather than being dropped: it is
 * still a real target with kept subs and no picture.
 */
export function pickFirstLookTarget(targets: Target[] | undefined): Target | null {
  const waiting = (targets ?? []).filter(
    (t) => t.n_frames_accepted > 0 && !t.has_preview,
  );
  if (waiting.length === 0) return null;
  const when = (t: Target) => {
    const ms = t.last_activity_utc ? Date.parse(t.last_activity_utc) : NaN;
    return Number.isNaN(ms) ? -Infinity : ms;
  };
  return [...waiting].sort((a, b) =>
    when(b) - when(a)
    || b.n_frames_accepted - a.n_frames_accepted
    || a.name.localeCompare(b.name),
  )[0];
}

/**
 * "Did tonight work?" — answered on the landing page, before any stack runs.
 *
 * The Target hub has shown the sharpest accepted sub since v0.139.0, but a
 * beginner who has just dropped a night in lands on the Dashboard, where a
 * target still being QC'd shows nothing reassuring at all: the Recent-stacks
 * grid only knows about *finished* pictures. This puts the same read-only peek
 * where the glance actually happens, for the one target most likely to be
 * tonight's.
 *
 * Deliberately one target, not a grid — the question is "did it work?", not
 * "show me everything pending", and the Library page already lists them all.
 * Renders nothing at all when every target has a picture (an established
 * library, and every install with nothing new in), so it costs a settled
 * install one cached list request and no screen space.
 */
export function FirstLookStrip() {
  const targets = useQuery({
    queryKey: ["targets"], queryFn: api.listTargets, staleTime: 30_000,
  });
  const pick = pickFirstLookTarget(targets.data);
  if (!pick) return null;
  return (
    <FirstLookCard
      safe={pick.safe_name}
      target={{ name: pick.name, to: `/targets/${pick.safe_name}` }}
    />
  );
}
