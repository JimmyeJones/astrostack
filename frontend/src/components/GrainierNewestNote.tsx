import { Alert, Button, Group, Text } from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { IconCloud, IconStarFilled } from "@tabler/icons-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";
import { formatStampDate } from "../format";

/**
 * "Last night's stack came out grainier than an earlier one — show that instead?"
 *
 * The mirror of `CleanestShotNote`, for the state a beginner is actually in.
 * That note handles a *pinned* cover going stale; this one handles the case
 * where nothing is pinned at all — which is the default, and the one where the
 * picture on show can quietly go **backwards**. Unpinned, the cover simply
 * follows the newest stack, so a restack through haze (or one where auto-reject
 * set a lot of subs aside) replaces a better picture on the Library tile, "My
 * best pictures" and the montage wall, with nothing said anywhere.
 *
 * So: say it once, with the numbers, and offer the earlier picture back — the
 * same one-tap `setTargetCover` the History page's star already uses, so there
 * is nothing new to undo. The app never pins anything by itself.
 *
 * The two notes can never both speak: this endpoint needs *nothing* pinned and
 * `cleanest-shot` needs a pin. Self-hiding and stateless — accepting the offer
 * pins a cover, which is exactly the state where this falls silent, so there is
 * no dismissal to go stale. Best-effort: an older backend (404) or a failed
 * fetch renders nothing, exactly as before this existed.
 */
export function GrainierNewestNote({ safe }: { safe: string }) {
  const qc = useQueryClient();
  const nudge = useQuery({
    queryKey: ["grainier-newest", safe],
    queryFn: () => api.grainierNewest(safe).catch(() => null),
    enabled: !!safe,
    staleTime: 30_000,
    retry: false,
  });
  const pin = useMutation({
    mutationFn: (runId: number) => api.setTargetCover(safe, runId),
    onSuccess: () => {
      // The same set the cleaner-shot note invalidates: this note, History's
      // star, the target payload, the Library tiles and the "My best pictures"
      // wall (which picks its representative from the cover).
      qc.invalidateQueries({ queryKey: ["grainier-newest", safe] });
      qc.invalidateQueries({ queryKey: ["cleanest-shot", safe] });
      qc.invalidateQueries({ queryKey: ["runs", safe] });
      qc.invalidateQueries({ queryKey: ["targets"] });
      qc.invalidateQueries({ queryKey: ["target", safe] });
      qc.invalidateQueries({ queryKey: ["galleryBest"] });
      notifications.show({
        message: "Cover updated — your better picture is on show now",
        color: "teal",
      });
    },
    onError: () => notifications.show({
      message: "Could not update cover", color: "red",
    }),
  });

  const g = nudge.data;
  if (!g) return null;
  const when = formatStampDate(g.timestamp_utc);
  // Say *why* only when the frame counts actually explain it; otherwise the
  // honest answer is "the sky was probably worse", not a number we don't have.
  const thinner = g.newest_n_frames_used < g.n_frames_used;
  return (
    <Alert color="yellow" variant="light" icon={<IconCloud size={18} />}
      title="Your newest stack came out grainier than an earlier one"
      data-testid="grainier-newest-note">
      <Text size="sm">
        {`It has about ${g.percent_grainier}% more background grain than your `}
        {when ? `${when} ` : "earlier "}
        {"stack"}
        {thinner
          ? ` — it combined ${g.newest_n_frames_used} subs against `
            + `${g.n_frames_used}, so it had less light to work with. `
          : " — the sky was probably hazier that night. "}
        {"You haven't pinned a cover, so the newest stack is what the Library "}
        {"tile and \"My best pictures\" show. Nothing is lost either way — both "}
        {"stacks are still in this target's history."}
      </Text>
      <Group gap="xs" mt="xs">
        <Button size="xs" variant="filled" color="yellow"
          leftSection={<IconStarFilled size={14} />}
          loading={pin.isPending}
          onClick={() => pin.mutate(g.run_id)}>
          Show the better one instead
        </Button>
      </Group>
    </Alert>
  );
}
