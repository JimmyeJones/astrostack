import { useEffect, useRef, useState } from "react";
import { Alert, Anchor, Box, Button, Group, Paper, Stack, Text } from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api, type FieldObject, type StackRun } from "../../api/client";
import { formatIntegration, formatStampDate } from "../../format";
import { AnnotatedImage, croppedAnnotationView } from "../AnnotatedImage";
import { describeFieldObjects } from "../fieldObjectList";
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
  const stacked = formatStampDate(run.timestamp_utc);
  if (stacked) parts.push(`Stacked ${stacked}`);
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
  // "What's in it?" — the same named-catalog-object overlay History's Adjust
  // panel has, on the page a beginner actually lands on. Off by default (the
  // picture is the point; the labels are the answer to a question), and the
  // fetch is lazy so an ordinary visit costs nothing extra.
  const [identify, setIdentify] = useState(false);
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
  // The pins are measured on the run's un-rotated, un-cropped FITS grid, and this
  // card always shows the *stored* preview bytes — which an earlier "Adjust →
  // North up → Save" may have turned, and the one-click auto-edit may have
  // trimmed. A trim composes exactly (shift the pixels into it); a rotation, or a
  // geometry that can't be reduced to a crop at all, does not — say so rather
  // than mis-plot, exactly as History does, and don't even fetch.
  const cantPlaceMarks = !!run?.preview_north_up_deg || !!run?.preview_geometry_unknown;
  // Same endpoint, cache key and staleness History uses, so opening either page
  // after the other costs no second fetch. Needs the master's WCS, hence has_fits.
  const annotations = useQuery({
    queryKey: ["annotations", safe, run?.id],
    queryFn: () => api.stackAnnotations(safe, run!.id),
    enabled: identify && !!run?.has_fits && !cantPlaceMarks,
    staleTime: Infinity,
  });
  if (!run || !run.has_preview) return null;
  const previewSrc = api.stackArtifactUrl(safe, run.id, "preview");
  const share = sharePictureText(name, formatStampDate(run.timestamp_utc));
  const view = croppedAnnotationView(
    run.preview_crop,
    annotations.data?.objects ?? [],
    null,
    annotations.data?.width ?? run.canvas_w,
    annotations.data?.height ?? run.canvas_h,
  );
  const showLabels = identify && !cantPlaceMarks;
  return (
    <Paper withBorder p="sm" radius="md" data-testid="latest-picture">
      <Group justify="space-between" gap="xs" mb={6} wrap="nowrap">
        <Text size="sm" fw={500}>Your picture</Text>
        <Group gap="sm" wrap="nowrap">
          {run.has_fits ? (
            <Anchor
              component="button" type="button" size="xs" data-testid="identify-toggle"
              c={identify ? "cyan.4" : undefined}
              onClick={() => setIdentify((v) => !v)}
            >
              {identify ? "Hide labels" : "What's in it?"}
            </Anchor>
          ) : null}
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
      <Box style={{ borderRadius: 8, overflow: "hidden" }}>
        <AnnotatedImage
          src={previewSrc}
          alt={`Latest stacked picture of ${name ?? "this target"}`}
          imgWidth={view.width}
          imgHeight={view.height}
          objects={view.objects}
          show={showLabels}
          height={260}
          onClick={() => setLight(true)}
        />
      </Box>
      <Text size="xs" c="dimmed" mt={6}>
        {latestPictureCaption(run)} — click to view it big
      </Text>
      {identify ? (
        <ObjectLabelNote
          cantPlaceMarks={cantPlaceMarks}
          northUpSaved={!!run.preview_north_up_deg}
          loading={annotations.isLoading}
          ready={annotations.isSuccess}
          objects={view.objects}
          width={view.width}
          height={view.height}
        />
      ) : null}
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

/**
 * The words under the labelled picture — the friendly read of the same objects
 * the overlay pins, plus every honest reason the pins can't be drawn.
 *
 * Split out (and pure) so each state is testable on its own: a beginner who taps
 * "What's in it?" must always get a sentence back, never a silently unchanged
 * picture — including on the runs where the labels genuinely can't be placed.
 */
function ObjectLabelNote({
  cantPlaceMarks, northUpSaved, loading, ready, objects, width, height,
}: {
  cantPlaceMarks: boolean;
  northUpSaved: boolean;
  loading: boolean;
  ready: boolean;
  objects: FieldObject[];
  width: number;
  height: number;
}) {
  if (cantPlaceMarks) {
    return (
      <Text size="xs" c="dimmed" mt={6} data-testid="identify-note">
        {northUpSaved
          ? "This picture was saved rotated so North is up, so the labels can’t be placed on it — they’re measured on the un-rotated image. Open Adjust in All versions and save it un-rotated to use them."
          : "This picture was reshaped when it was processed, so the labels can’t be placed on it — they’re measured on the original image. Open Adjust in All versions and save it again to use them."}
      </Text>
    );
  }
  if (loading) {
    return (
      <Text size="xs" c="dimmed" mt={6} data-testid="identify-note">
        Looking up what’s in this picture…
      </Text>
    );
  }
  if (!ready) {
    return (
      <Text size="xs" c="dimmed" mt={6} data-testid="identify-note">
        Couldn’t work out what’s in this picture — it needs a located (plate-solved) stack.
      </Text>
    );
  }
  if (!objects.length) {
    return (
      <Text size="xs" c="dimmed" mt={6} data-testid="identify-note">
        No catalog objects fall inside this field
      </Text>
    );
  }
  const described = describeFieldObjects(objects, width, height);
  return (
    <Stack gap={2} mt={6} data-testid="identify-note">
      <Text size="xs" c="cyan.4">
        In this picture — {objects.length} catalog object{objects.length === 1 ? "" : "s"}:
      </Text>
      {described.map((d) => (
        <Text key={d.catalogId} size="xs" c="dimmed">
          {d.label}{d.typePhrase ? ` — ${d.typePhrase}` : ""}, {d.positionPhrase}.
        </Text>
      ))}
      {objects.length > described.length ? (
        <Text size="xs" c="dimmed">…and {objects.length - described.length} more.</Text>
      ) : null}
    </Stack>
  );
}
