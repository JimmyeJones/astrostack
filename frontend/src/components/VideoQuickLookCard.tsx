import { Image, Paper, Text } from "@mantine/core";
import type { VideoQuickLook } from "../api/client";

/**
 * "Quick look" — the sharpest single frame of a checked Moon/Sun capture.
 *
 * Before this, the only way to see what a capture actually held was to run a
 * full lucky stack: two decode passes and a multi-minute wait, after which a
 * beginner might learn a cloud had rolled in or the Moon had drifted out of
 * frame. The grading pass already finds the best frame, so showing that one
 * frame turns "should I bother stacking this?" into a look.
 *
 * Self-hiding, like `VideoSharpnessCard`: a capture that has never been checked
 * (or was checked by a version that kept only the scores) renders nothing.
 */
export function VideoQuickLookCard({
  quicklook, subject,
}: {
  quicklook: VideoQuickLook | null | undefined;
  subject: string;
}) {
  if (!quicklook) return null;
  return (
    <Paper withBorder radius="md" p="sm" mt="sm">
      <Text size="sm" fw={600} mb={6}>Quick look</Text>
      <Image
        src={quicklook.url}
        alt={`The sharpest single frame of your ${subject} capture`}
        fit="contain"
        mah={240}
        bg="black"
        radius="sm"
      />
      {/* The backend writes this sentence from the capture's own numbers — and
          it is the part that keeps a noisy single frame from being mistaken for
          the finished picture, so it is never abbreviated away. */}
      <Text size="xs" c="dimmed" mt={6}>{quicklook.note}</Text>
    </Paper>
  );
}
