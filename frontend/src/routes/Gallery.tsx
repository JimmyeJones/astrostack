import { useMemo, useState } from "react";
import {
  ActionIcon, Alert, Badge, Button, Card, Center, Checkbox, Group, Image, Loader,
  Menu, Paper, SegmentedControl, Select, SimpleGrid, Spoiler, Stack, Text, TextInput,
  Title, Tooltip,
} from "@mantine/core";
import {
  IconArrowBackUp, IconCopy, IconCrop, IconGitCompare, IconPhoto, IconPlayerPlay,
  IconSearch, IconSparkles, IconVideo, IconWand,
} from "@tabler/icons-react";
import { notifications } from "@mantine/notifications";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate } from "react-router-dom";
import {
  api, type GalleryItem, type StackOptionField, type VideoStill,
} from "../api/client";
import { sharePictureText } from "../share";
import { formatIntegration, formatStampDate } from "../format";
import { HazyNightBadge } from "../components/HazyNightBadge";
import { PanelSeamsBadge } from "../components/PanelSeamsBadge";
import { CalibrationBadge } from "../components/CalibrationBadge";
import { UnexportedEditBadge } from "../components/UnexportedEditBadge";
import { FrameCountBadge } from "../components/target/FrameCountBadge";
import {
  RejectionBadge, combineMethodKey, COMBINE_METHOD_LABELS, type CombineMethod,
} from "../components/RejectionBadge";
import { NoiseReadout, hasNoise } from "../components/NoiseBadge";
import { ImageLightbox } from "../components/ImageLightbox";
import {
  NorthUpViewToggle, loadNorthUpView, saveNorthUpView,
} from "../components/NorthUpViewToggle";
import { ShowRemovedToggle } from "../components/ShowRemovedToggle";
import { removedOverlayCaption } from "../removed";
import { WallpaperMenu } from "../components/WallpaperMenu";
import { QueryError } from "../components/QueryError";
import { videoPreviewSrc } from "../components/videoPreviewSrc";
import {
  DEFAULT_SHARPEN, SHARPEN_PRESETS, cropNote, cropSuggestion, sharpenNote,
  sharpenOffer, sharpenValueOf,
} from "../components/videoFraming";
import { FirstImageCard } from "../components/dashboard/FirstImageCard";
import { runSlideKey, showFromHref, videoSlideKey } from "../showAndTell";

export type GallerySort = "newest" | "cleanest";
export type CalFilter = "all" | "calibrated" | "uncalibrated";
export type MethodFilter = "all" | CombineMethod;

// A run counts as "calibrated" when it recorded a non-empty calibration status
// (the additive `calstat` column, "dark+flat"/"bias+flat"/…). Pre-v0.48 runs
// and uncalibrated stacks have a null/empty calstat.
export function isCalibrated(it: GalleryItem): boolean {
  return !!(it.calstat && it.calstat.trim());
}

// Filter items by calibration status. "all" is a passthrough; "calibrated" keeps
// runs that applied any master; "uncalibrated" keeps the rest. Pure and
// non-mutating so it's easy to test.
export function filterByCalibration(items: GalleryItem[], filter: CalFilter): GalleryItem[] {
  if (filter === "all") return items;
  const want = filter === "calibrated";
  return items.filter((it) => isCalibrated(it) === want);
}

// Order gallery items for display. "newest" preserves the API's timestamp-DESC
// order; "cleanest" puts the lowest-noise stacks first (a global "show me my
// cleanest results" across every target — the recorded σ is normalized to each
// image's own signal range so it's comparable across gain/exposure), with runs
// that carry no measured σ (pre-v0.48 or not computable) kept after, in their
// original order. Pure and non-mutating so it's easy to test.
export function sortGallery(items: GalleryItem[], sort: GallerySort): GalleryItem[] {
  if (sort !== "cleanest") return items;
  const measured = items.filter((it) => hasNoise(it.noise_sigma));
  const rest = items.filter((it) => !hasNoise(it.noise_sigma));
  measured.sort((a, b) => (a.noise_sigma as number) - (b.noise_sigma as number));
  return [...measured, ...rest];
}

// Free-text filter across a run's label (notes), target name, output basename
// and its calibration status ("dark+flat", …) — so a user can find "best RGB
// v2", "M42", or every "flat"-calibrated stack across every target. Pure and
// non-mutating so it's easy to test. An empty/whitespace query matches all.
export function filterGallery(items: GalleryItem[], query: string): GalleryItem[] {
  const q = query.trim().toLowerCase();
  if (!q) return items;
  return items.filter((it) =>
    [it.notes, it.target_name, it.output_basename, it.calstat]
      .some((s) => (s ?? "").toLowerCase().includes(q)));
}

// Filter items by their (coarse) combine method. "all" is a passthrough;
// otherwise keep runs whose effective method matches. Editor/channel-combine runs
// (no method key) are dropped by any non-"all" filter. Pure and non-mutating.
export function filterByMethod(items: GalleryItem[], filter: MethodFilter): GalleryItem[] {
  if (filter === "all") return items;
  return items.filter((it) => combineMethodKey(it.options) === filter);
}

// One card in the grid. A finished Moon/Sun still is a picture the user made,
// so it belongs here next to their stacks — but it is not a stack run (no
// target, no run id, no stacking options, none of the per-run actions), so it
// travels as its own variant rather than being faked into a GalleryItem.
export type GalleryEntry =
  | { kind: "run"; run: GalleryItem }
  | { kind: "video"; video: VideoStill };

// Sortable instant for either kind of entry. Both timestamps are UTC ISO 8601
// but a stack run's carries microseconds and a video still's doesn't, so compare
// the shared "YYYY-MM-DDTHH:MM:SS" prefix rather than the whole string.
function entryInstant(e: GalleryEntry): string {
  return (e.kind === "run" ? e.run.timestamp_utc : e.video.created_utc).slice(0, 19);
}

// Free-text filter over Moon/Sun stills — the plain-language label ("Moon"), the
// video file the picture came from, and the capture folder id. Mirrors
// filterGallery so the single search box covers both kinds of picture. Pure and
// non-mutating. An empty/whitespace query matches all.
export function filterVideoStills(videos: VideoStill[], query: string): VideoStill[] {
  const q = query.trim().toLowerCase();
  if (!q) return videos;
  return videos.filter((v) =>
    [v.label, v.source_name, v.capture_id]
      .some((s) => (s ?? "").toLowerCase().includes(q)));
}

// Interleave finished Moon/Sun stills with the (already sorted and filtered)
// stack runs into the one grid.
//
// "newest" merges both by date, so the picture someone made five minutes ago is
// first whichever kind it is. "cleanest" ranks by measured background noise —
// something a video still has no equivalent of — so rather than invent a score
// for it, the stills keep their own newest-first order after the ranked runs.
// Pure and non-mutating.
export function mergeGalleryEntries(
  runs: GalleryItem[], videos: VideoStill[], sort: GallerySort,
): GalleryEntry[] {
  const runEntries: GalleryEntry[] = runs.map((run) => ({ kind: "run", run }));
  const videoEntries: GalleryEntry[] = videos.map((video) => ({ kind: "video", video }));
  if (sort !== "newest") return [...runEntries, ...videoEntries];
  return [...runEntries, ...videoEntries].sort((a, b) =>
    entryInstant(a) < entryInstant(b) ? 1 : entryInstant(a) > entryInstant(b) ? -1 : 0);
}

/** The dimmed detail line under a Moon/Sun still: where it came from, when, how
 * big, and how many video frames were averaged into it. */
export function videoStillCaption(v: VideoStill): string {
  const when = v.created_utc.replace("T", " ").slice(0, 16);
  const frames = `${v.n_stacked} frame${v.n_stacked === 1 ? "" : "s"}`;
  return `${v.source_name} · ${when} · ${v.width}×${v.height} · ${frames} stacked`;
}

function VideoStillCard({ still, onView }: {
  still: VideoStill;
  onView: (still: VideoStill) => void;
}) {
  const qc = useQueryClient();

  // The same in-place crop the Moon & Sun page offers, on the surface where the
  // picture actually lives. It matters here most: Moon & Sun lists the captures
  // still sitting in `incoming/`, so someone who has cleared the video off the
  // NAS only ever sees their Moon here — adrift in black sky, with nowhere to
  // fix it. Neither call re-decodes anything; both slice the saved artifacts.
  const cropStill = useMutation({
    mutationFn: () => api.cropVideoStill(still.capture_id),
    onSuccess: (r) => {
      qc.invalidateQueries({ queryKey: ["gallery"] });
      qc.invalidateQueries({ queryKey: ["videos"] });
      notifications.show({
        message: (
          `Trimmed ${Math.round((r.crop_trim_fraction ?? 0) * 100)}% of empty sky `
          + `— your ${still.label} picture is now ${r.width}×${r.height}.`
        ),
        color: "teal",
      });
    },
    onError: (e: Error) => notifications.show({ message: e.message, color: "red" }),
  });

  const restoreStill = useMutation({
    mutationFn: () => api.restoreVideoStill(still.capture_id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["gallery"] });
      qc.invalidateQueries({ queryKey: ["videos"] });
      notifications.show({ message: "Put the full frame back.", color: "teal" });
    },
    onError: (e: Error) => notifications.show({ message: e.message, color: "red" }),
  });

  // …and the other in-place edit, for the same reason and on the same terms:
  // every strength is rendered from the copy kept beside the picture, so trying
  // them costs nothing and "Off" gets the user back exactly where they started.
  const sharpenStill = useMutation({
    mutationFn: (amount: number) => api.sharpenVideoStill(still.capture_id, amount),
    onSuccess: (r) => {
      qc.invalidateQueries({ queryKey: ["gallery"] });
      qc.invalidateQueries({ queryKey: ["videos"] });
      notifications.show({
        message: (r.sharpen_amount ?? 0) > 0
          ? `Sharpened your ${still.label} picture — change it again any time.`
          : `Put the unsharpened ${still.label} picture back.`,
        color: "teal",
      });
    },
    onError: (e: Error) => notifications.show({ message: e.message, color: "red" }),
  });

  // Reused from Moon & Sun rather than re-worded, so the two surfaces can never
  // drift into telling the user two different things about one picture.
  const suggestCrop = cropSuggestion(still, still.kind);
  const cropped = cropNote(still, still.kind);
  const sharpened = sharpenNote(still.sharpen_amount);
  const offerSharpen = sharpenOffer(still, still.kind);

  return (
    <Card withBorder padding="md" radius="md">
      <Card.Section>
        <Tooltip label="Click to view fullscreen" openDelay={400}>
          <Image
            src={videoPreviewSrc(still)} h={200} fit="contain" bg="#000"
            alt={`${still.label} still`}
            style={{ cursor: "zoom-in" }}
            onClick={() => onView(still)}
          />
        </Tooltip>
      </Card.Section>

      <Group justify="space-between" mt="sm" wrap="nowrap">
        <Text fw={600} truncate>{still.label}</Text>
        <Badge size="sm" variant="light" color="yellow" style={{ flexShrink: 0 }}>
          Moon &amp; Sun
        </Badge>
      </Group>
      <Text size="xs" c="dimmed">{videoStillCaption(still)}</Text>

      {cropped ? (
        <Group gap="xs" wrap="nowrap" align="center" mt={4}>
          <Text size="xs" c="dimmed">{cropped}</Text>
          {/* A framing decision should never be one-way — the full frame is kept
              beside the cropped one, so undoing it is a click. */}
          {still.crop_restorable ? (
            <Button
              size="compact-xs" variant="subtle"
              leftSection={<IconArrowBackUp size={12} />}
              onClick={() => restoreStill.mutate()}
              loading={restoreStill.isPending}
            >
              Undo crop
            </Button>
          ) : null}
        </Group>
      ) : null}

      {sharpened ? <Text size="xs" c="dimmed" mt={4}>{sharpened}</Text> : null}

      {/* Verbatim engine strings, as the Moon & Sun card renders them — this is
          the only surface a user whose clip is gone still has, so it must not be
          the one that stays quiet about frames the stack had to drop. */}
      {(still.warnings ?? []).map((w) => (
        <Text key={w} size="xs" c="dimmed" mt={4}>{w}</Text>
      ))}

      {suggestCrop ? (
        <Alert color="violet" variant="light" icon={<IconCrop size={16} />} p="xs" mt="xs">
          <Text size="xs">{suggestCrop}</Text>
          <Button
            size="compact-xs" variant="light" mt={6}
            leftSection={<IconCrop size={12} />}
            onClick={() => cropStill.mutate()}
            loading={cropStill.isPending}
          >
            Crop it
          </Button>
        </Alert>
      ) : null}

      {/* The person whose clip is long gone off the NAS is precisely the person
          who can't re-stack to change how sharp their picture is — so this is
          the surface where the in-place sharpen matters most. */}
      {offerSharpen ? (
        <Alert color="violet" variant="light" icon={<IconSparkles size={16} />} p="xs" mt="xs">
          <Text size="xs">{offerSharpen}</Text>
          <Select
            mt={6}
            size="xs"
            label="Bring out surface detail"
            description="Applied to the saved picture — no re-stack."
            data={SHARPEN_PRESETS}
            value={sharpenValueOf(still)}
            onChange={(v) => sharpenStill.mutate(Number(v ?? DEFAULT_SHARPEN))}
            disabled={sharpenStill.isPending}
            allowDeselect={false}
          />
        </Alert>
      ) : null}

      <Group gap="xs" mt="xs" wrap="nowrap">
        {/* Deliberately one link, not a per-run action row: none of the stack
            actions (edit, reuse settings, set as cover) apply to a video still,
            so the card points back at the page that does own it. */}
        <Button
          component={Link} to="/moon-sun"
          leftSection={<IconVideo size={14} />} variant="light" color="gray" size="xs"
          style={{ flex: 1 }}
        >
          Open in Moon &amp; Sun
        </Button>
      </Group>
    </Card>
  );
}

/** Format an option value for display (booleans → On/Off, round floats). */
function fmt(v: unknown): string {
  if (v === null || v === undefined || v === "") return "—";
  if (typeof v === "boolean") return v ? "On" : "Off";
  if (typeof v === "number") return Number.isInteger(v) ? String(v) : v.toFixed(2);
  return String(v);
}

/** A few headline settings shown as badges on every card. The combine method
 * (σ-clip / min-max / drizzle) is shown separately by <RejectionBadge>, which
 * carries a plain-language tooltip and honours the engine's method precedence. */
function highlightBadges(opts: Record<string, unknown>) {
  const badges: { label: string; on: boolean }[] = [];
  if (opts.quality_weighted) badges.push({ label: "Quality-weighted", on: true });
  if (opts.background_flatten) badges.push({ label: "BG flatten", on: true });
  if (opts.final_gradient_removal) badges.push({ label: "Gradient removal", on: true });
  if (typeof opts.lucky_fraction === "number" && opts.lucky_fraction < 1) {
    badges.push({ label: `Lucky ${Math.round(opts.lucky_fraction * 100)}%`, on: true });
  }
  return badges;
}

function GalleryCard({ item, labels, onView, selected, onToggleSelect }: {
  item: GalleryItem;
  labels: Map<string, string>;
  onView: (item: GalleryItem) => void;
  selected: boolean;
  onToggleSelect: () => void;
}) {
  const badges = highlightBadges(item.options);
  // Full settings list (only keys we have a label for, in schema order).
  const rows = useMemo(
    () =>
      [...labels.entries()]
        .filter(([key]) => item.options[key] !== undefined)
        .map(([key, label]) => ({ label, value: fmt(item.options[key]) })),
    [item.options, labels],
  );

  return (
    <Card withBorder padding="md" radius="md"
      style={selected ? { outline: "2px solid var(--mantine-color-violet-5)" } : undefined}>
      <Card.Section style={{ position: "relative" }}>
        <Checkbox
          checked={selected} onChange={onToggleSelect}
          aria-label="Select for batch edit"
          styles={{ root: { position: "absolute", top: 8, left: 8, zIndex: 2 } }}
        />
        {item.has_preview ? (
          <Tooltip label="Click to view fullscreen" openDelay={400}>
            <Image
              src={item.preview_url} h={200} fit="contain" bg="#000"
              style={{ cursor: "zoom-in" }}
              onClick={() => onView(item)}
            />
          </Tooltip>
        ) : (
          <Center h={200} bg="dark.6"><Text c="dimmed">No preview</Text></Center>
        )}
      </Card.Section>

      <Group justify="space-between" mt="sm" wrap="nowrap">
        {/* The badge group beside this is ``flexShrink: 0``, so on a narrow card
            a long target name truncates hard — "Sample: Orion Nebula (M42)" can
            end up as "Sample: …". Carry the full name as a ``title`` so it is
            still readable on hover, exactly as the notes line below already
            does. */}
        <Text fw={600} truncate title={item.target_name}
              component={Link} to={`/targets/${item.safe}/history`}>
          {item.target_name}
        </Text>
        <Group gap={4} wrap="nowrap" style={{ flexShrink: 0 }}>
          <RejectionBadge options={item.options} />
          <HazyNightBadge ratio={item.transparency_ratio} />
          <PanelSeamsBadge verdict={item.seam_verdict} />
          <CalibrationBadge calstat={item.calstat} />
          {/* This card's thumbnail is the run's baked preview, so a saved-but-
              never-exported edit isn't in it — say so here too, not just on
              History and the Target hero. */}
          <UnexportedEditBadge show={item.unexported_edit} />
          <FrameCountBadge nFramesUsed={item.n_frames_used} />
        </Group>
      </Group>
      {item.notes ? (
        <Text size="sm" c="violet.4" fw={500} truncate title={item.notes}>
          {item.notes}
        </Text>
      ) : null}
      <Text size="xs" c="dimmed">
        {item.output_basename} · {item.timestamp_utc.replace("T", " ").slice(0, 16)}
        {" · "}{item.canvas_w}×{item.canvas_h}
        {item.total_exposure_s ? ` · ${formatIntegration(item.total_exposure_s)}` : ""}
        {hasNoise(item.noise_sigma) ? <> · <NoiseReadout sigma={item.noise_sigma} /></> : null}
      </Text>

      {/* ``wrap="nowrap"`` + ``flex: 1`` (basis 0) let the primary button shrink
          below its own label: measured in a real build, "Edit image" needed
          108 px of a 246 px card row and was given 99, so it rendered as
          "Edit imag" — the card's main action, clipped mid-word. ``1 1 auto``
          bases the button on its content, so it still fills a wide row but can
          no longer be squeezed under its label; with wrapping allowed the pair
          stacks on a narrow card (and on a phone) instead of clipping. */}
      <Group gap="xs" mt="xs">
        <Button
          component={Link} to={`/targets/${item.safe}/edit/${item.run_id}`}
          leftSection={<IconWand size={14} />} variant="light" size="xs"
          style={{ flex: "1 1 auto" }}
        >
          Edit image
        </Button>
        {item.reusable ? (
          <Tooltip label="Re-run the Stack form pre-filled with this image's settings">
            <Button
              component={Link} to={`/targets/${item.safe}/stack?from=${item.run_id}`}
              leftSection={<IconCopy size={14} />} variant="light" color="gray" size="xs"
            >
              Reuse settings
            </Button>
          </Tooltip>
        ) : null}
      </Group>

      {badges.length > 0 ? (
        <Group gap={6} mt="xs">
          {badges.map((b) => (
            <Badge key={b.label} size="sm" variant="dot" color="violet">{b.label}</Badge>
          ))}
        </Group>
      ) : null}

      {rows.length > 0 ? (
        <Spoiler maxHeight={0} showLabel="Stacking settings" hideLabel="Hide settings" mt="xs">
          <Stack gap={2} mt={6}>
            {rows.map((r) => (
              <Group key={r.label} justify="space-between" gap="xs" wrap="nowrap">
                <Text size="xs" c="dimmed" truncate>{r.label}</Text>
                <Text size="xs" style={{ flexShrink: 0 }}>{r.value}</Text>
              </Group>
            ))}
          </Stack>
        </Spoiler>
      ) : null}
    </Card>
  );
}

export function GalleryView() {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const gallery = useQuery({ queryKey: ["gallery"], queryFn: api.getGallery });
  const schema = useQuery({ queryKey: ["stackSchema"], queryFn: api.optionsSchema });
  const presets = useQuery({ queryKey: ["presets"], queryFn: api.listPresets });
  const [viewing, setViewing] = useState<GalleryItem | null>(null);
  const [viewingStill, setViewingStill] = useState<VideoStill | null>(null);
  // "Show it the way every reference photo of this object is" — a *view*, not a
  // save; nothing on disk changes. Off by default and remembered per viewer, in
  // the one `localStorage` key the Target page's copy of this control uses, so
  // turning it on here turns it on there too (see `NorthUpViewToggle`).
  const [northUp, setNorthUp] = useState(loadNorthUpView);
  // The same endpoint, cache key and staleness the Target hero uses, so opening
  // a picture here warms the answer there instead of asking twice. Only fetched
  // once a picture is actually open: an ordinary Gallery load makes no extra
  // request, however many cards it draws.
  const viewingAnnotations = useQuery({
    queryKey: ["annotations", viewing?.safe, viewing?.run_id],
    queryFn: () => api.stackAnnotations(viewing!.safe, viewing!.run_id),
    enabled: !!viewing?.has_fits,
    staleTime: Infinity,
  });
  // Offer the turn only where it would visibly do something: the run reports a
  // rotation `?north_up=true` would actually apply (null covers an unsolved run,
  // a field already sitting North-up, and a picture a past "Adjust → North up →
  // Save" already turned — asking again for any of those is a no-op).
  const viewingCanNorthUp =
    typeof viewingAnnotations.data?.north_up_deg === "number";
  const viewingTurned = northUp && viewingCanNorthUp;
  // What the big view is actually showing, and therefore what the PNG download
  // hands over. The turn is its own helper rather than a flag on
  // `stackArtifactUrl` on purpose: the bare artifact URLs stay WCS-aligned for
  // every surface that embeds them.
  const viewingNorthUpSrc = viewing
    ? api.stackPreviewNorthUpUrl(viewing.safe, viewing.run_id) : "";
  const viewingSrc = !viewing ? ""
    : viewingTurned ? viewingNorthUpSrc : viewing.preview_url;
  const viewingPngHref = !viewing ? undefined
    : viewingTurned ? viewingNorthUpSrc
      : api.stackArtifactUrl(viewing.safe, viewing.run_id, "preview");
  // "Show what stacking removed" — the History card's tint, offered where the
  // picture is big enough to actually read it. This viewer always shows the
  // *stored* preview bytes (turned on the way out, at most), which is exactly
  // what the tint is measured against, so it composes rather than standing down
  // the way the pins and the scale bar have to. Off by default, and only on the
  // runs that recorded a map at all — `record_rejection_map` is off by default,
  // so most pictures get no control rather than an inert one.
  const [showRemoved, setShowRemoved] = useState(false);
  const viewingHasRemoved = !!viewing?.has_rejection_map;
  // The caption's measured fraction, on the endpoint and cache key History's
  // copy of this tint already uses. Fetched only once the tint is switched on,
  // so opening a picture costs nothing extra.
  const removedInfo = useQuery({
    queryKey: ["stack-info", viewing?.safe, viewing?.run_id],
    queryFn: () => api.stackRunInfo(viewing!.safe, viewing!.run_id),
    enabled: showRemoved && viewingHasRemoved,
    staleTime: Infinity,
  });
  const [search, setSearch] = useState("");
  const [sort, setSort] = useState<GallerySort>("newest");
  const [calFilter, setCalFilter] = useState<CalFilter>("all");
  const [methodFilter, setMethodFilter] = useState<MethodFilter>("all");
  // Batch selection: key "safe:run_id" -> {safe, run_id}.
  const [selected, setSelected] = useState<Record<string, { safe: string; run_id: number }>>({});
  const selKey = (it: GalleryItem) => `${it.safe}:${it.run_id}`;
  const toggleSelect = (it: GalleryItem) =>
    setSelected((s) => {
      const k = selKey(it);
      const next = { ...s };
      if (next[k]) delete next[k]; else next[k] = { safe: it.safe, run_id: it.run_id };
      return next;
    });
  const selItems = Object.values(selected);

  const batch = useMutation({
    mutationFn: (preset_id: string) => api.batchApply({ items: selItems, preset_id }),
    onSuccess: () => {
      notifications.show({ message: `Batch edit started on ${selItems.length} images`, color: "violet" });
      setSelected({});
      qc.invalidateQueries({ queryKey: ["jobs"] });
      navigate("/jobs");
    },
    onError: (e: Error) => notifications.show({ message: e.message, color: "red" }),
  });
  const applyPreset = (id: string, label: string) => {
    if (window.confirm(`Apply "${label}" to ${selItems.length} image(s)? Each becomes a new edited stack.`)) {
      batch.mutate(id);
    }
  };

  const labels = useMemo(() => {
    const m = new Map<string, string>();
    for (const f of (schema.data ?? []) as StackOptionField[]) {
      // output_name isn't an interesting "setting" to show in the gallery.
      if (f.key !== "output_name") m.set(f.key, f.label);
    }
    return m;
  }, [schema.data]);

  if (gallery.isError && !gallery.data) {
    return <QueryError error={gallery.error} onRetry={() => gallery.refetch()} />;
  }
  if (gallery.isLoading) {
    return <Center h={300}><Loader /></Center>;
  }
  if (gallery.isError) {
    return <Alert color="red" m="md" title="Could not load the gallery">
      {(gallery.error as Error)?.message}
    </Alert>;
  }

  const allItems = gallery.data?.items ?? [];
  // Free-text filter across the run's label (notes), target name, output
  // basename and calibration status — so a user can find "best RGB v2", "M42",
  // or their "flat"-calibrated stacks across every target.
  const items = sortGallery(
    filterByMethod(filterByCalibration(filterGallery(allItems, search), calFilter), methodFilter),
    sort,
  );
  // Finished Moon/Sun stills, folded into the same grid. They're hidden while a
  // *stack-specific* facet is active (calibration / combine method) — a video
  // still has neither, so keeping it in a "Calibrated" cut would be a lie about
  // what the filter selected.
  const allStills = gallery.data?.videos ?? [];
  const stills = calFilter === "all" && methodFilter === "all"
    ? filterVideoStills(allStills, search)
    : [];
  const entries = mergeGalleryEntries(items, stills, sort);
  // Only offer the Cleanest sort once it's a meaningful comparison: more than one
  // image and at least one carries a measured σ (pre-v0.48 runs have none).
  const anyNoise = allItems.some((it) => hasNoise(it.noise_sigma));
  const showSort = allItems.length > 1 && anyNoise;
  // Only offer the calibration filter when the set is *mixed* — some calibrated
  // and some not — so it's a useful cut, not a no-op chip.
  const anyCalibrated = allItems.some(isCalibrated);
  const anyUncalibrated = allItems.some((it) => !isCalibrated(it));
  const showCalFilter = anyCalibrated && anyUncalibrated;
  // Combine-method facet: the distinct methods present across all runs (in the
  // engine's precedence order). Only offered when the set is *mixed* (>1 distinct
  // method) so it's a useful cut, not a no-op chip — mirroring the cal filter.
  const METHOD_ORDER: CombineMethod[] = ["drizzle", "min-max", "sigma-clip", "mean"];
  const presentMethods = METHOD_ORDER.filter((m) =>
    allItems.some((it) => combineMethodKey(it.options) === m));
  const showMethodFilter = presentMethods.length > 1;

  return (
    <Stack>
      <Group gap="xs">
        <IconPhoto size={24} />
        <Title order={2}>Gallery</Title>
        <Tooltip label="Every picture you've made — stacked images across all targets, plus your Moon & Sun stills">
          <Badge variant="light">{allItems.length + allStills.length}</Badge>
        </Tooltip>
      </Group>

      {allItems.length + allStills.length > 0 ? (
        <Group justify="space-between" wrap="wrap" gap="xs">
          <TextInput
            value={search}
            onChange={(e) => setSearch(e.currentTarget.value)}
            placeholder="Search by label, target, filename or calibration…"
            leftSection={<IconSearch size={16} />}
            maw={420}
            style={{ flex: 1, minWidth: 220 }}
          />
          {showCalFilter ? (
            <Tooltip label="Filter by whether a stack had calibration masters (dark/flat/bias) applied to its lights.">
              <SegmentedControl
                size="xs"
                value={calFilter}
                onChange={(v) => setCalFilter(v as CalFilter)}
                data={[
                  { label: "All", value: "all" },
                  { label: "Calibrated", value: "calibrated" },
                  { label: "Uncalibrated", value: "uncalibrated" },
                ]}
              />
            </Tooltip>
          ) : null}
          {showMethodFilter ? (
            <Tooltip label="Filter by how each stack was combined (drizzle / min-max / σ-clip / mean).">
              <SegmentedControl
                size="xs"
                value={methodFilter}
                onChange={(v) => setMethodFilter(v as MethodFilter)}
                data={[
                  { label: "All", value: "all" },
                  ...presentMethods.map((m) => ({ label: COMBINE_METHOD_LABELS[m], value: m })),
                ]}
              />
            </Tooltip>
          ) : null}
          {showSort ? (
            <Tooltip label="Cleanest sorts by lowest background noise across every target — the σ is normalized so it's comparable between images.">
              <SegmentedControl
                size="xs"
                value={sort}
                onChange={(v) => setSort(v as GallerySort)}
                data={[
                  { label: "Newest", value: "newest" },
                  { label: "Cleanest", value: "cleanest" },
                ]}
              />
            </Tooltip>
          ) : null}
        </Group>
      ) : null}

      {selItems.length ? (
        <Paper withBorder p="sm" pos="sticky" top={8} style={{ zIndex: 3 }}>
          <Group justify="space-between" wrap="wrap" gap="xs">
            <Text fw={600}>{selItems.length} selected</Text>
            <Group gap="xs">
              <Button variant="subtle" size="xs" onClick={() => setSelected({})}>Clear</Button>
              {selItems.length === 2 ? (
                <Button
                  component={Link}
                  to={`/compare?a=${selItems[0].safe}:${selItems[0].run_id}&b=${selItems[1].safe}:${selItems[1].run_id}`}
                  variant="light" color="grape" size="xs"
                  leftSection={<IconGitCompare size={14} />}
                >
                  Compare
                </Button>
              ) : null}
              <Menu shadow="md" position="bottom-end" width={240}>
                <Menu.Target>
                  <Button size="xs" leftSection={<IconWand size={14} />} loading={batch.isPending}>
                    Apply preset to selected
                  </Button>
                </Menu.Target>
                <Menu.Dropdown mah={400} style={{ overflowY: "auto" }}>
                  <Menu.Label>Built-in</Menu.Label>
                  {(presets.data?.builtin ?? []).map((p) => (
                    <Menu.Item key={p.id} onClick={() => applyPreset(p.id, p.label)}>{p.label}</Menu.Item>
                  ))}
                  {(presets.data?.user ?? []).length ? <Menu.Label>My presets</Menu.Label> : null}
                  {(presets.data?.user ?? []).map((p) => (
                    <Menu.Item key={p.id} onClick={() => applyPreset(p.id, p.label)}>{p.label}</Menu.Item>
                  ))}
                </Menu.Dropdown>
              </Menu>
            </Group>
          </Group>
        </Paper>
      ) : null}

      {entries.length === 0 ? (
        <Stack gap="sm">
          <Text c="dimmed">
            {search.trim()
              ? `No images match “${search.trim()}”.`
              : methodFilter !== "all"
                ? `No ${COMBINE_METHOD_LABELS[methodFilter]}-combined images.`
                : calFilter !== "all"
                  ? `No ${calFilter} images.`
                  : "No stacked images yet. Stack a target and its results will appear here."}
          </Text>
          {/* Only on a genuinely empty gallery — never when a search or filter is
              what emptied it, where "here's how to make your first picture" would
              read as a non-sequitur. The card itself also stays hidden on an
              established install and once dismissed. */}
          {!search.trim() && methodFilter === "all" && calFilter === "all"
            ? <FirstImageCard />
            : null}
        </Stack>
      ) : (
        <SimpleGrid cols={{ base: 1, sm: 2, md: 3, lg: 4 }}>
          {entries.map((e) => (
            e.kind === "run" ? (
              <GalleryCard
                key={`run-${e.run.safe}-${e.run.run_id}`} item={e.run} labels={labels}
                onView={setViewing}
                selected={!!selected[selKey(e.run)]}
                onToggleSelect={() => toggleSelect(e.run)}
              />
            ) : (
              <VideoStillCard
                key={`video-${e.video.capture_id}`} still={e.video}
                onView={setViewingStill}
              />
            )
          ))}
        </SimpleGrid>
      )}

      <ImageLightbox
        src={viewing ? viewingSrc : null}
        title={viewing ? `${viewing.target_name} · ${viewing.output_basename}` : undefined}
        downloadHref={viewing?.has_preview ? viewingPngHref : undefined}
        jpegHref={viewing?.has_preview
          ? api.stackArtifactUrl(viewing.safe, viewing.run_id, "jpeg", viewingTurned)
          : undefined}
        fullResHref={viewing?.has_fits
          ? api.stackFullResPngUrl(viewing.safe, viewing.run_id, viewingTurned) : undefined}
        fullResCanvas={viewing ? { w: viewing.canvas_w, h: viewing.canvas_h } : undefined}
        // The FITS deliberately does not follow the view: the raw data stays
        // WCS-aligned, whichever way the picture is being looked at.
        rawHref={viewing?.has_fits
          ? api.stackArtifactUrl(viewing.safe, viewing.run_id, "fits") : undefined}
        overlaySrc={viewing && showRemoved && viewingHasRemoved
          ? api.stackRejectionOverlayUrl(viewing.safe, viewing.run_id, viewingTurned)
          : null}
        overlayNote={removedOverlayCaption(removedInfo.data?.rejection)}
        toolbarExtra={viewing?.has_preview
          ? (
            <Group gap={4} wrap="nowrap">
              {/* Only where the turn would visibly do something — the run reports
                  a rotation `?north_up=true` would actually apply. Nothing here
                  has to fall out of register with the turned view: there are no
                  pins and no scale bar (both measured on the un-rotated FITS
                  grid), and the one thing that *is* laid over the picture — the
                  "what was removed" tint — takes the same turn the picture
                  itself takes. */}
              {viewingCanNorthUp ? (
                <NorthUpViewToggle
                  on={northUp}
                  onChange={(on) => { setNorthUp(on); saveNorthUpView(on); }}
                />
              ) : null}
              {viewingHasRemoved ? (
                <ShowRemovedToggle on={showRemoved} onChange={setShowRemoved} />
              ) : null}
              {/* Same "show me this one" entry point as My best pictures, so the
                  slideshow can start on whatever you're looking at. */}
              <Tooltip label="Start the slideshow on this picture">
                <ActionIcon
                  variant="subtle" color="gray" aria-label="Start the slideshow here"
                  component={Link} to={showFromHref(runSlideKey(viewing.safe, viewing.run_id))}
                >
                  <IconPlayerPlay size={18} />
                </ActionIcon>
              </Tooltip>
              <WallpaperMenu safe={viewing.safe} runId={viewing.run_id} variant="subtle" />
            </Group>
          ) : undefined}
        {...(viewing?.has_preview
          ? (() => {
              const { title, text, filename } = sharePictureText(
                viewing.target_name,
                formatStampDate(viewing.timestamp_utc),
              );
              return { shareFilename: filename, shareTitle: title, shareText: text };
            })()
          : {})}
        onClose={() => setViewing(null)}
      />

      {/* Moon/Sun stills get the same viewer, offering only what the video store
          actually holds: the display-rendered PNG plus the 16-bit TIFF beside it,
          worded exactly as Moon & Sun words it. There is no FITS, no JPEG and no
          full-res render behind a video still, so those controls stay absent
          rather than being offered and broken. */}
      <ImageLightbox
        src={viewingStill ? videoPreviewSrc(viewingStill) : null}
        title={viewingStill
          ? `${viewingStill.label} · ${viewingStill.source_name}` : undefined}
        downloadHref={viewingStill?.preview_url}
        rawHref={viewingStill?.tiff_url ?? undefined}
        rawLabel="16-bit TIFF"
        toolbarExtra={viewingStill ? (
          <Tooltip label="Start the slideshow on this picture">
            <ActionIcon
              variant="subtle" color="gray" aria-label="Start the slideshow here"
              component={Link} to={showFromHref(videoSlideKey(viewingStill.capture_id))}
            >
              <IconPlayerPlay size={18} />
            </ActionIcon>
          </Tooltip>
        ) : undefined}
        {...(viewingStill
          ? (() => {
              // The still's PNG *is* its picture, so the share sheet gets that —
              // named `.png`, since a PNG arriving called `.jpg` confuses the
              // app it lands in.
              const { title, text, filename } = sharePictureText(
                viewingStill.label,
                formatStampDate(viewingStill.created_utc),
                "png",
              );
              return { shareFilename: filename, shareTitle: title, shareText: text };
            })()
          : {})}
        onClose={() => setViewingStill(null)}
      />
    </Stack>
  );
}
