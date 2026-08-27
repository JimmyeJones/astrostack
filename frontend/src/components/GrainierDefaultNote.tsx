import { Alert, Button, Group, Text } from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { IconCloudRain, IconStarFilled } from "@tabler/icons-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";
import { formatNightDayMonth } from "../format";

/**
 * "Last night's stack came out grainier — show the better one instead?"
 *
 * The mirror of `CleanestShotNote`, for the case that one deliberately leaves
 * out. A target's **cover** is the picture the Library tile, "My best pictures",
 * the montage wall and the gallery's "best" endpoint all show. `CleanestShotNote`
 * handles the *pinned* cover going stale — but with nothing pinned the cover
 * means "newest", and that is the state a beginner is actually in, and the one
 * where the default can go *backwards* on its own.
 *
 * A restack through haze — or one where auto-reject rightly set a lot of subs
 * aside — produces a legitimately newer stack with materially more background
 * grain than one the target already has, and every showcase surface switches to
 * it with nothing said. The picture quietly gets worse and the app looks like
 * it's working fine. Saying so once, with the numbers, is the trust half of what
 * the app promises: an owner who walks away has to be able to believe the
 * picture they come back to is the best one they've got.
 *
 * It never pins anything by itself. Taking the offer goes through the same
 * `setTargetCover` the History page already uses, so there is nothing new to
 * undo (History's star still toggles it back). Self-hiding and stateless: the
 * endpoint returns `null` the moment something is pinned, so accepting clears
 * the note with no dismissal state to go stale. Best-effort — an older backend
 * (404) or a failed fetch renders nothing, exactly as before this existed.
 */
export function GrainierDefaultNote({ safe }: { safe: string }) {
  const qc = useQueryClient();
  const hit = useQuery({
    queryKey: ["grainier-default", safe],
    queryFn: () => api.grainierDefault(safe).catch(() => null),
    enabled: !!safe,
    staleTime: 30_000,
    retry: false,
  });
  const pin = useMutation({
    mutationFn: (runId: number) => api.setTargetCover(safe, runId),
    onSuccess: () => {
      // The same set History's "Set as cover" invalidates (its star, the target
      // payload, the Library tiles and the "My best pictures" wall, which picks
      // its representative from the cover), plus both cover nudges — pinning
      // silences this one and is exactly the state the other one watches.
      qc.invalidateQueries({ queryKey: ["grainier-default", safe] });
      qc.invalidateQueries({ queryKey: ["cleanest-shot", safe] });
      qc.invalidateQueries({ queryKey: ["runs", safe] });
      qc.invalidateQueries({ queryKey: ["targets"] });
      qc.invalidateQueries({ queryKey: ["target", safe] });
      qc.invalidateQueries({ queryKey: ["galleryBest"] });
      notifications.show({
        message: "Cover updated — your cleaner picture is on show now",
        color: "teal",
      });
    },
    onError: () => notifications.show({
      message: "Could not update cover", color: "red",
    }),
  });

  const g = hit.data;
  if (!g) return null;
  const when = formatNightDayMonth(g.best_timestamp_utc);
  // Past a doubling, a percentage stops reading as a quantity and starts reading
  // as a bug ("about 2400% more grain"), so a big gap is stated as a multiple
  // instead — the way anyone would say it out loud. The endpoint keeps reporting
  // the honest percent either way; this is phrasing, not a different number.
  const gap = g.percent_grainier > 200
    ? `about ${(1 + g.percent_grainier / 100).toFixed(1)}× as much background grain as`
    : `about ${g.percent_grainier}% more background grain than`;
  // Fewer subs is the one *concrete* explanation we can stand behind (a hazy
  // night usually means auto-reject set more aside). With the same or more subs
  // the honest answer is "the sky was worse", not a count.
  const thinner = g.best_n_frames_used > g.n_frames_used;
  return (
    <Alert color="orange" variant="light" icon={<IconCloudRain size={18} />}
      title="Your newest stack came out grainier than an earlier one"
      data-testid="grainier-default-note">
      <Text size="sm">
        {`The stack now on show has ${gap} `}
        {when ? `your ${when} one` : "an earlier one"}
        {thinner
          ? ` — it combined ${g.n_frames_used} subs against ${g.best_n_frames_used}, `
            + "which usually means a hazier night left more of them unusable. "
          : ", which usually means the sky was worse that night. "}
        {"Nothing is pinned as this target's cover, so the Library tile and "}
        {"\"My best pictures\" simply follow your newest stack. Both pictures are "}
        {"safe — you can put the better one back on show, and swap it again any "}
        {"time from History."}
      </Text>
      <Group gap="xs" mt="xs">
        <Button size="xs" variant="filled" color="teal"
          leftSection={<IconStarFilled size={14} />}
          loading={pin.isPending}
          onClick={() => pin.mutate(g.run_id)}>
          Show the cleaner picture
        </Button>
      </Group>
    </Alert>
  );
}
