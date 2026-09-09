import { Alert, Anchor, Button, Group, Text } from "@mantine/core";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../../api/client";
import { loadDismissedSig, saveDismissedSig } from "../../dismissal";

const DISMISS_KEY = "astrostack.dashboard.newSubsWaitingDismissed";

// How many targets the note names outright before it stops listing and points at
// the Library instead. Three fits on one line on a phone, which is where the
// owner reads this — the same bound the un-exported-edits note uses.
const NAMED = 3;

/**
 * "You've shot more of these since their pictures were made" — the library-wide
 * half of a nudge that has only ever existed per target.
 *
 * The Target page has said *"N new subs since your last stack — restack?"* since
 * v0.90.0, and it is the right sentence for someone already looking at the
 * picture that has fallen behind. But with auto-stack off (the owner's setting)
 * and a target per object across many nights, the question after a night's
 * capture is *which* target to open — and the only surface that knew was the one
 * you had to open to find out. So a picture could sit months behind its own data
 * with nothing anywhere saying so.
 *
 * It self-hides at zero — a library that is fully stacked, and every library on
 * the very first render — names up to three targets with a direct link into each
 * one's Stack form, and is dismissable by *signature*, so "not now" quiets
 * exactly this backlog and the next night's subs still speak up.
 *
 * **Advisory, and it never acts.** Nothing is broken and nothing is lost; there
 * is just light of theirs the picture doesn't have yet. Re-stacking is hours of
 * CPU on a NAS, so there is deliberately no "do them all" button here — each
 * link lands on the Stack form, where the frame count, the time estimate and the
 * settings are, and the existing picture stays in that target's history either
 * way.
 */
export function NewSubsWaitingNote() {
  const { data } = useQuery({
    queryKey: ["new-subs-waiting"],
    queryFn: api.getNewSubsWaiting,
    // Long on purpose: this is a cross-target read and the Dashboard is a
    // polling page. Once per visit is plenty for a note about subs already on
    // disk.
    staleTime: 300_000,
  });
  const [dismissedSig, setDismissedSig] = useState(() => loadDismissedSig(DISMISS_KEY));

  const count = data?.count ?? 0;
  if (count === 0) return null;

  const items = data?.items ?? [];
  const total = data?.total_new_subs ?? 0;
  // The signature carries the counts, not just the targets: shooting more of a
  // target you already dismissed is new news, and should speak again.
  const sig = `${count}|${items.map((i) => `${i.safe}:${i.n_new_subs}`).join(",")}`;
  if (sig === dismissedSig) return null;

  const named = items.slice(0, NAMED);
  // `total` is never below `count` (each target listed has at least one waiting
  // sub), so "one sub" implies "one target" and the three shapes below are the
  // only ones reachable.
  const subWord = total === 1 ? "sub" : "subs";
  const title = total === 1
    ? "1 sub you've shot isn't in the picture yet"
    : count === 1
      ? `${total} subs you've shot aren't in the picture yet`
      : `${total} subs you've shot aren't in your pictures yet`;

  return (
    <Alert
      color="violet" variant="light" data-testid="new-subs-waiting-note"
      withCloseButton closeButtonLabel="Not now"
      onClose={() => { setDismissedSig(sig); saveDismissedSig(DISMISS_KEY, sig); }}
      title={title}
    >
      <Text size="sm">
        {count === 1
          ? `You've shot ${total} more ${subWord} of this target since AstroStack last `
            + "stacked it, so the picture you're seeing doesn't include your newest "
            + `light. Stacking again folds ${total === 1 ? "it" : "them"} in — the `
            + "picture you have now stays in that target's history."
          : `You've shot ${total} more ${subWord} across ${count} targets since AstroStack `
            + "last stacked them, so the pictures you're seeing don't include your "
            + "newest light. Stacking one again folds its new subs in — the picture you "
            + "have now stays in that target's history."}
      </Text>
      <Group gap="sm" mt="xs" wrap="wrap">
        {named.map((it) => (
          <Button
            key={it.safe}
            component={Link} to={`/targets/${it.safe}/stack`}
            size="compact-xs" variant="light" color="violet"
          >
            {`${it.target_name} · +${it.n_new_subs}`}
          </Button>
        ))}
        {/* Deliberately *not* "see all N in the Library": the Library doesn't
            single these out, and a link that promises a list nobody wrote is the
            kind of small untruth this app keeps having to unpick. It says where
            the other targets are, which is true. */}
        {count > named.length ? (
          <Anchor component={Link} to="/library" size="xs">
            {`${count - named.length} more in your Library →`}
          </Anchor>
        ) : null}
      </Group>
    </Alert>
  );
}
