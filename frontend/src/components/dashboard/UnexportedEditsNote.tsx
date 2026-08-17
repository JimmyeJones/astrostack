import { Alert, Anchor, Button, Group, List, Modal, Text } from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../../api/client";
import { loadDismissedSig, saveDismissedSig } from "../../dismissal";

const DISMISS_KEY = "astrostack.dashboard.unexportedEditsDismissed";

// How many pictures the note names outright before it stops listing and points at
// the Gallery instead. Three fits on one line on a phone, which is where the owner
// reads this.
const NAMED = 3;

/**
 * "You have edits you saved but never exported" — the one surface that finds you
 * rather than waiting to be found.
 *
 * Three places already admit, per picture, that a thumbnail isn't the user's
 * version (the Target hero, History, the Gallery) — but every one of them needs
 * you to be *looking at that picture already*. Someone who dialled in a look,
 * pressed **Save**, closed the editor and moved on has no reason to go back, so
 * their work stays invisible indefinitely and the app keeps showing a picture they
 * didn't make. This note is the library-wide version of the same honesty, on the
 * page they land on.
 *
 * It self-hides at zero (the overwhelmingly common case), names up to three
 * pictures with a direct link into the editor for each, and is dismissable by
 * *signature* — so saying "not now" quiets exactly these edits, and a new one
 * later still speaks up. Deliberately advisory, never a warning: nothing is
 * broken, there is just work of theirs the app isn't showing.
 *
 * **"Finish them all" (two or more only).** Naming them is right for one or two;
 * someone who edits across several nights and never exports accumulates a dozen,
 * and clicking through a dozen editors to press Export a dozen times is the manual
 * chain the app exists to remove. The saved recipe *is* the instruction, so the
 * server can do it unattended. Three deliberate constraints, because this one
 * writes files:
 *   * it is the **secondary** action, never the note's default — the per-picture
 *     buttons keep the prominent slot, and this sits after them as a subtle link;
 *   * it asks first, and the confirmation says how many pictures, that each is a
 *     **new** version written beside the original with nothing replaced, and where
 *     the disk cost lands;
 *   * dismissing the note is "not now", never "do it" — closing the Alert has no
 *     connection to this button at all.
 */
export function UnexportedEditsNote() {
  const qc = useQueryClient();
  const { data } = useQuery({
    queryKey: ["unexported-edits"],
    queryFn: api.getUnexportedEdits,
    // Long on purpose: this is a cross-target read, and the Dashboard is a polling
    // page. Once per visit is plenty for a note about work the user did earlier.
    staleTime: 300_000,
  });
  const [dismissedSig, setDismissedSig] = useState(() => loadDismissedSig(DISMISS_KEY));
  const [confirming, setConfirming] = useState(false);

  const finishAll = useMutation({
    mutationFn: api.exportUnexportedEdits,
    onSuccess: ({ count: n }) => {
      setConfirming(false);
      notifications.show({
        message: `Finishing ${n} ${n === 1 ? "picture" : "pictures"} — follow it on the `
          + "Jobs page, where you can also stop it.",
        color: "violet",
      });
      // The job re-counts as it goes, so re-ask once it is queued and let the
      // Jobs badge carry the rest; the note will empty itself on the next visit.
      qc.invalidateQueries({ queryKey: ["jobs"] });
      qc.invalidateQueries({ queryKey: ["unexported-edits"] });
    },
    onError: (e: Error) => notifications.show({ message: e.message, color: "red" }),
  });

  const count = data?.count ?? 0;
  if (count === 0) return null;

  const items = data?.items ?? [];
  const sig = `${count}|${items.map((i) => `${i.safe}:${i.run_id}`).join(",")}`;
  if (sig === dismissedSig) return null;

  const named = items.slice(0, NAMED);

  return (
    <>
      <Alert
        color="violet" variant="light" data-testid="unexported-edits-note"
        withCloseButton closeButtonLabel="Not now"
        onClose={() => { setDismissedSig(sig); saveDismissedSig(DISMISS_KEY, sig); }}
        title={count === 1
          ? "You have an edit you never finished"
          : `You have ${count} edits you never finished`}
      >
        <Text size="sm">
          {count === 1
            ? "You saved an edit in the editor but never exported it, so AstroStack is "
              + "still showing the un-edited version of that picture. Exporting it makes "
              + "your version the one you see everywhere — and the one you share."
            : `You saved edits for ${count} pictures but never exported them, so AstroStack `
              + "is still showing the un-edited versions. Exporting an edit makes your "
              + "version the one you see everywhere — and the one you share."}
        </Text>
        <Group gap="sm" mt="xs" wrap="wrap">
          {named.map((it) => (
            <Button
              key={`${it.safe}-${it.run_id}`}
              component={Link} to={`/targets/${it.safe}/edit/${it.run_id}`}
              size="compact-xs" variant="light" color="violet"
            >
              {count === 1 ? `Finish ${it.target_name}` : it.target_name}
            </Button>
          ))}
          {count > named.length ? (
            <Anchor component={Link} to="/gallery" size="xs">
              {`See all ${count} in the Gallery →`}
            </Anchor>
          ) : null}
        </Group>
        {count > 1 ? (
          <Anchor
            component="button" type="button" size="xs" mt="xs" display="block"
            data-testid="finish-all-edits"
            onClick={() => setConfirming(true)}
          >
            {`Or finish all ${count} for me →`}
          </Anchor>
        ) : null}
      </Alert>

      <Modal
        opened={confirming} onClose={() => setConfirming(false)}
        title={`Finish all ${count} edits?`} centered
      >
        <Text size="sm">
          AstroStack will re-render each picture with the edit you saved for it and
          add it to that target's history. It runs as one job, so you can watch it
          — or stop it — on the Jobs page.
        </Text>
        <List size="sm" mt="sm" spacing={4}>
          <List.Item>
            <b>{count} pictures</b>, one after another.
          </List.Item>
          <List.Item>
            Nothing is replaced or deleted — each finished picture is written
            <i> alongside</i> the original, which stays exactly as it is.
          </List.Item>
          <List.Item>
            That means {count} new sets of files, each about the size of the stack
            it came from. <Anchor component={Link} to="/storage">Storage</Anchor> shows
            what you have room for.
          </List.Item>
        </List>
        <Group justify="flex-end" mt="md">
          <Button variant="default" onClick={() => setConfirming(false)}>
            Not now
          </Button>
          <Button
            color="violet" loading={finishAll.isPending}
            data-testid="finish-all-confirm"
            onClick={() => finishAll.mutate()}
          >
            {`Finish all ${count}`}
          </Button>
        </Group>
      </Modal>
    </>
  );
}
