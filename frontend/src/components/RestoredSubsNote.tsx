import { Alert, Button, Group, Text } from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { IconArrowBackUp, IconStack2 } from "@tabler/icons-react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import type { RestoredSubs } from "../api/client";
import { api } from "../api/client";
import { formatStampDate } from "../format";

/**
 * "Some of your subs came back after this picture was made."
 *
 * AstroStack sets subs aside on its own — a satellite trail, a bad grade, a file
 * it couldn't read — and it also puts them *back* on its own when it works out
 * they were good after all (an edge-on galaxy that only looked like a trail, a
 * grade re-run on a bigger night, a drive that came back online). That is a
 * quiet win, except for what happens next: the target's picture was stacked
 * before the subs returned, so it is thinner than the owner's own data, and with
 * auto-stack off nothing will ever notice.
 *
 * The "N new subs since your last stack" nudge structurally cannot see this: it
 * compares each sub's *capture* time against the stack, and a restored sub was
 * shot long before the picture was made — usually on the very night it is made
 * of. So this is the one surface that can say so, and it says it from the
 * server's own record of *when* each sub came back (`frames.restored_utc`)
 * rather than from a count comparison, which would nag forever on any target
 * whose run legitimately combined fewer frames than it was offered.
 *
 * It only ever offers — re-stacking is hours of CPU on a NAS — and it self-hides
 * the moment the re-stack lands. The verdict is fetched by the page rather than
 * here, because the page also uses it to decide which of the two "stack it
 * again" notes speaks; `null`/`undefined` (an older backend, a failed fetch, or
 * simply nothing to say) renders nothing.
 */
export function RestoredSubsNote(
  { safe, back }: { safe: string; back: RestoredSubs | null | undefined },
) {
  const qc = useQueryClient();
  const restack = useMutation({
    mutationFn: () => api.processTarget(safe),
    onSuccess: () => {
      notifications.show({
        message: "Stacking again — this run will include the subs that came back. "
          + "Watch Jobs for progress.",
        color: "violet",
      });
      qc.invalidateQueries({ queryKey: ["jobs"] });
    },
    onError: (e: Error) => notifications.show({ message: e.message, color: "red" }),
  });

  if (!back) return null;
  const n = back.n_restored;
  const stacked = formatStampDate(back.timestamp_utc);
  return (
    <Alert color="blue" variant="light" icon={<IconArrowBackUp size={18} />}
      title={`${n.toLocaleString()} sub${n === 1 ? "" : "s"} came back after this picture was made`}
      data-testid="restored-subs-note">
      <Text size="sm">
        {`AstroStack had set ${n === 1 ? "a sub" : `${n.toLocaleString()} subs`} aside — `}
        {"as a satellite trail, on quality, or because the file couldn't be read — "}
        {`and has since worked out ${n === 1 ? "it was" : "they were"} fine and put `}
        {n === 1 ? "it" : "them"}{" back."}
        {` Your picture was stacked ${stacked ? `on ${stacked}, ` : ""}before that, `}
        {`so it doesn't include ${n === 1 ? "that sub" : "those subs"} yet. `}
        {"Stacking again folds "}{n === 1 ? "it" : "them"}{" in — nothing is lost "}
        {"either way, the picture you have stays in this target's history."}
      </Text>
      {back.n_frames_used > 0 ? (
        <Text size="xs" c="dimmed" mt={4}>
          {`The picture you have was made from ${back.n_frames_used.toLocaleString()} sub`}
          {back.n_frames_used === 1 ? "" : "s"}
          {". Re-stacking takes a while — best started when you're not waiting on the app."}
        </Text>
      ) : null}
      <Group gap="xs" mt="xs">
        <Button size="xs" variant="filled" color="blue"
          leftSection={<IconStack2 size={14} />}
          loading={restack.isPending} onClick={() => restack.mutate()}>
          Stack it again
        </Button>
      </Group>
    </Alert>
  );
}
