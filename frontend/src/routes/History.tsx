import { useEffect, useRef, useState } from "react";
import {
  ActionIcon, Alert, Badge, Button, Card, Center, Group, Loader, SegmentedControl,
  SimpleGrid, Slider, Stack, Switch, Table, Text, TextInput, Title, Tooltip,
} from "@mantine/core";
import { useDebouncedValue } from "@mantine/hooks";
import { notifications } from "@mantine/notifications";
import { IconAdjustments, IconCheck, IconCopy, IconDeviceFloppy, IconDownload, IconGitCompare, IconInfoCircle, IconPencil, IconPhotoDown, IconSparkles, IconStar, IconStarFilled, IconTags, IconTrash, IconX } from "@tabler/icons-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import { api, type StackRun, type StackPhotometricSummary, type StackDarkScalingSummary, type StackRejectionSummary, type StackWeightingSummary, type StackFrameAccounting } from "../api/client";
import { formatIntegration } from "../format";
import { HazyNightBadge } from "../components/HazyNightBadge";
import { CalibrationBadge } from "../components/CalibrationBadge";
import { calibrationSummaryText } from "../components/calibrationSummary";
import { autoSkyCastCaption } from "../components/editor/skyCast";
import { autoColorCalCaption } from "../components/editor/colorCal";
import { RejectionBadge } from "../components/RejectionBadge";
import { NoiseReadout, NoiseDelta, CleanestBadge, cleanestRunId, hasNoise } from "../components/NoiseBadge";
import { ImageLightbox } from "../components/ImageLightbox";
import { AnnotatedImage } from "../components/AnnotatedImage";
import { StackHealthCard } from "../components/StackHealthCard";
import { ProgressReelCard } from "../components/ProgressReelCard";
import { OneFrameVsStackCard } from "../components/OneFrameVsStackCard";
import { SharePictureButton } from "../components/SharePictureButton";
import { WallpaperMenu } from "../components/WallpaperMenu";
import { sharePictureText } from "../share";
import { Sparkline } from "../components/Sparkline";

export type RunSort = "newest" | "cleanest";

// Order runs for display. "newest" preserves the API's timestamp-DESC order;
// "cleanest" puts the lowest-noise runs first, with runs that carry no measured
// σ (pre-v0.48 or not computable) kept after, in their original order. Pure and
// non-mutating so it's easy to test.
export function sortRuns(runs: StackRun[], sort: RunSort): StackRun[] {
  if (sort !== "cleanest") return runs;
  const measured = runs.filter((r) => hasNoise(r.noise_sigma));
  const rest = runs.filter((r) => !hasNoise(r.noise_sigma));
  measured.sort((a, b) => (a.noise_sigma as number) - (b.noise_sigma as number));
  return [...measured, ...rest];
}

// Map each run id → the fractional change in its background-noise σ against the
// same target's chronologically *previous* measured stack (the most recent older
// run that carries a σ). Negative = cleaner than last time. `runs` is the API's
// timestamp-DESC order; we walk it oldest→newest so "previous" means "earlier in
// time", independent of the display sort. Runs with no earlier measured σ (the
// first measured stack, or pre-v0.48 runs) get no entry. Pure/non-mutating.
export function noiseDeltas(runs: StackRun[]): Map<number, number> {
  const deltas = new Map<number, number>();
  let prev: number | null = null;
  for (let i = runs.length - 1; i >= 0; i--) {
    const r = runs[i];
    if (!hasNoise(r.noise_sigma)) continue;
    const sigma = r.noise_sigma as number;
    if (prev !== null && prev > 0) deltas.set(r.id, (sigma - prev) / prev);
    prev = sigma;
  }
  return deltas;
}

// Given the API's timestamp-DESC run list, return the id of the run that
// immediately *precedes* `id` in time (the next-older stack of this target) —
// the most common thing a user wants to compare against ("did adding subs /
// changing κ actually help vs my last run?"). The previous run is the next
// index in a newest-first list. Null when `id` is the oldest run or not found.
// Pure/non-mutating so it's easy to test.
export function previousRunId(runs: StackRun[], id: number): number | null {
  const idx = runs.findIndex((r) => r.id === id);
  if (idx < 0 || idx + 1 >= runs.length) return null;
  return runs[idx + 1].id;
}

// Build the bookmarkable /compare URL for two runs of the *same* target. The
// Compare view resolves each "<safe>:<run_id>" ref against the gallery (which
// carries every run), so a same-target link works with no backend change.
export function historyCompareHref(safe: string, aId: number, bId: number): string {
  return `/compare?a=${safe}:${aId}&b=${safe}:${bId}`;
}

// Extract this target's background-noise σ across runs in chronological order
// (oldest→newest), keeping only runs that carry a measured σ. `runs` is the
// API's timestamp-DESC order, so we reverse it. Drives the trend sparkline —
// lets a user see whether their stacks are getting cleaner as they add nights,
// not just the last hop. Pure/non-mutating.
export function noiseTrendSeries(runs: StackRun[]): number[] {
  const out: number[] = [];
  for (let i = runs.length - 1; i >= 0; i--) {
    if (hasNoise(runs[i].noise_sigma)) out.push(runs[i].noise_sigma as number);
  }
  return out;
}

// Translate the raw STACKER FITS card ("mean" / "sigma-clip" / "min-max-reject"
// / "drizzle") into a plain-language "how it was combined" line for the Info
// panel — the raw value is engine jargon a beginner won't recognise. Returns
// null when the method is unknown / absent (e.g. channel-combine runs, which
// use STACKMTD instead), so the line is simply omitted.
export function combineMethodLabel(
  cards: { key: string; value: string | number | boolean }[],
): string | null {
  const card = cards.find((c) => c.key === "STACKER");
  if (!card) return null;
  const method = String(card.value).trim().toLowerCase();
  const labels: Record<string, string> = {
    "mean": "Plain mean (no per-pixel outlier rejection)",
    "sigma-clip": "κ-σ (sigma-clip) outlier rejection",
    "min-max-reject": "Min/max (extremes) rejection — drops the highest and lowest value at each pixel",
    "drizzle": "Drizzle (sub-pixel resampling)",
  };
  return labels[method] ?? null;
}

// `calibrationSummaryText` now lives in a shared module so the editor's
// auto-note surface can tell the same calibration story (re-exported here to
// keep the History Info panel and its tests importing it from one place).
export { calibrationSummaryText };

// Provenance label for a run's producing app version — "v0.75.0", or "" when
// the run predates version tracking (schema < 9) or carries a blank value. Kept
// pure so the History card can show which build made each image without the
// caller re-deriving the "v" prefix / empty-guard each time.
export function formatEngineVersion(v: string | null | undefined): string {
  const s = (v ?? "").trim();
  if (!s) return "";
  return s.startsWith("v") ? s : `v${s}`;
}

// One-line provenance for photometric (multiplicative) frame normalization —
// "Photometrically normalized · N frames gain-matched · scales lo–hi (median m)".
// Returns null when the run wasn't normalized (so the card omits the line). Pure
// so it can be unit-tested and mirrors the inline quality-weighting summary.
export function photometricSummaryText(
  photometric: StackPhotometricSummary | null | undefined,
): string | null {
  if (!photometric) return null;
  let s = "Photometrically normalized";
  if (typeof photometric.n_adjusted === "number") {
    s += ` · ${photometric.n_adjusted} frame${photometric.n_adjusted === 1 ? "" : "s"} gain-matched`;
  }
  if (typeof photometric.min === "number" && typeof photometric.max === "number") {
    s += ` · scales ${photometric.min.toFixed(2)}–${photometric.max.toFixed(2)}`;
  }
  if (typeof photometric.median === "number") {
    s += ` (median ${photometric.median.toFixed(2)})`;
  }
  return s;
}

// One-line provenance for dark exposure-scaling — "Dark scaled to sub exposure ·
// 30s → 10s". Returns null when the run didn't scale its dark (so the card omits
// the line). Pure so it can be unit-tested and mirrors photometricSummaryText.
export function darkScalingSummaryText(
  darkScaling: StackDarkScalingSummary | null | undefined,
): string | null {
  if (!darkScaling) return null;
  let s = "Dark scaled to sub exposure";
  const { dark_exposure: de, light_exposure: le } = darkScaling;
  if (typeof de === "number" && typeof le === "number") {
    s += ` · ${formatExposure(de)} → ${formatExposure(le)}`;
  }
  return s;
}

// One-line provenance for how much the outlier rejection actually removed. A
// trust signal so the user can see the rejection did its job without being told
// "trust me". Mode-aware because the two rejection kinds mean different things:
//
//  * κ-σ ("sigma-clip") — the fraction is *data-driven*: a small share means it
//    removed satellites/planes/cosmic rays without eating real signal, ~0% means
//    the data was already clean, and an unusually large one (≳ 8%) hints a
//    too-tight κ eating signal → "Rejection clipped ~0.4% of samples (…)".
//  * min/max reject ("min-max-reject") — it *always* drops the per-pixel extremes
//    by design, so the fraction is *structural* (≈ 2k / frames): small at high
//    frame counts, large-by-design at low ones. No over-clipping caution — a big
//    number just means a short stack → "Rejection dropped the ~50% most-extreme
//    samples (min/max reject)".
//
// Returns null when the run ran no rejection pass (so the card omits the line).
// Pure so it can be unit-tested and mirrors photometricSummaryText.
export function rejectionSummaryText(
  rejection: StackRejectionSummary | null | undefined,
): string | null {
  if (!rejection) return null;
  const isMinMax = rejection.mode === "min-max-reject";
  const verb = isMinMax ? "dropped the" : "clipped";
  const label = isMinMax ? "min/max reject" : "sigma-clip";
  const frac = rejection.fraction;
  if (typeof frac !== "number" || !Number.isFinite(frac) || frac < 0) {
    return "Outlier rejection applied";
  }
  const pct = frac * 100;
  let pctText: string;
  if (pct === 0) pctText = "0%";
  else if (pct < 0.1) pctText = "<0.1%";
  else if (pct < 10) pctText = `${pct.toFixed(1)}%`;
  else pctText = `${Math.round(pct)}%`;
  const noun = isMinMax ? "most-extreme samples" : "of samples";
  let note: string;
  if (isMinMax) {
    // Structural, by design — never a caution; just name the method.
    note = label;
  } else if (pct === 0) {
    note = "data was already clean";
  } else if (pct < 8) {
    note = "transient outliers";
  } else {
    note = "high — check that κ isn't clipping real signal";
  }
  return `Rejection ${verb} ~${pctText} ${noun} (${note})`;
}

// Plain-language trust note for quality weighting. The stacker already computes
// which subs it down-weighted (soft/hazy/elongated frames pulled below full
// weight), but the raw "7 frames down-weighted · weights 0.31–1.00 (median
// 0.72)" reads as jargon to a beginner. This turns the invisible auto-decision
// into a reassuring sentence — the same "show (and explain) what the autonomy
// did" pattern as the rejection and auto-edit notes — so a non-expert trusts
// that weighting helped (best subs did more) rather than fearing frames were
// thrown away. Pure so it's unit-tested. Returns null when weighting is off.
export function weightingSummaryText(
  weighting: StackWeightingSummary | null | undefined,
  nFrames?: number | null,
): string | null {
  if (!weighting) return null;
  const n = weighting.n_downweighted;
  if (typeof n !== "number" || !Number.isFinite(n) || n <= 0) {
    // Weighting ran but nothing stood out — reassure the subs were consistent.
    return "Quality-weighted — your subs were consistent, so they all counted about equally.";
  }
  const was = n === 1 ? "was" : "were";
  const them = n === 1 ? "it" : "them";
  const count =
    typeof nFrames === "number" && Number.isFinite(nFrames) && nFrames > 0
      ? `of your ${nFrames.toLocaleString()} subs, ${n.toLocaleString()} ${was}`
      : `${n.toLocaleString()} ${n === 1 ? "sub" : "subs"} ${was}`;
  return (
    `Quality-weighted — ${count} softer or hazier than the rest, so the ` +
    `stacker trusted ${them} a little less (not dropped — just weighted down). ` +
    `Your best subs did the heavy lifting.`
  );
}

export interface FrameAccountingNote {
  // The honest one-liner: "1,850 of 2,000 subs combined · 150 couldn't be aligned".
  text: string;
  // True when the align-failure share is large enough that it's probably a real
  // problem worth guiding a fix for (mixed targets / bad plate-solves), not just
  // the odd unreadable sub. Drives the amber colour + guidance line.
  concern: boolean;
  // Actionable next step, present only when `concern` — mirrors the guidance the
  // stacker's own mosaic-canvas error already gives for wildly-off frames.
  guidance: string | null;
}

// One-line honest frame accounting for a finished stack — how many of the subs
// the stacker *tried* to combine actually made it in, and (when it's a lot) a
// nudge toward the likely cause. For the target user (thousands of subs, walks
// away) a silent "150 of your 2,000 subs couldn't be aligned" is a real trust
// hole: a large align-failure fraction usually means two targets' frames landed
// in one folder, or a cluster of frames plate-solved to the wrong place.
//
// Returns null when nothing's worth saying — no accounting recorded (older
// master), or every attempted sub aligned (the "· N subs" integration line
// already tells that happy story). Pure so it can be unit-tested.
export function frameAccountingNote(
  fa: StackFrameAccounting | null | undefined,
): FrameAccountingNote | null {
  if (!fa || typeof fa.n_offered !== "number" || fa.n_offered <= 0) return null;
  const offered = fa.n_offered;
  const failed = typeof fa.n_align_failed === "number" && fa.n_align_failed > 0
    ? Math.min(fa.n_align_failed, offered)
    : 0;
  if (failed <= 0) return null;
  const used = offered - failed;
  const nf = (n: number) => n.toLocaleString();
  const text =
    `${nf(used)} of ${nf(offered)} subs combined · ` +
    `${nf(failed)} couldn't be aligned`;
  // Guide a fix only when it's a materially large share and not a tiny stack
  // (one dud sub out of five is 20% but not worth a scary nudge).
  const fraction = failed / offered;
  const concern = offered >= 10 && fraction >= 0.2;
  const guidance = concern
    ? "Many subs didn't line up to the reference — this usually means two " +
      "targets' frames are in one folder, or some plate-solved to the wrong " +
      "place. Open the Frames table, sort by RA/Dec, and reject or re-solve the " +
      "ones whose centre is far from the rest."
    : null;
  return { text, concern, guidance };
}

// Compact seconds label for exposures — "30s", "2.5s" — trimming a trailing ".0".
function formatExposure(s: number): string {
  const r = Math.round(s * 10) / 10;
  return `${Number.isInteger(r) ? r.toFixed(0) : r.toFixed(1)}s`;
}

function StackInfoPanel({ safe, runId }: { safe: string; runId: number }) {
  const info = useQuery({
    queryKey: ["stack-info", safe, runId],
    queryFn: () => api.stackRunInfo(safe, runId),
  });
  if (info.isLoading) return <Center h={60}><Loader size="sm" /></Center>;
  if (info.isError) {
    return <Text size="xs" c="dimmed">Could not read FITS header.</Text>;
  }
  const data = info.data!;
  if (data.cards.length === 0) {
    return <Text size="xs" c="dimmed">No provenance recorded in this stack's FITS.</Text>;
  }
  return (
    <Stack gap={4} mt="xs">
      {data.integration_s ? (
        <Text size="xs" fw={600}>
          Integration: {formatIntegration(data.integration_s)}
          {data.n_frames ? ` · ${data.n_frames} subs` : ""}
        </Text>
      ) : null}
      {data.auto_edit ? (
        <Text size="xs" c="dimmed">
          {data.auto_edit}
        </Text>
      ) : null}
      {(() => {
        const cc = autoColorCalCaption(data.color_cal);
        if (!cc) return null;
        return (
          <Text size="xs" c={cc.neutral ? "teal.6" : "dimmed"}>
            {cc.text}
          </Text>
        );
      })()}
      {(() => {
        const sc = autoSkyCastCaption({ sky_cast: data.sky_cast });
        if (!sc) return null;
        return (
          <Text size="xs" c={sc.neutral ? "teal.6" : "dimmed"}>
            {sc.text}
          </Text>
        );
      })()}
      {(() => {
        const cal = calibrationSummaryText(data.cards, data.calibration_advice);
        if (!cal) return null;
        return (
          <Text size="xs" c="dimmed">
            {cal.text}
          </Text>
        );
      })()}
      {weightingSummaryText(data.weighting, data.n_frames) ? (
        <Text size="xs" c="dimmed">
          {weightingSummaryText(data.weighting, data.n_frames)}
        </Text>
      ) : null}
      {photometricSummaryText(data.photometric) ? (
        <Text size="xs" c="dimmed">
          {photometricSummaryText(data.photometric)}
        </Text>
      ) : null}
      {darkScalingSummaryText(data.dark_scaling) ? (
        <Text size="xs" c="dimmed">
          {darkScalingSummaryText(data.dark_scaling)}
        </Text>
      ) : null}
      {rejectionSummaryText(data.rejection) ? (
        <Text size="xs" c="dimmed">
          {rejectionSummaryText(data.rejection)}
        </Text>
      ) : null}
      {(() => {
        const fa = frameAccountingNote(data.frame_accounting);
        if (!fa) return null;
        return (
          <Stack gap={2}>
            <Text size="xs" c={fa.concern ? "yellow.7" : "dimmed"} fw={fa.concern ? 600 : undefined}>
              {fa.text}
            </Text>
            {fa.guidance ? (
              <Text size="xs" c="dimmed">{fa.guidance}</Text>
            ) : null}
          </Stack>
        );
      })()}
      {combineMethodLabel(data.cards) ? (
        <Text size="xs" c="dimmed">
          Combined: {combineMethodLabel(data.cards)}
        </Text>
      ) : null}
      {data.processing && data.processing.length > 0 ? (
        <Text size="xs" c="dimmed">
          Processing: {data.processing.map((s) => s.label).join(" → ")}
        </Text>
      ) : null}
      <Table verticalSpacing={2} horizontalSpacing="xs" fz="xs" withRowBorders={false}>
        <Table.Tbody>
          {data.cards.map((c) => (
            <Table.Tr key={c.key}>
              <Table.Td c="dimmed" style={{ whiteSpace: "nowrap" }}>{c.key}</Table.Td>
              <Table.Td>{String(c.value)}</Table.Td>
            </Table.Tr>
          ))}
        </Table.Tbody>
      </Table>
    </Stack>
  );
}

// Inline, editable free-text label for a run ("best RGB v2", "cloudy night").
// Persisted via PATCH; reuses the long-standing notes column.
function NotesEditor({ safe, run }: { safe: string; run: StackRun }) {
  const qc = useQueryClient();
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(run.notes ?? "");

  const save = useMutation({
    mutationFn: (notes: string) => api.updateStackRunNotes(safe, run.id, notes),
    onSuccess: () => {
      setEditing(false);
      qc.invalidateQueries({ queryKey: ["runs", safe] });
    },
    onError: (e: Error) => notifications.show({ message: e.message, color: "red" }),
  });

  if (editing) {
    return (
      <Group gap={4} mt={4} wrap="nowrap">
        <TextInput
          size="xs" style={{ flex: 1 }} value={draft} maxLength={500} autoFocus
          placeholder="Label this stack (e.g. best RGB v2)"
          aria-label="Stack note"
          onChange={(e) => setDraft(e.currentTarget.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") save.mutate(draft);
            if (e.key === "Escape") { setDraft(run.notes ?? ""); setEditing(false); }
          }}
        />
        <ActionIcon size="sm" color="teal" variant="light" aria-label="Save note"
          loading={save.isPending} onClick={() => save.mutate(draft)}>
          <IconCheck size={14} />
        </ActionIcon>
        <ActionIcon size="sm" variant="subtle" aria-label="Cancel note"
          onClick={() => { setDraft(run.notes ?? ""); setEditing(false); }}>
          <IconX size={14} />
        </ActionIcon>
      </Group>
    );
  }
  return (
    <Group gap={4} mt={4} wrap="nowrap">
      {run.notes ? (
        <Text size="xs" c="dimmed" style={{ flex: 1 }} truncate>“{run.notes}”</Text>
      ) : (
        <Text size="xs" c="dimmed" fs="italic" style={{ flex: 1 }}>No label</Text>
      )}
      <Tooltip label={run.notes ? "Edit label" : "Add a label"}>
        <ActionIcon size="sm" variant="subtle" aria-label="Edit note"
          onClick={() => { setDraft(run.notes ?? ""); setEditing(true); }}>
          <IconPencil size={14} />
        </ActionIcon>
      </Tooltip>
    </Group>
  );
}

// Asinh stretch controls, both 0..1 (see seestack asinh_stretch). "Stretch"
// lifts faint nebulosity; "Black point" cleans the sky background. Users push
// Stretch up to reveal detail the baked 8-bit preview clipped.
const DEFAULT_STRETCH = 0.5;
const DEFAULT_BLACK = 0.35;

function RunCard({ safe, run, onDelete, deleting, isCleanest, noiseDelta, compareToId }: {
  safe: string; run: StackRun; onDelete: () => void; deleting?: boolean;
  isCleanest?: boolean; noiseDelta?: number; compareToId?: number | null;
}) {
  const qc = useQueryClient();
  const [adjust, setAdjust] = useState(false);
  const [showInfo, setShowInfo] = useState(false);
  const [northUp, setNorthUp] = useState(false);
  const [nameplate, setNameplate] = useState(false);
  const [stretch, setStretch] = useState(DEFAULT_STRETCH);
  const [black, setBlack] = useState(DEFAULT_BLACK);
  const [cacheBust, setCacheBust] = useState(0);
  const [light, setLight] = useState(false);
  // "What's in this picture?" — lazily fetch the catalog objects in this run's
  // field only once the user asks (needs the FITS-header WCS, so gated on has_fits).
  const [identify, setIdentify] = useState(false);
  const annotations = useQuery({
    queryKey: ["annotations", safe, run.id],
    queryFn: () => api.stackAnnotations(safe, run.id),
    enabled: identify && run.has_fits,
    staleTime: Infinity,
  });
  const objects = annotations.data?.objects ?? [];
  const [dStretch] = useDebouncedValue(stretch, 250);
  const [dBlack] = useDebouncedValue(black, 250);
  // Suggest the initial asinh sliders from the run's own data (fetched lazily
  // once Adjust is opened) so the first adjustable render matches the STF preview
  // thumbnail instead of jumping to a fixed 0.5/0.35. Falls back to the fixed
  // defaults when there's no useful suggestion or on an older/display-space run.
  const suggestion = useQuery({
    queryKey: ["render-suggestion", safe, run.id],
    queryFn: () => api.stackRenderSuggestion(safe, run.id),
    enabled: adjust && run.has_fits,
    staleTime: Infinity,
  });
  const sugStretch = suggestion.data?.stretch;
  const sugBlack = suggestion.data?.black;
  // "North up" is offered only when the run's WCS yields a real orientation
  // correction (the endpoint returns null otherwise); apply it only while it's
  // both available and toggled on.
  const northUpDeg = suggestion.data?.north_up_deg;
  const canNorthUp = typeof northUpDeg === "number";
  const applyNorthUp = northUp && canNorthUp;
  const defStretch = typeof sugStretch === "number" ? sugStretch : DEFAULT_STRETCH;
  const defBlack = typeof sugBlack === "number" ? sugBlack : DEFAULT_BLACK;
  // Apply the suggestion the first time it arrives, but only while the user
  // hasn't touched the sliders yet (so it never yanks a value out from under them).
  const touched = useRef(false);
  useEffect(() => {
    if (!touched.current && (typeof sugStretch === "number" || typeof sugBlack === "number")) {
      if (typeof sugStretch === "number") setStretch(sugStretch);
      if (typeof sugBlack === "number") setBlack(sugBlack);
    }
  }, [sugStretch, sugBlack]);

  const save = useMutation({
    mutationFn: () => api.saveStackPreview(safe, run.id, dStretch, dBlack),
    onSuccess: () => {
      setCacheBust(Date.now());
      qc.invalidateQueries({ queryKey: ["sky"] });
      qc.invalidateQueries({ queryKey: ["gallery"] });
      notifications.show({ message: "Preview updated", color: "teal" });
    },
    onError: () => notifications.show({ message: "Could not save preview", color: "red" }),
  });

  // Pin this run as the target's showcase "cover" — the picture the Library /
  // Dashboard tile shows — or clear it back to the newest stack.
  const cover = useMutation({
    mutationFn: (pin: boolean) => api.setTargetCover(safe, pin ? run.id : null),
    onSuccess: (_data, pin) => {
      qc.invalidateQueries({ queryKey: ["runs", safe] });
      qc.invalidateQueries({ queryKey: ["targets"] });
      qc.invalidateQueries({ queryKey: ["target", safe] });
      notifications.show({
        message: pin ? "Set as the target's cover" : "Cover cleared — showing the newest stack",
        color: "teal",
      });
    },
    onError: () => notifications.show({ message: "Could not update cover", color: "red" }),
  });

  const previewSrc = `${api.stackArtifactUrl(safe, run.id, "preview")}${cacheBust ? `?v=${cacheBust}` : ""}`;
  // While the first suggestion fetch is still in flight, keep showing the STF
  // preview thumbnail rather than briefly rendering at the fixed defaults and
  // then jumping to the anchored sliders.
  const imgSrc = adjust && run.has_fits && !suggestion.isLoading
    ? api.stackRenderUrl(safe, run.id, dStretch, dBlack, applyNorthUp)
    : previewSrc;

  return (
    <Card withBorder padding="md" radius="md">
      <Card.Section>
        {run.has_preview || (adjust && run.has_fits) ? (
          <AnnotatedImage
            src={imgSrc} alt={run.output_basename}
            imgWidth={annotations.data?.width ?? run.canvas_w}
            imgHeight={annotations.data?.height ?? run.canvas_h}
            objects={objects} show={identify} height={180}
            onClick={() => setLight(true)}
          />
        ) : (
          <Center h={180} bg="dark.6"><Text c="dimmed">No preview</Text></Center>
        )}
      </Card.Section>

      {identify && !annotations.isLoading && annotations.isSuccess ? (
        <Text size="xs" c={objects.length ? "cyan.4" : "dimmed"} mt={6}>
          {objects.length
            ? `Found ${objects.length} catalog object${objects.length === 1 ? "" : "s"} in this field`
            : "No catalog objects fall inside this field"}
        </Text>
      ) : null}

      <Group justify="space-between" mt="sm" wrap="nowrap">
        <Text fw={600}>{run.output_basename}</Text>
        <Group gap={4} wrap="nowrap">
          <CleanestBadge isCleanest={!!isCleanest} />
          <RejectionBadge options={run.options} />
          <HazyNightBadge ratio={run.transparency_ratio} />
          <CalibrationBadge calstat={run.calstat} />
          <Badge variant="light">{run.n_frames_used} frames</Badge>
        </Group>
      </Group>
      <Text size="xs" c="dimmed">
        {run.timestamp_utc.replace("T", " ").slice(0, 19)} · {run.canvas_w}×{run.canvas_h}
        {run.total_exposure_s ? ` · ${formatIntegration(run.total_exposure_s)}` : ""}
        {hasNoise(run.noise_sigma) ? <> · <NoiseReadout sigma={run.noise_sigma} /></> : null}
        {formatEngineVersion(run.engine_version) ? ` · ${formatEngineVersion(run.engine_version)}` : ""}
      </Text>
      {typeof noiseDelta === "number" ? (
        <Text size="xs"><NoiseDelta delta={noiseDelta} /></Text>
      ) : null}
      <NotesEditor safe={safe} run={run} />

      {adjust && run.has_fits ? (
        <Stack gap={6} mt="sm">
          <div>
            <Group justify="space-between" gap={4}>
              <Text size="xs">Stretch (asinh)</Text>
              <Text size="xs" c="dimmed">{stretch.toFixed(2)}</Text>
            </Group>
            <Slider
              min={0} max={1} step={0.01} value={stretch}
              onChange={(v) => { touched.current = true; setStretch(v); }}
              label={(v) => v.toFixed(2)} size="sm"
            />
          </div>
          <div>
            <Group justify="space-between" gap={4}>
              <Text size="xs">Black point</Text>
              <Text size="xs" c="dimmed">{black.toFixed(2)}</Text>
            </Group>
            <Slider
              min={0} max={1} step={0.01} value={black}
              onChange={(v) => { touched.current = true; setBlack(v); }}
              label={(v) => v.toFixed(2)} size="sm"
            />
          </div>
          {canNorthUp ? (
            <Switch
              size="sm" checked={northUp} onChange={(e) => setNorthUp(e.currentTarget.checked)}
              label="Rotate so North is up"
              description="Orient the picture — and the JPEG you download or share — like reference photos of this object."
            />
          ) : null}
          <Switch
            size="sm" checked={nameplate} onChange={(e) => setNameplate(e.currentTarget.checked)}
            label="Add a caption to the JPEG"
            description="Bake the acquisition data (target, integration, date, gear) into the JPEG you download or share."
          />
          <Group gap="xs" mt={4}>
            <Button
              size="xs" leftSection={<IconDeviceFloppy size={14} />}
              loading={save.isPending} onClick={() => save.mutate()}
            >
              Save as preview
            </Button>
            <Button
              size="xs" variant="subtle"
              onClick={() => { touched.current = false; setStretch(defStretch); setBlack(defBlack); }}
            >
              Reset
            </Button>
          </Group>
        </Stack>
      ) : null}

      <Group mt="sm" justify="space-between">
        <Group gap="xs">
          {run.has_fits && (
            <Button
              size="xs" variant="light" color="grape" leftSection={<IconSparkles size={14} />}
              component={Link} to={`/targets/${safe}/edit/${run.id}`}
            >
              Edit
            </Button>
          )}
          {run.reusable && (
            <Tooltip label="Pre-fill the Stack form with the exact settings used for this run">
              <Button
                size="xs" variant="light" leftSection={<IconCopy size={14} />}
                component={Link} to={`/targets/${safe}/stack?from=${run.id}`}
              >
                Reuse settings
              </Button>
            </Tooltip>
          )}
          {typeof compareToId === "number" && (
            <Tooltip label="Compare this stack side-by-side with your previous run of this target">
              <Button
                size="xs" variant="light" color="grape" leftSection={<IconGitCompare size={14} />}
                component={Link} to={historyCompareHref(safe, run.id, compareToId)}
              >
                Compare
              </Button>
            </Tooltip>
          )}
          {run.has_fits && (
            <Tooltip label="Adjust stretch / black point from the full-range FITS">
              <Button
                size="xs" variant={adjust ? "filled" : "light"}
                leftSection={<IconAdjustments size={14} />}
                onClick={() => setAdjust((a) => !a)}
              >
                Adjust
              </Button>
            </Tooltip>
          )}
          {run.has_fits && (
            <Tooltip label="Show how this stack was made (from the FITS header)">
              <Button
                size="xs" variant={showInfo ? "filled" : "light"}
                leftSection={<IconInfoCircle size={14} />}
                onClick={() => setShowInfo((s) => !s)}
              >
                Info
              </Button>
            </Tooltip>
          )}
          {run.has_fits && (
            <Tooltip label="Label the catalog objects that fall inside this picture (Messier / NGC / IC)">
              <Button
                size="xs" variant={identify ? "filled" : "light"} color="cyan"
                leftSection={<IconTags size={14} />}
                onClick={() => setIdentify((v) => !v)}
                loading={identify && annotations.isLoading}
              >
                Identify
              </Button>
            </Tooltip>
          )}
          {run.has_preview && (
            <Tooltip label={run.is_cover
              ? "This is the target's cover — show the newest stack instead"
              : "Make this picture the target's cover (shown on the Library tile)"}>
              <Button
                size="xs" variant={run.is_cover ? "filled" : "light"} color="yellow"
                leftSection={run.is_cover ? <IconStarFilled size={14} /> : <IconStar size={14} />}
                loading={cover.isPending}
                onClick={() => cover.mutate(!run.is_cover)}
              >
                {run.is_cover ? "Cover" : "Set as cover"}
              </Button>
            </Tooltip>
          )}
          {run.has_preview && (
            <Tooltip label="Download the finished picture as a PNG (best quality)">
              <Button
                size="xs" variant="light" leftSection={<IconPhotoDown size={14} />}
                component="a" href={api.stackArtifactUrl(safe, run.id, "preview")}
              >
                PNG
              </Button>
            </Tooltip>
          )}
          {run.has_preview && (
            <Tooltip label={applyNorthUp
              ? "Download a JPEG oriented so North is up (smaller — best for sharing)"
              : "Download the finished picture as a JPEG (smaller — best for sharing)"}>
              <Button
                size="xs" variant="light" leftSection={<IconPhotoDown size={14} />}
                component="a" href={api.stackArtifactUrl(safe, run.id, "jpeg", applyNorthUp, nameplate)}
              >
                JPEG
              </Button>
            </Tooltip>
          )}
          {run.has_preview && (
            <SharePictureButton
              url={api.stackArtifactUrl(safe, run.id, "jpeg", applyNorthUp, nameplate)}
              {...sharePictureText(
                run.output_basename,
                new Date(run.timestamp_utc).toLocaleDateString(),
              )}
            />
          )}
          {run.has_preview && <WallpaperMenu safe={safe} runId={run.id} />}
          {run.has_fits && (
            <Tooltip label="Download the raw scientific data (FITS) — for re-processing, not sharing">
              <Button
                size="xs" variant="light" leftSection={<IconDownload size={14} />}
                component="a" href={api.stackArtifactUrl(safe, run.id, "fits")}
              >
                FITS
              </Button>
            </Tooltip>
          )}
          {run.has_tiff && (
            <Button
              size="xs" variant="light" leftSection={<IconDownload size={14} />}
              component="a" href={api.stackArtifactUrl(safe, run.id, "tiff")}
            >
              TIFF
            </Button>
          )}
        </Group>
        <Tooltip label="Delete this stack run">
          <ActionIcon variant="subtle" color="red" loading={deleting} aria-label="Delete stack"
            onClick={() => {
              if (window.confirm(
                `Delete "${run.output_basename}" permanently? Its FITS/TIFF/preview will be removed.`)) {
                onDelete();
              }
            }}>
            <IconTrash size={16} />
          </ActionIcon>
        </Tooltip>
      </Group>

      {showInfo && run.has_fits ? (
        <>
          <StackInfoPanel safe={safe} runId={run.id} />
          {/* "How's my stack?" for *this* run — self-hides for non-genuine
              (editor/combine) runs the endpoint declines to grade. */}
          <StackHealthCard safe={safe} runId={run.id} />
        </>
      ) : null}

      {/* "Watch your picture appear" reel — self-hides unless this run was
          stacked with save_progress on (the opt-in default-off extra). */}
      {run.has_fits ? <ProgressReelCard safe={safe} runId={run.id} /> : null}

      {/* "One frame vs your stack" reveal — self-hides unless this run has a
          preview to compare against and a frame to render. */}
      {run.has_preview ? <OneFrameVsStackCard safe={safe} runId={run.id} /> : null}

      <ImageLightbox
        src={light
          ? (adjust && run.has_fits
              ? `${api.stackRenderUrl(safe, run.id, dStretch, dBlack, applyNorthUp)}&size=2048`
              : previewSrc)
          : null}
        title={run.output_basename}
        downloadHref={run.has_preview ? api.stackArtifactUrl(safe, run.id, "preview") : undefined}
        jpegHref={run.has_preview ? api.stackArtifactUrl(safe, run.id, "jpeg", applyNorthUp, nameplate) : undefined}
        rawHref={run.has_fits ? api.stackArtifactUrl(safe, run.id, "fits") : undefined}
        {...(run.has_preview
          ? (() => {
              const { title, text, filename } = sharePictureText(
                run.output_basename,
                new Date(run.timestamp_utc).toLocaleDateString(),
              );
              return { shareFilename: filename, shareTitle: title, shareText: text };
            })()
          : {})}
        onClose={() => setLight(false)}
      />
    </Card>
  );
}

export function HistoryView() {
  const { safe = "" } = useParams();
  const qc = useQueryClient();
  const [sort, setSort] = useState<RunSort>("newest");
  const runs = useQuery({ queryKey: ["runs", safe], queryFn: () => api.listStackRuns(safe) });

  const del = useMutation({
    mutationFn: (id: number) => api.deleteStackRun(safe, id),
    onSuccess: () => {
      notifications.show({ message: "Stack deleted", color: "teal" });
      // A deleted run also vanishes from the Gallery, Sky map and Dashboard.
      qc.invalidateQueries({ queryKey: ["runs", safe] });
      qc.invalidateQueries({ queryKey: ["gallery"] });
      qc.invalidateQueries({ queryKey: ["sky"] });
      qc.invalidateQueries({ queryKey: ["stats"] });
    },
    onError: (e: Error) => notifications.show({ message: e.message, color: "red" }),
  });

  if (runs.isLoading) {
    return <Center h={300}><Loader /></Center>;
  }
  if (runs.isError) {
    return <Alert color="red" m="md" title="Could not load stacks">{(runs.error as Error)?.message}</Alert>;
  }

  const list = runs.data ?? [];
  const cleanestId = cleanestRunId(list);
  const anyNoise = list.some((r) => hasNoise(r.noise_sigma));
  const deltas = noiseDeltas(list);
  const sorted = sortRuns(list, sort);
  const trend = noiseTrendSeries(list);

  return (
    <Stack>
      <Group justify="space-between">
        <Title order={2}>Stack history — {safe}</Title>
        <Group gap="sm">
          {list.length > 1 && anyNoise ? (
            <SegmentedControl
              size="xs"
              value={sort}
              onChange={(v) => setSort(v as RunSort)}
              data={[
                { label: "Newest", value: "newest" },
                { label: "Cleanest", value: "cleanest" },
              ]}
              aria-label="Sort stacks"
            />
          ) : null}
          <Button component={Link} to={`/targets/${safe}/stack`}>New stack</Button>
        </Group>
      </Group>
      {trend.length >= 2 ? (
        <Card withBorder padding="sm" radius="md">
          <Group justify="space-between" wrap="nowrap" gap="md">
            <div>
              <Group gap={6}>
                <Text size="sm" fw={600}>Noise trend</Text>
                <Tooltip
                  label="Background-noise σ of each measured stack, oldest → newest. Lower is cleaner; a downward line means your results are improving as you add nights."
                  multiline w={260} withArrow>
                  <Text span size="xs" c="dimmed" style={{ cursor: "help" }}
                    td="underline dotted">what's this?</Text>
                </Tooltip>
              </Group>
              <Text size="xs" c="dimmed">
                {trend[trend.length - 1] < trend[0]
                  ? `Cleaner than your first measured stack (σ ${trend[trend.length - 1].toFixed(3)} vs ${trend[0].toFixed(3)}).`
                  : trend[trend.length - 1] > trend[0]
                    ? `Noisier than your first measured stack (σ ${trend[trend.length - 1].toFixed(3)} vs ${trend[0].toFixed(3)}).`
                    : `Steady around σ ${trend[0].toFixed(3)}.`}
              </Text>
            </div>
            <Sparkline
              values={trend}
              color={trend[trend.length - 1] <= trend[0]
                ? "var(--mantine-color-teal-5)" : "var(--mantine-color-orange-5)"}
              aria-label={`Noise trend across ${trend.length} measured stacks`}
            />
          </Group>
        </Card>
      ) : null}
      {list.length === 0 ? (
        <Card withBorder padding="xl">
          <Stack align="center" gap="sm">
            <Text c="dimmed">No stacks yet for this target.</Text>
            <Button component={Link} to={`/targets/${safe}/stack`}>Stack it now</Button>
          </Stack>
        </Card>
      ) : (
        <SimpleGrid cols={{ base: 1, sm: 2, md: 3 }}>
          {sorted.map((r) => (
            <RunCard key={r.id} safe={safe} run={r}
              onDelete={() => del.mutate(r.id)}
              deleting={del.isPending && del.variables === r.id}
              isCleanest={r.id === cleanestId}
              noiseDelta={deltas.get(r.id)}
              compareToId={previousRunId(list, r.id)} />
          ))}
        </SimpleGrid>
      )}
    </Stack>
  );
}
