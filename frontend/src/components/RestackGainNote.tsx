import { Alert, Button, Group, Text } from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { IconCalendarQuestion, IconStack2 } from "@tabler/icons-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";
import { formatStampDate } from "../format";

/**
 * "This picture was made before AstroStack recorded when your subs were shot."
 *
 * Most of what an old run is missing the app can heal from disk on its own — its
 * coverage share and its panel-seam figure both are, silently, the first time
 * anyone looks. **When its subs were shot cannot be**, because nothing on disk
 * records which frames that run used. So a picture from before the app learned
 * to record that says "Stacked 30 Aug 2026" where it should say "Shot over 4
 * nights, 15–18 Nov 2024" — on its captions, its nameplate, the share sheet, the
 * Gallery card, the History row and the Sky footprint — and it will say that
 * forever, because nothing anywhere tells the owner that pressing Stack again
 * would fix it. This note is that missing sentence.
 *
 * Three rules it keeps, all decided server-side (see
 * `seestack/restackgain.py`), because they are what stop it being a nag:
 * it names **a gain, never a version** ("your version is old" is not a reason a
 * beginner can act on); it never appears unless the target's own subs are
 * datable *now*, so it cannot promise a date a re-stack wouldn't supply; and it
 * only ever **offers** — re-stacking is hours of CPU on a NAS, so the app never
 * does it uninvited.
 *
 * It also says what the re-stack would cost, in the only unit that matters here
 * (how many subs it would combine), and it self-hides the moment the re-stack
 * lands. Best-effort: an older backend (404) or a failed fetch renders nothing.
 */
export function RestackGainNote({ safe }: { safe: string }) {
  const qc = useQueryClient();
  const gain = useQuery({
    queryKey: ["restack-gain", safe],
    queryFn: () => api.restackGain(safe).catch(() => null),
    enabled: !!safe,
    staleTime: 30_000,
    retry: false,
  });
  const restack = useMutation({
    mutationFn: () => api.processTarget(safe),
    onSuccess: () => {
      notifications.show({
        message: "Stacking again — this run will record when your subs were shot. "
          + "Watch Jobs for progress.",
        color: "violet",
      });
      qc.invalidateQueries({ queryKey: ["jobs"] });
    },
    onError: (e: Error) => notifications.show({ message: e.message, color: "red" }),
  });

  const g = gain.data;
  if (!g) return null;
  const stacked = formatStampDate(g.timestamp_utc);
  return (
    <Alert color="blue" variant="light" icon={<IconCalendarQuestion size={18} />}
      title="This picture can't say which night it's from"
      data-testid="restack-gain-note">
      <Text size="sm">
        {g.missing_capture_window
          ? "It was made before AstroStack recorded when your subs were shot, so "
            + "everywhere it's shown — captions, the share sheet, your Gallery "
            + `and History — its date is ${stacked ? `the day it was stacked (${stacked})` : "the day it was stacked"}, `
            + "not the night you took it. "
          : "It knows the dates its subs were shot, but not how many nights they "
            + "came from — so its captions can name two dates but never say "
            + "\"over four nights\", which is the part worth saying. "}
        {"Your subs still carry their capture times, so stacking this target "}
        {"again would fix it. Nothing is lost either way — the picture you have "}
        {"stays in this target's history."}
      </Text>
      <Text size="xs" c="dimmed" mt={4}>
        {`It would re-combine ${g.n_frames_ready.toLocaleString()} sub`}
        {g.n_frames_ready === 1 ? "" : "s"}
        {g.n_frames_used > 0
          ? ` (the picture you have was made from ${g.n_frames_used.toLocaleString()})`
          : ""}
        {", which takes a while — best started when you're not waiting on the app."}
      </Text>
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
