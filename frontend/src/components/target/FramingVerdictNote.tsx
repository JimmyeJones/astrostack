import { Alert, Anchor, Group, Text } from "@mantine/core";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { api, type StackFraming } from "../../api/client";
import {
  recentreCropRect, recentreKeptLabel, recentreRefusalLine,
} from "../editor/recentreCrop";
import { cropCoverageFraction } from "../editor/mosaicTrim";

const TONE: Record<StackFraming["level"], { color: string; icon: string }> = {
  centred: { color: "teal", icon: "🎯" },
  off_centre: { color: "blue", icon: "🎯" },
  clipped: { color: "yellow", icon: "✂️" },
  partial: { color: "yellow", icon: "🧩" },
};

/**
 * The measured framing verdict for one run, or `undefined` when there isn't one.
 *
 * Exported because the *Target* page needs the same answer the note itself
 * reaches: it also renders `ObjectInfoCard`, whose catalog "will it fit?" line
 * predicts the very thing this measures, and two sentences saying "it's bigger
 * than one frame" on one page is one too many. Sharing the query key means
 * react-query serves both from a single request, and asking the same source
 * means the generic line can only ever step aside when the measured one is
 * genuinely on screen — a run with no usable WCS keeps it.
 *
 * `runId` may be `null` (no finished picture yet); the fetch is then skipped.
 */
export function useStackFraming(safe: string, runId: number | null) {
  return useQuery({
    queryKey: ["stack-framing", safe, runId],
    queryFn: () => api.stackFraming(safe, runId as number),
    enabled: runId != null,
  }).data;
}

const TITLE: Record<StackFraming["level"], string> = {
  centred: "Nicely framed",
  off_centre: "It landed off to one side",
  clipped: "Part of it is outside the frame",
  partial: "It's bigger than one frame",
};

/**
 * "Did I frame it well?" — one plain-language line on the finished picture.
 *
 * The app already warns *before* a session that a target may be too big for one
 * Seestar frame. Nothing told a beginner afterwards how it actually landed — and
 * the framing surprises that matter (the object well off-centre, or half of it
 * running off an edge) are only visible once the picture exists, by which point
 * a whole night has been spent. The verdict is measured from the run's own
 * solved WCS and the object's catalog size, so it describes what happened rather
 * than what was intended, and it always says what to do differently.
 *
 * Self-hiding: renders nothing when the endpoint has no honest answer (target
 * not in the catalog, no vetted size, or a run with no usable WCS), so it's safe
 * to drop in unconditionally.
 */
export function FramingVerdictNote({ safe, runId }: { safe: string; runId: number }) {
  const v = useStackFraming(safe, runId);
  // The picture they have *now* can often be improved too: when the target landed
  // off to one side and a crop can put it back in the middle without gutting the
  // frame, offer that as a one-click trip into the editor. An offer, never an
  // automatic change — it lands as a normal Crop op they preview, apply, adjust
  // or drop. Absent (older backend, or a crop that wouldn't help) → no link.
  const recentre = recentreCropRect(v?.recentre);
  // …but the verdict is measured from the *stack*, which can't see that the user
  // already cropped this picture in the editor an hour ago. Offering to re-centre
  // something they re-centred themselves reads as the app not noticing their work,
  // so ask the saved recipe — only when there's actually an offer to make, so an
  // ordinary target page costs no extra request.
  const recipe = useQuery({
    queryKey: ["recipe", safe, runId],
    queryFn: () => api.getRecipe(safe, runId),
    enabled: !!recentre,
  });
  if (!v) return null;
  const tone = TONE[v.level] ?? TONE.centred;
  // A *disabled* crop op isn't shrinking anything, which `cropCoverageFraction`
  // already knows. An unreadable recipe falls back to making the offer — the old
  // behaviour — rather than silently withholding it.
  const alreadyCropped = !!recentre
    && recipe.isSuccess
    && cropCoverageFraction(recipe.data?.ops ?? []) != null;
  const offerRecentre = !!recentre && !recipe.isLoading && !alreadyCropped;
  const refusal = recentre ? null : recentreRefusalLine(v.recentre_refused, v.object_name);
  return (
    <Alert
      color={tone.color}
      variant="light"
      data-testid="framing-verdict"
      title={
        <Group gap={6} wrap="nowrap">
          <span aria-hidden>{tone.icon}</span>
          <span>{TITLE[v.level] ?? TITLE.centred}</span>
        </Group>
      }
    >
      <Text size="sm">{`${v.object_name} ${v.text}`}</Text>
      {/* "Re-centre it next session" is only advice you can act on once you know
          which way. Absent on an older backend, or where a re-point isn't the fix. */}
      {v.nudge ? (
        <Text size="sm" mt={6} data-testid="framing-nudge">
          {v.nudge.text}
        </Text>
      ) : null}
      {offerRecentre && recentre ? (
        <Text size="sm" mt={6}>
          <Anchor component={Link} to={`/targets/${safe}/edit/${runId}?recentre=1`}
            data-testid="framing-recentre">
            Re-centre this picture
          </Anchor>
          {` — crop it so ${v.object_name} sits in the middle `}
          ({recentreKeptLabel(recentre)}). You can adjust or remove the crop
          afterwards.
        </Text>
      ) : null}
      {alreadyCropped ? (
        <Text size="sm" mt={6} data-testid="framing-already-cropped">
          You've already cropped this picture —{" "}
          <Anchor component={Link} to={`/targets/${safe}/edit/${runId}`}>
            open the editor
          </Anchor>
          {" "}to adjust it.
        </Text>
      ) : null}
      {/* The worst-framed pictures used to get the *least* help: no offer and no
          explanation. This is the sentence the refusal already knew. */}
      {refusal ? (
        <Text size="sm" c="dimmed" mt={6} data-testid="framing-recentre-refused">
          {refusal}
        </Text>
      ) : null}
      <Text size="xs" c="dimmed" mt={4}>
        Measured from where {v.object_name} actually landed in this picture and its
        catalogue size (about {Math.round(v.size_arcmin)}′ across).
      </Text>
    </Alert>
  );
}
