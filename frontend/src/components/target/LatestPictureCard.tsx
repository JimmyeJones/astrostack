import { useEffect, useRef, useState } from "react";
import { Alert, Anchor, Box, Button, Group, Image, Paper, Text } from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api, type StackRun } from "../../api/client";
import { formatIntegration } from "../../format";
import { ImageLightbox } from "../ImageLightbox";
import { isJobPollAbort, pollJobUntilDone } from "../editor/pollJob";
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
  const qc = useQueryClient();
  // Hooks must run unconditionally, so this is declared before the early return.
  // `run` is captured lazily inside the mutation, which only fires from a button
  // that cannot exist without one.
  const mounted = useRef(true);
  useEffect(() => () => { mounted.current = false; }, []);
  const finishEdit = useMutation({
    mutationFn: () => api.exportSavedEdit(safe, run!.id, `${safe}_edit`),
    onSuccess: ({ job_id }) => {
      notifications.show({
        message: "Making your edited version — it'll appear here when it's done.",
        color: "violet",
      });
      qc.invalidateQueries({ queryKey: ["jobs"] });
      // Refresh the runs list when the export lands, so the promise the message
      // makes ("it'll appear here") is one the page actually keeps — the new run
      // becomes the hero and this note goes away, with no manual reload.
      // Best-effort and unmount-guarded; the navbar job badge tracks it anyway.
      void pollJobUntilDone(job_id, {
        getJob: api.getJob, isAbandoned: () => !mounted.current, intervalMs: 1000,
      })
        .then(() => qc.invalidateQueries({ queryKey: ["runs", safe] }))
        .catch((e) => {
          if (isJobPollAbort(e)) return;
          notifications.show({ message: (e as Error).message, color: "red" });
        });
    },
    onError: (e: Error) => notifications.show({ message: e.message, color: "red" }),
  });
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
      {/* The honest half of "your picture": a saved-but-never-exported edit lives
          only in the editor, so what's shown above is still the plain auto-stretch
          of the stack. Say so where the picture is, and offer the one step that
          makes their version the real one — rather than quietly showing an image
          they didn't make. */}
      {run.unexported_edit && (
        <Alert
          color="violet" variant="light" p="xs" mt="xs" radius="sm"
          data-testid="unexported-edit"
        >
          <Text size="xs">
            You edited this picture and saved it, but never exported it — so this is
            still the un-edited version. Finishing it makes your edit the picture
            shown here, in the Gallery, and in anything you share.
          </Text>
          <Group gap="sm" mt={6} wrap="nowrap">
            <Button
              size="compact-xs" variant="light" color="violet"
              loading={finishEdit.isPending}
              onClick={() => finishEdit.mutate()}
            >
              Finish my edit
            </Button>
            <Anchor component={Link} to={`/targets/${safe}/edit/${run.id}`} size="xs">
              Open the editor
            </Anchor>
          </Group>
        </Alert>
      )}
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
