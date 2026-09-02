import { Alert, Button, Group, Text } from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { IconAlertTriangle, IconArrowBackUp, IconFileOff } from "@tabler/icons-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "../api/client";

/**
 * "Last night's stack was held back — some of your subs aren't on disk."
 *
 * The walk-away readability preflight (v0.270.1) refuses to publish a picture
 * made thin by subs it couldn't read, and explains itself in full — but only on
 * the **Jobs** page. A beginner whose picture quietly stops updating goes to the
 * **Target** page, where their picture lives, sees a stale image and no reason
 * for it, and has no cause to go hunting through job history. So the one place
 * the hold is explained is the one place they won't look.
 *
 * This is that same fact, in the same words, on the page they actually stare at
 * — and, since v0.327.4, **the one thing to do about it**. The hold is right
 * while the files are coming back; it is a dead end when they never do. If the
 * owner deleted a session from `incoming/` (their folder, their right) the rows
 * stay, `unreadable` never drops, and the target is held until brand-new subs
 * outnumber the best run it ever made. "Those subs are gone" sets exactly those
 * rows aside — database-only, nothing on disk touched — and the next scan puts
 * any of them straight back if its file reappears.
 *
 * Read-only until that button is pressed, and self-clearing: the endpoint reads
 * only the *newest* finished scan, so the moment a scan stacks the target the
 * note disappears on its own. Best-effort: an older backend (404) or a failed
 * fetch renders nothing, exactly as before this existed.
 */
export function AutoStackHoldNote({ safe }: { safe: string }) {
  const qc = useQueryClient();
  const [undoIds, setUndoIds] = useState<number[] | null>(null);
  const hold = useQuery({
    queryKey: ["autostack-hold", safe],
    queryFn: () => api.autoStackHold(safe).catch(() => null),
    enabled: !!safe,
    staleTime: 30_000,
    retry: false,
  });
  const refresh = () => {
    qc.invalidateQueries({ queryKey: ["frames", safe] });
    qc.invalidateQueries({ queryKey: ["target", safe] });
    qc.invalidateQueries({ queryKey: ["reject-summary", safe] });
  };
  const setAside = useMutation({
    mutationFn: () => api.setMissingAside(safe),
    onSuccess: ({ changed, changed_ids }) => {
      setUndoIds(changed ? changed_ids : null);
      notifications.show({
        message: changed
          ? `${changed} missing sub${changed === 1 ? "" : "s"} set aside — the next stack will use the rest.`
          : "Nothing to set aside: every sub is readable again.",
        color: changed ? "yellow" : "green",
      });
      refresh();
    },
    onError: (e: Error) => notifications.show({ message: e.message, color: "red" }),
  });
  const undo = useMutation({
    mutationFn: () => api.bulkFrames(safe, { action: "accept", ids: undoIds ?? [] }),
    onSuccess: () => {
      setUndoIds(null);
      notifications.show({ message: "Put back.", color: "green" });
      refresh();
    },
    onError: (e: Error) => notifications.show({ message: e.message, color: "red" }),
  });
  const h = hold.data;
  if (!h || h.unreadable <= 0) return null;
  return (
    <Alert color="yellow" variant="light" icon={<IconAlertTriangle size={18} />}
      title="Your latest stack was held back — some subs aren't on disk right now"
      data-testid="autostack-hold-note">
      <Text size="sm">
        {`${h.unreadable} of ${h.offered} subs couldn't be read on the last scan `}
        {`(${h.readable} still readable). Stacking without them would have made a `}
        {"thinner, noisier picture than the one you already have, so it was left "}
        {"alone. This usually means a drive or network share went off-line, or a "}
        {"folder was moved. Put it back and the next scan will stack the full set "}
        {"automatically — nothing has been lost."}
      </Text>
      <Text size="sm" mt="xs">
        {"Deleted those subs on purpose? Then they're never coming back, and this "}
        {"target would stay held for good. Set them aside and stacking carries on "}
        {"with the "}{h.readable}{" you still have. It only changes AstroStack's own "}
        {"records — your files are never touched — and if the missing ones ever "}
        {"turn up again they're put back automatically."}
      </Text>
      <Group gap="xs" mt="xs">
        <Button size="xs" variant="light" color="yellow"
          leftSection={<IconFileOff size={14} />}
          loading={setAside.isPending}
          onClick={() => setAside.mutate()}
          data-testid="set-missing-aside">
          Those subs are gone — carry on without them
        </Button>
        {undoIds?.length ? (
          <Button size="xs" variant="subtle" color="gray"
            leftSection={<IconArrowBackUp size={14} />}
            loading={undo.isPending}
            onClick={() => undo.mutate()}
            data-testid="undo-missing-aside">
            Undo
          </Button>
        ) : null}
      </Group>
    </Alert>
  );
}
