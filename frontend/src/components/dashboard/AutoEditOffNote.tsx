import { Alert, Button, Group, Text } from "@mantine/core";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";

import { api } from "../../api/client";
import {
  AUTO_EDIT_NUDGE_ACTION, AUTO_EDIT_NUDGE_DONE, AUTO_EDIT_NUDGE_KEY,
  AUTO_EDIT_NUDGE_SIG, AUTO_EDIT_NUDGE_TITLE, autoEditNudge,
} from "../../autoEditNudge";
import { loadDismissedSig, saveDismissedSig } from "../../dismissal";
import { settingsLink } from "../../settingsSections";

/**
 * "It stacked your targets by itself and stopped one step short of the
 * picture" — and the switch that finishes them, on the page the owner lands on.
 *
 * The sibling of `AutoStackOffNote`, for the *other* half of the walk-away
 * promise. `auto_edit_on_autostack` has shipped **on** since v0.395.0 but only
 * reaches a fresh install (§9: an install that has ever run carries an explicit
 * `false` in `state/config.json` that no upgrade may overwrite), so on an
 * established box the chain now stacks every target overnight and leaves each
 * one as a linear master — flat and dark until somebody opens the editor and
 * presses Auto-process. The app knew, every morning, exactly how many pictures
 * it had left unfinished, and said nothing.
 *
 * **Why the notice board.** Same reasoning as `AutoStackOffNote`: the board is
 * the Dashboard's designated place for "something to act on", it is above the
 * fold, it folds surplus notes behind one line, and the owner's standing
 * complaint is that the pages are busy — so this joins the board rather than
 * becoming one more always-on banner (AGENTS.md §1).
 *
 * Self-hiding and separately dismissable: it says nothing unless the newest
 * hands-off scan really did stack targets and leave some of them unfinished,
 * and it disappears for good the moment the switch goes on.
 */
export function AutoEditOffNote() {
  const settings = useQuery({ queryKey: ["settings"], queryFn: api.getSettings });
  // The same cache entry `LastNightCard` and `AutoStackOffNote` read, so on a
  // Dashboard that already shows either of them this costs no extra request.
  const night = useQuery({
    queryKey: ["last-night"], queryFn: api.getLastNight, staleTime: 60_000,
  });
  const qc = useQueryClient();
  const [dismissed, setDismissed] = useState(
    () => loadDismissedSig(AUTO_EDIT_NUDGE_KEY) === AUTO_EDIT_NUDGE_SIG);
  const [turnedOn, setTurnedOn] = useState(false);
  const turnOn = useMutation({
    // A *patch* of one key: `SettingsStore.update` merges into the stored model,
    // so nothing else in the config moves. `auto_stack` is deliberately not
    // sent with it — the note only ever speaks on an install where auto-stack
    // is already doing the stacking, so there is nothing else to switch on.
    mutationFn: () => api.putSettings({ auto_edit_on_autostack: true }),
    onSuccess: () => {
      setTurnedOn(true);
      qc.invalidateQueries({ queryKey: ["settings"] });
    },
  });

  const sentence = autoEditNudge({
    autoEditOnAutostack: settings.data?.auto_edit_on_autostack as boolean | undefined,
    autoStacked: night.data?.auto_stacked,
    autoEdited: night.data?.auto_edited,
  });

  // The confirmation outlives the sentence that earned it: once the switch is on
  // `autoEditNudge` correctly goes quiet, and a note that simply vanished on
  // click would leave the reader unsure anything happened.
  if (turnedOn) {
    return (
      <Alert color="teal" variant="light" title="Auto-editing is on"
        data-testid="auto-edit-on-note">
        <Text size="sm">{AUTO_EDIT_NUDGE_DONE}</Text>
      </Alert>
    );
  }
  if (dismissed || !sentence) return null;

  return (
    <Alert color="violet" variant="light" title={AUTO_EDIT_NUDGE_TITLE}
      withCloseButton closeButtonLabel="Not now"
      onClose={() => {
        saveDismissedSig(AUTO_EDIT_NUDGE_KEY, AUTO_EDIT_NUDGE_SIG);
        setDismissed(true);
      }}
      data-testid="auto-edit-off-note">
      <Text size="sm">{sentence}</Text>
      {/* `wrap` on purpose: a phone at 420 px squeezed an earlier fix button
          until its label read `Use “N` (see docs/PROCESS-NOTES.md, 2026-09-09),
          and this row is a button beside a link. */}
      <Group gap="xs" mt="xs" wrap="wrap">
        <Button size="xs" variant="light" color="violet"
          loading={turnOn.isPending} onClick={() => turnOn.mutate()}>
          {AUTO_EDIT_NUDGE_ACTION}
        </Button>
        <Button component={Link} to={settingsLink("automation")}
          size="xs" variant="subtle" color="violet">
          See what it does
        </Button>
      </Group>
      {turnOn.isError && (
        <Text size="xs" c="red" mt={4}>
          Couldn&rsquo;t change that setting — you can turn auto-editing on
          yourself in Settings &rarr; Automation.
        </Text>
      )}
    </Alert>
  );
}
