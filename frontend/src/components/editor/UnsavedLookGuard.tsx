import { Button, Group, Modal, Stack, Text } from "@mantine/core";
import { useEffect, useState } from "react";
import { useBlocker } from "react-router-dom";

/**
 * "You haven't kept this look yet" — the editor's unsaved-changes guard.
 *
 * An edit lives only in the browser until **Save**: nothing in the editor writes
 * a recipe on its own, so walking away with the nav bar, the in-page "History"
 * button or the browser's back button silently drops the whole look and leaves
 * every other screen showing the plain stack. There was no guard of any kind
 * before this component (`grep beforeunload|useBlocker` in `frontend/src` found
 * nothing), which is why a half-finished edit could evaporate on a mis-click.
 *
 * **What counts as unsaved is deliberately narrow.** The caller passes `dirty`,
 * and the baseline it measures against is *the look the editor put on screen*,
 * not the empty recipe — so the Auto-process the app seeds for you on first open
 * (v0.390.0) does **not** by itself make the picture dirty. Two reasons: nobody
 * asked for that look, and it is reproducible for free (the next open seeds it
 * again). A guard that stopped a beginner leaving a picture they never touched
 * would be worse than no guard at all. The moment they change *anything* — a
 * slider, an added op, the Auto button pressed by hand — it is their work and
 * the guard applies.
 *
 * Two exits, because the browser gives us two:
 *  - an in-app navigation is blocked by `useBlocker` (a data router is mounted in
 *    `main.tsx`) and answered with the modal below, which offers Save, leave, or
 *    stay — "leave it" kept as an easy, unpunished answer;
 *  - a tab close or reload can only raise the browser's own generic dialog, via
 *    `beforeunload`.
 *
 * Search-param-only navigations are **not** blocked: the editor rewrites its own
 * query string (`setSearchParams`, e.g. dropping the `?recentre=1` deep link),
 * and blocking that would pop a modal at someone who never navigated.
 */
export function UnsavedLookGuard({ dirty, saving, onSave }: {
  /** Does the live recipe differ from the last look the user committed? */
  dirty: boolean;
  /** Is a Save already in flight (from anywhere)? Disables the modal's buttons. */
  saving?: boolean;
  /** Save the look. Resolves on success, rejects on failure (we then stay put). */
  onSave: () => Promise<unknown>;
}) {
  const blocker = useBlocker(({ currentLocation, nextLocation }) =>
    dirty && currentLocation.pathname !== nextLocation.pathname);
  const [savingHere, setSavingHere] = useState(false);

  // The tab-close half. Registered only while dirty so an untouched editor never
  // makes the browser ask; the modern contract is preventDefault(), with
  // returnValue kept for the browsers that still want it.
  useEffect(() => {
    if (!dirty) return;
    const onBeforeUnload = (e: BeforeUnloadEvent) => {
      e.preventDefault();
      e.returnValue = "";
    };
    window.addEventListener("beforeunload", onBeforeUnload);
    return () => window.removeEventListener("beforeunload", onBeforeUnload);
  }, [dirty]);

  const blocked = blocker.state === "blocked";
  const busy = savingHere || saving === true;

  const saveAndLeave = async () => {
    setSavingHere(true);
    try {
      await onSave();
    } catch {
      // The editor already shows the failure; keep the user (and their look)
      // here rather than navigating away from work that did not persist.
      setSavingHere(false);
      return;
    }
    setSavingHere(false);
    blocker.proceed?.();
  };

  return (
    <Modal opened={blocked} onClose={() => blocker.reset?.()}
      title="Keep this look?" centered>
      <Stack gap="sm">
        <Text size="sm">
          Your changes to this picture are only on this screen — they aren't kept
          with it until you save. Saving means you can come back and carry on
          later.
        </Text>
        <Group justify="flex-end">
          <Button variant="subtle" disabled={busy}
            onClick={() => blocker.reset?.()}>Stay here</Button>
          <Button variant="default" disabled={busy}
            onClick={() => blocker.proceed?.()}>Leave without saving</Button>
          <Button loading={busy} onClick={saveAndLeave}>Save and leave</Button>
        </Group>
      </Stack>
    </Modal>
  );
}
