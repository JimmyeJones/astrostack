import { Alert, Button, Group, Text } from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { IconSparkles, IconStarFilled } from "@tabler/icons-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";

/**
 * "This stack is your cleanest yet — make it the cover?"
 *
 * A target's **cover** is the picture the Library tile, "My best pictures", the
 * montage wall and the gallery's "best" endpoint all show. It defaults to the
 * newest stack, but once the owner *pins* a run as the cover it stays pinned
 * forever — deliberately, because that choice is theirs (a favourite framing, a
 * hand-edited version). The quiet cost is that a beginner who keeps adding subs
 * gets steadily cleaner stacks while every showcase surface keeps showing the
 * older, grainier picture, and nothing ever mentions the gap.
 *
 * So: mention it, once, with the numbers — and let them decide. Taking the offer
 * goes through the same `setTargetCover` the History page already uses, so there
 * is nothing new to undo (History's star still toggles it back). The app never
 * swaps a cover by itself.
 *
 * Self-hiding and stateless: the endpoint returns `null` the moment the newest
 * stack *is* the cover, so accepting clears the note with no dismissal state to
 * go stale. Best-effort — an older backend (404) or a failed fetch renders
 * nothing, exactly as before this existed.
 */
export function CleanestShotNote({ safe }: { safe: string }) {
  const qc = useQueryClient();
  const shot = useQuery({
    queryKey: ["cleanest-shot", safe],
    queryFn: () => api.cleanestShot(safe).catch(() => null),
    enabled: !!safe,
    staleTime: 30_000,
    retry: false,
  });
  const promote = useMutation({
    mutationFn: (runId: number) => api.setTargetCover(safe, runId),
    onSuccess: () => {
      // The same set History's "Set as cover" invalidates (its star, the
      // target payload, the Library tiles and the "My best pictures" wall,
      // which picks its representative from the cover), plus this note.
      qc.invalidateQueries({ queryKey: ["cleanest-shot", safe] });
      qc.invalidateQueries({ queryKey: ["runs", safe] });
      qc.invalidateQueries({ queryKey: ["targets"] });
      qc.invalidateQueries({ queryKey: ["target", safe] });
      qc.invalidateQueries({ queryKey: ["galleryBest"] });
      notifications.show({
        message: "Cover updated — your cleanest stack is on show now",
        color: "teal",
      });
    },
    onError: () => notifications.show({
      message: "Could not update cover", color: "red",
    }),
  });

  const s = shot.data;
  if (!s) return null;
  const deeper = s.n_frames_used > s.cover_n_frames_used;
  return (
    <Alert color="teal" variant="light" icon={<IconSparkles size={18} />}
      title="This is your cleanest shot of this target yet"
      data-testid="cleanest-shot-note">
      <Text size="sm">
        {`Your newest stack has about ${s.percent_cleaner}% less background grain `}
        {"than the picture you pinned as this target's cover"}
        {deeper
          ? ` — it combined ${s.n_frames_used} subs against ${s.cover_n_frames_used}, `
            + "so the extra time you put in is showing. "
          : " — the extra time you put in is showing. "}
        {"Your cover is what the Library tile and \"My best pictures\" show, and "}
        {"it only changes when you say so."}
      </Text>
      <Group gap="xs" mt="xs">
        <Button size="xs" variant="filled" color="teal"
          leftSection={<IconStarFilled size={14} />}
          loading={promote.isPending}
          onClick={() => promote.mutate(s.run_id)}>
          Make this the cover
        </Button>
      </Group>
    </Alert>
  );
}
