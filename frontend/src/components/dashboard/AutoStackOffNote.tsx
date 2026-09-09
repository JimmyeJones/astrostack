import { Alert, Button, Group, Text } from "@mantine/core";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";

import { api } from "../../api/client";
import {
  AUTO_STACK_NUDGE_ACTION, AUTO_STACK_NUDGE_DONE, AUTO_STACK_NUDGE_KEY,
  AUTO_STACK_NUDGE_SIG, AUTO_STACK_NUDGE_TITLE, autoStackNudge,
} from "../../autoStackNudge";
import { loadDismissedSig, saveDismissedSig } from "../../dismissal";
import { settingsLink } from "../../settingsSections";

/**
 * "You captured a night and nothing was stacked" — and the one switch that
 * changes it, on the page the owner lands on.
 *
 * **Why this exists at all.** `Settings.auto_stack` has shipped **on** since
 * v0.391.0, but only reaches a *fresh* install: `SettingsStore` re-saves the
 * whole model every boot, so any box that has ever run carries an explicit
 * `"auto_stack": false` in `state/config.json` that no upgrade may overwrite —
 * a stored value cannot be told apart from a value its owner chose, and
 * flipping one they chose is exactly the breach AGENTS.md §9 exists to prevent.
 * So on every existing install the entire "drop your subs in and come back to a
 * picture" chain sits behind one switch on a Settings tab, and until now nothing
 * in the app had ever mentioned it. The backlog has carried it for days as a
 * thing only the owner can do; what nobody had done is *tell* him.
 *
 * **Why the notice board and not the "Last night" card.** The first draft put it
 * inside `LastNightCard`, which is where the news of the night is — and a
 * browser at 420 px showed it rendered *hidden*, because that card lives in the
 * Dashboard's `InsightTabs` "Recent" panel, which is `display: none` until the
 * tab is clicked. An offer nobody scrolls to is not an offer. The board is the
 * page's designated place for "something to act on", it is above the fold, it
 * folds surplus notes behind one line, and its own comment says a later
 * Dashboard warning should join it rather than become another banner.
 *
 * Self-hiding and separately dismissable, like every other note here: it says
 * nothing at all unless the app really did capture a night and stack nothing of
 * it, and it disappears for good the moment the switch goes on.
 */
export function AutoStackOffNote() {
  const settings = useQuery({ queryKey: ["settings"], queryFn: api.getSettings });
  // The same cache entry `LastNightCard` reads, so on a Dashboard that already
  // shows that card this costs no extra request.
  const night = useQuery({
    queryKey: ["last-night"], queryFn: api.getLastNight, staleTime: 60_000,
  });
  const qc = useQueryClient();
  const [dismissed, setDismissed] = useState(
    () => loadDismissedSig(AUTO_STACK_NUDGE_KEY) === AUTO_STACK_NUDGE_SIG);
  const [turnedOn, setTurnedOn] = useState(false);
  const turnOn = useMutation({
    // A *patch* of one key: `SettingsStore.update` merges into the stored model,
    // so nothing else in the config moves.
    mutationFn: () => api.putSettings({ auto_stack: true }),
    onSuccess: () => {
      setTurnedOn(true);
      qc.invalidateQueries({ queryKey: ["settings"] });
    },
  });

  const r = night.data;
  const sentence = autoStackNudge({
    autoStack: settings.data?.auto_stack as boolean | undefined,
    minFrames: settings.data?.auto_stack_min_frames as number | undefined,
    targetsKept: (r?.targets ?? []).map((t) => t.n_kept),
    nNewPictures: (r?.new_pictures ?? []).length,
  });

  // The confirmation outlives the sentence that earned it: once the switch is on
  // `autoStackNudge` correctly goes quiet, and a note that simply vanished on
  // click would leave the reader unsure anything happened.
  if (turnedOn) {
    return (
      <Alert color="teal" variant="light" title="Auto-stack is on"
        data-testid="auto-stack-on-note">
        <Text size="sm">{AUTO_STACK_NUDGE_DONE}</Text>
      </Alert>
    );
  }
  if (dismissed || !sentence) return null;

  return (
    <Alert color="violet" variant="light" title={AUTO_STACK_NUDGE_TITLE}
      withCloseButton closeButtonLabel="Not now"
      onClose={() => {
        saveDismissedSig(AUTO_STACK_NUDGE_KEY, AUTO_STACK_NUDGE_SIG);
        setDismissed(true);
      }}
      data-testid="auto-stack-off-note">
      <Text size="sm">{sentence}</Text>
      {/* `wrap` on purpose: a phone at 420 px squeezed an earlier fix button
          until its label read `Use “N` (see docs/PROCESS-NOTES.md, 2026-09-09),
          and this row is a button beside a link. */}
      <Group gap="xs" mt="xs" wrap="wrap">
        <Button size="xs" variant="light" color="violet"
          loading={turnOn.isPending} onClick={() => turnOn.mutate()}>
          {AUTO_STACK_NUDGE_ACTION}
        </Button>
        <Button component={Link} to={settingsLink("automation")}
          size="xs" variant="subtle" color="violet">
          See what it does
        </Button>
      </Group>
      {turnOn.isError && (
        <Text size="xs" c="red" mt={4}>
          Couldn&rsquo;t change that setting — you can turn Auto-stack on
          yourself in Settings → Automation.
        </Text>
      )}
    </Alert>
  );
}
