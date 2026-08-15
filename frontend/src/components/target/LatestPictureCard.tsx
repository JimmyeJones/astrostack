import { useState } from "react";
import { Anchor, Box, Group, Image, Paper, Text } from "@mantine/core";
import { Link } from "react-router-dom";
import { api, type StackRun } from "../../api/client";
import { formatIntegration } from "../../format";
import { ImageLightbox } from "../ImageLightbox";
import { sharePictureText } from "../../share";

/**
 * The one-line provenance caption under the picture. Pure/testable.
 *
 * Deliberately plain: when it was stacked, how many subs went in, and how much
 * light that is — the three things a beginner uses to tell "is this the picture
 * I think it is?". Anything measured or diagnostic belongs in the insight tabs,
 * not here.
 */
export function latestPictureCaption(run: StackRun): string {
  const parts: string[] = [];
  const t = new Date(run.timestamp_utc);
  if (!Number.isNaN(t.getTime())) {
    parts.push(`Stacked ${t.toLocaleDateString()}`);
  }
  parts.push(`${run.n_frames_used} frame${run.n_frames_used === 1 ? "" : "s"}`);
  if (run.total_exposure_s) parts.push(`${formatIntegration(run.total_exposure_s)} of light`);
  return parts.join(" · ");
}

/**
 * "Your picture" — the target's newest finished stack, shown at the top of the
 * Target page.
 *
 * Why this exists (IA slice (c) of the owner's "the pages are extremely busy"
 * item): the Target page used to show *everything about* a target except the
 * thing the user came for. The finished picture lived only on History, behind a
 * click, so the page opened onto notes, analysis cards and a frames table and a
 * beginner had to go looking for their own image. This puts it above the fold,
 * one click from the editor, and clicking it opens the same zoomable lightbox
 * (with the same download/share controls) as everywhere else.
 *
 * Renders nothing when there is no finished picture yet — the parent's
 * pre-stack "First look" reassurance covers that case, unchanged.
 */
export function LatestPictureCard({
  safe, name, run,
}: {
  safe: string;
  name?: string;
  run?: StackRun | null;
}) {
  const [light, setLight] = useState(false);
  if (!run || !run.has_preview) return null;
  const previewSrc = api.stackArtifactUrl(safe, run.id, "preview");
  const share = sharePictureText(name, new Date(run.timestamp_utc).toLocaleDateString());
  return (
    <Paper withBorder p="sm" radius="md" data-testid="latest-picture">
      <Group justify="space-between" gap="xs" mb={6} wrap="nowrap">
        <Text size="sm" fw={500}>Your picture</Text>
        <Group gap="sm" wrap="nowrap">
          <Anchor component={Link} to={`/targets/${safe}/edit/${run.id}`} size="xs">
            Edit this picture
          </Anchor>
          <Anchor component={Link} to={`/targets/${safe}/history`} size="xs" c="dimmed">
            All versions
          </Anchor>
        </Group>
      </Group>
      {/* Height-capped on purpose: the point of this slice is that the picture
          AND the frames table below it fit on one screen, so the thumbnail must
          not push the table off the fold on a 1080p window. */}
      <Box
        style={{ background: "#000", borderRadius: 8, overflow: "hidden", cursor: "zoom-in" }}
        onClick={() => setLight(true)}
      >
        <Image
          src={previewSrc}
          alt={`Latest stacked picture of ${name ?? "this target"}`}
          fit="contain"
          h={260}
          fallbackSrc=""
        />
      </Box>
      <Text size="xs" c="dimmed" mt={6}>
        {latestPictureCaption(run)} — click to view it big
      </Text>
      <ImageLightbox
        src={light ? previewSrc : null}
        title={run.output_basename}
        downloadHref={previewSrc}
        jpegHref={api.stackArtifactUrl(safe, run.id, "jpeg")}
        fullResHref={run.has_fits ? api.stackFullResPngUrl(safe, run.id) : undefined}
        rawHref={run.has_fits ? api.stackArtifactUrl(safe, run.id, "fits") : undefined}
        shareFilename={share.filename}
        shareTitle={share.title}
        shareText={share.text}
        onClose={() => setLight(false)}
      />
    </Paper>
  );
}
