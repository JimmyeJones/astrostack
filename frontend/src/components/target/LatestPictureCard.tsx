import { useEffect, useRef, useState } from "react";
import { Alert, Anchor, Button, Group, Paper, Text } from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api, type FieldObject, type StackRun } from "../../api/client";
import { formatCaptureNights, formatIntegration, pictureDateLabel } from "../../format";
import { AnnotatedImage, croppedAnnotationView, objectLabel } from "../AnnotatedImage";
import { ImageLightbox } from "../ImageLightbox";
import { NorthUpViewToggle, loadNorthUpView, saveNorthUpView } from "../NorthUpViewToggle";
import { ShowRemovedToggle } from "../ShowRemovedToggle";
import { removedOverlayCaption } from "../../removed";
import { isJobPollAbort, pollJobUntilDone } from "../editor/pollJob";
import { sharePictureText } from "../../share";

/**
 * The one-line provenance caption under the picture. Pure/testable.
 *
 * Deliberately plain: when the light was collected, how many subs went in, and
 * how much light that is — the three things a beginner uses to tell "is this
 * the picture I think it is?". Anything measured or diagnostic belongs in the
 * insight tabs, not here.
 *
 * The date goes through `pictureDateLabel`, which prefers the run's capture
 * window and *names which date it is* either way — "Shot 15 Nov 2024", else
 * "Stacked 30 Aug 2026". This card used to print the stack stamp unconditionally
 * and it is the app's most prominent picture: dogfooding the sample showed
 * "Stacked Aug 30, 2026" directly above a frames table of 2024-11-15 subs.
 */
export function latestPictureCaption(run: StackRun): string {
  const parts: string[] = [];
  const when = pictureDateLabel(
    run.capture_night_start, run.capture_night_end, run.timestamp_utc,
    run.capture_nights);
  if (when) parts.push(when);
  parts.push(`${run.n_frames_used} frame${run.n_frames_used === 1 ? "" : "s"}`);
  if (run.total_exposure_s) parts.push(`${formatIntegration(run.total_exposure_s)} of light`);
  return parts.join(" · ");
}

/**
 * The one-line "what's in it?" readout under the labelled picture. Pure/testable.
 *
 * Names the catalog objects the overlay just pinned, in the order the backend
 * returned them (brightest/most notable first), capped so the line can't grow
 * into a paragraph on a rich field — the Target page is the one the owner called
 * "extremely busy", so this stays one line whatever lands in the frame.
 * Returns "" for an empty field, so the caller can say the honest thing instead.
 */
export function inThisPictureSentence(objects: FieldObject[], limit = 6): string {
  if (!objects.length) return "";
  const shown = objects.slice(0, limit).map(objectLabel);
  const rest = objects.length - shown.length;
  return rest > 0
    ? `In this picture: ${shown.join(", ")} and ${rest} more`
    : `In this picture: ${shown.join(", ")}`;
}

/**
 * "Your picture" — the target's own finished stack, shown at the top of the
 * Target page: the run the owner **pinned as the cover** when there is one, and
 * otherwise the newest, exactly as the Library tile and the Best wall resolve it
 * (see `representativeRun`). `pinned` says which, so the heading can name it;
 * `newerRunId` is set only when a pinned cover is standing in front of a newer
 * picture, so the card can say so instead of leaving someone to wonder whether
 * their restack ran.
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
  safe, name, run, pinned = false, newerRunId = null,
}: {
  safe: string;
  name?: string;
  run?: StackRun | null;
  pinned?: boolean;
  newerRunId?: number | null;
}) {
  const [light, setLight] = useState(false);
  // "What's in it?" — the same named-object overlay History has always had, on
  // the page a beginner actually lands on. Off by default (the picture is the
  // point; the labels are the answer to a question they have to ask), and the
  // annotations are only fetched once they ask, so an ordinary page load makes
  // no extra request.
  const [identify, setIdentify] = useState(false);
  // "Show it the way every reference photo of this object is" — a *view*, not a
  // save. Remembered per viewer, off by default: the saved orientation is the
  // one the owner chose (see `NorthUpViewToggle`).
  const [northUp, setNorthUp] = useState(loadNorthUpView);
  // "Show what stacking removed" — the History card's tint, offered where the
  // picture is actually big enough to read it. Off by default, and only on runs
  // that recorded a map at all (`record_rejection_map`, off by default), so the
  // control is absent rather than inert on every ordinary stack.
  const [showRemoved, setShowRemoved] = useState(false);
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
  // Same endpoint and cache key History uses, so asking here warms the answer
  // there (and vice versa) instead of solving the field twice. Needs the run's
  // FITS-header WCS, hence the `has_fits` gate.
  // Also fetched when the picture is opened big, because the same response now
  // answers "would turning this to North up actually change anything?" — the
  // one question the lightbox's view toggle needs, and one this handler already
  // reads the WCS for. Still nothing on an ordinary page load.
  const annotations = useQuery({
    queryKey: ["annotations", safe, run?.id],
    queryFn: () => api.stackAnnotations(safe, run!.id),
    enabled: (identify || light) && !!run?.has_fits,
    staleTime: Infinity,
  });
  // The caption's measured fraction, on the same endpoint and cache key the
  // History card's copy of this tint uses — fetched only once the tint is
  // actually switched on, so an ordinary page load (and an ordinary lightbox
  // open) asks for nothing.
  const removedInfo = useQuery({
    queryKey: ["stack-info", safe, run?.id],
    queryFn: () => api.stackRunInfo(safe, run!.id),
    enabled: showRemoved && !!run?.has_rejection_map,
    staleTime: Infinity,
  });
  if (!run || !run.has_preview) return null;
  const previewSrc = api.stackArtifactUrl(safe, run.id, "preview");
  // The date on a shared picture is when its subs were *shot*, never when the
  // stack ran — a run with no recorded capture window shares without one.
  const share = sharePictureText(
    name, formatCaptureNights(run.capture_night_start, run.capture_night_end));
  // The pins are measured on the run's un-rotated, un-cropped FITS grid, and this
  // card always shows the *stored* preview bytes. A crop the one-click auto-edit
  // baked in composes exactly (shift the pixels into the trim); a baked-in
  // North-up rotation, or a render whose geometry isn't a crop at all, does not —
  // so hide the pins and say why, exactly as History does, rather than mis-plot.
  const view = croppedAnnotationView(
    run.preview_crop,
    annotations.data?.objects ?? [],
    null,
    annotations.data?.width ?? run.canvas_w,
    annotations.data?.height ?? run.canvas_h,
  );
  const cantPlaceMarks = !!run.preview_north_up_deg || !!run.preview_geometry_unknown;
  const sentence = inThisPictureSentence(view.objects);
  // Offer the turn only where it would visibly do something: the run reports a
  // real correction, and its stored bytes aren't already turned (a picture a
  // past "Adjust → North up → Save" baked is North-up on disk, and asking for
  // it again is a no-op the server correctly refuses to repeat).
  //
  // The second half is now belt-and-braces: since v0.309.0 the endpoint reports
  // the *remainder* — what a `?north_up=true` render would still apply — so it
  // already returns null on a baked run. Kept deliberately rather than removed:
  // it costs nothing, and dropping it would make this page depend on that
  // meaning for correctness rather than merely agree with it.
  const canNorthUp = typeof annotations.data?.north_up_deg === "number"
    && !run.preview_north_up_deg;
  const turned = northUp && canNorthUp;
  // Everything the lightbox hands over follows what's on screen — the preview
  // it shows, the JPEG behind Share, and the full-res PNG — so a picture you
  // downloaded because you liked how it looked arrives that way. The FITS
  // deliberately does not: the raw data stays WCS-aligned.
  const lightboxSrc = turned
    ? api.stackPreviewNorthUpUrl(safe, run.id) : previewSrc;
  // The tint is measured against the *stored* preview bytes, which is exactly
  // what this lightbox shows — so unlike the pins and the scale bar it needs no
  // stand-down for a baked-in crop or rotation, and it composes with the
  // North-up *view* by taking the same turn the picture underneath takes.
  const hasRejectionMap = !!run.has_rejection_map;
  return (
    <Paper withBorder p="sm" radius="md" data-testid="latest-picture">
      <Group justify="space-between" gap="xs" mb={6} wrap="nowrap">
        <Text size="sm" fw={500}>
          {pinned ? "Your picture (cover)" : "Your picture"}
        </Text>
        <Group gap="sm" wrap="nowrap">
          {/* Only offered when the run still has its FITS: the object positions
              come off its WCS, and a preview-only run has none to read. */}
          {run.has_fits ? (
            <Anchor
              component="button" type="button" size="xs"
              data-testid="identify-toggle"
              onClick={() => setIdentify((v) => !v)}
            >
              {identify ? "Hide labels" : "What’s in it?"}
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
      <AnnotatedImage
        src={previewSrc}
        alt={`Latest stacked picture of ${name ?? "this target"}`}
        imgWidth={view.width}
        imgHeight={view.height}
        objects={view.objects}
        show={identify && !cantPlaceMarks}
        height={260}
        onClick={() => setLight(true)}
      />
      <Text size="xs" c="dimmed" mt={6}>
        {latestPictureCaption(run)} — click to view it big
      </Text>
      {/* A pinned cover standing in front of a newer stack. Without this the
          page looks like the restack never happened — the picture is simply the
          older one, with nothing on screen to say why. Says it plainly and
          points at where to change it, rather than second-guessing the pin. */}
      {pinned && newerRunId != null ? (
        <Text size="xs" c="dimmed" mt={4} data-testid="cover-newer-note">
          You pinned this one as this target’s cover, so it’s the picture shown
          everywhere. You have a newer stack —{" "}
          <Anchor component={Link} to={`/targets/${safe}/history`} size="xs">
            see all versions
          </Anchor>.
        </Text>
      ) : null}
      {identify ? (
        <Text size="xs" c={cantPlaceMarks ? "dimmed" : "cyan.4"} mt={4}
          data-testid="identify-readout">
          {cantPlaceMarks
            ? (run.preview_north_up_deg
              ? "This picture was saved rotated so North is up, so object labels can’t be placed on it — they’re measured on the un-rotated image."
              : "This picture was reshaped when it was processed, so object labels can’t be placed on it — they’re measured on the original image.")
            : annotations.isError
            ? "Couldn’t work out what’s in this picture."
            : annotations.isLoading
            ? "Working out what’s in this picture…"
            : sentence
            || "No catalog objects landed in this picture — it’s a patch of sky between the famous ones."}
          {/* The names are drawn in the browser, so they vanish the moment the
              picture leaves the app — and "here's the Running Man Nebula, just
              above Orion" is a far better post than an unlabelled smudge. Offered
              *here*, while the labels are on screen, rather than as a seventh item
              in the page's Save/share menu: the owner's standing complaint is that
              these pages are too busy, and this is the one moment the option is
              obviously wanted. Shown only when there is actually something to
              label — the server would hand back the plain picture otherwise. */}
          {!cantPlaceMarks && view.objects.length ? (
            <>
              {" "}
              <Anchor
                component="a"
                data-testid="save-labelled"
                href={api.stackArtifactUrl(
                  safe, run.id, "jpeg", false, false, false, false, true)}
                download
                size="xs"
              >
                Save it with the names on it
              </Anchor>
            </>
          ) : null}
        </Text>
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
        src={light ? lightboxSrc : null}
        title={run.output_basename}
        downloadHref={lightboxSrc}
        jpegHref={api.stackArtifactUrl(safe, run.id, "jpeg", turned)}
        fullResHref={run.has_fits
          ? api.stackFullResPngUrl(safe, run.id, turned) : undefined}
        fullResCanvas={{ w: run.canvas_w, h: run.canvas_h }}
        rawHref={run.has_fits ? api.stackArtifactUrl(safe, run.id, "fits") : undefined}
        overlaySrc={showRemoved && hasRejectionMap
          ? api.stackRejectionOverlayUrl(safe, run.id, turned) : null}
        overlayNote={removedOverlayCaption(removedInfo.data?.rejection)}
        toolbarExtra={canNorthUp || hasRejectionMap ? (
          <>
            {canNorthUp ? (
              <NorthUpViewToggle
                on={northUp}
                onChange={(on) => { setNorthUp(on); saveNorthUpView(on); }}
              />
            ) : null}
            {hasRejectionMap ? (
              <ShowRemovedToggle on={showRemoved} onChange={setShowRemoved} />
            ) : null}
          </>
        ) : undefined}
        shareFilename={share.filename}
        shareTitle={share.title}
        shareText={share.text}
        onClose={() => setLight(false)}
      />
    </Paper>
  );
}
