import { Alert, Group, Text } from "@mantine/core";
import { useQuery } from "@tanstack/react-query";

import { api, type StackFraming } from "../../api/client";

const TONE: Record<StackFraming["level"], { color: string; icon: string }> = {
  centred: { color: "teal", icon: "🎯" },
  off_centre: { color: "blue", icon: "🎯" },
  clipped: { color: "yellow", icon: "✂️" },
  partial: { color: "yellow", icon: "🧩" },
};

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
  const q = useQuery({
    queryKey: ["stack-framing", safe, runId],
    queryFn: () => api.stackFraming(safe, runId),
  });
  const v = q.data;
  if (!v) return null;
  const tone = TONE[v.level] ?? TONE.centred;
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
      <Text size="xs" c="dimmed" mt={4}>
        Measured from where {v.object_name} actually landed in this picture and its
        catalogue size (about {Math.round(v.size_arcmin)}′ across).
      </Text>
    </Alert>
  );
}
