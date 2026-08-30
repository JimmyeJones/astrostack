import { useEffect, useRef, useState } from "react";
import type { CSSProperties } from "react";
import {
  ActionIcon, Alert, Badge, Button, Card, Center, Group, Loader, Menu, SegmentedControl,
  SimpleGrid, Slider, Stack, Switch, Table, Text, TextInput, Title, Tooltip,
} from "@mantine/core";
import { useDebouncedValue } from "@mantine/hooks";
import { notifications } from "@mantine/notifications";
import { IconAdjustments, IconCheck, IconChevronDown, IconClipboardText, IconCopy, IconDeviceFloppy, IconDeviceMobile, IconDownload, IconGitCompare, IconInfoCircle, IconPencil, IconPhotoDown, IconRuler2, IconSparkles, IconStar, IconStarFilled, IconTags, IconTrash, IconVideo, IconX } from "@tabler/icons-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import { api, type StackRun, type ObjectInfo, type StackPhotometricSummary, type StackDarkScalingSummary, type StackRejectionSummary, type StackWeightingSummary, type StackWeightingSkipped, type StackFrameAccounting, type StackDrizzleDegraded } from "../api/client";
import { formatIntegration, formatStampDate } from "../format";
import { postCaption, formatCaptionDate } from "../components/postCaption";
import { HazyNightBadge } from "../components/HazyNightBadge";
import { PanelSeamsBadge } from "../components/PanelSeamsBadge";
import { CalibrationBadge } from "../components/CalibrationBadge";
import { UnexportedEditBadge } from "../components/UnexportedEditBadge";
import { calibrationSummaryText } from "../components/calibrationSummary";
import { autoSkyCastCaption } from "../components/editor/skyCast";
import { autoColorCalCaption } from "../components/editor/colorCal";
import { RejectionBadge } from "../components/RejectionBadge";
import { FocusChip } from "../components/target/FocusChip";
import { FramingVerdictNote } from "../components/target/FramingVerdictNote";
import { focusChips, type FocusVerdict } from "../components/target/focusChips";
import { integrationTrend } from "../components/target/integrationTrend";
import { NoiseReadout, NoiseDelta, CleanestBadge, cleanestRunId, hasNoise } from "../components/NoiseBadge";
import { ImageLightbox } from "../components/ImageLightbox";
import { AnnotatedImage, croppedAnnotationView } from "../components/AnnotatedImage";
import { describeFieldObjects } from "../components/fieldObjectList";
import { StackHealthCard } from "../components/StackHealthCard";
import { ProgressReelCard } from "../components/ProgressReelCard";
import { OneFrameVsStackCard } from "../components/OneFrameVsStackCard";
import { SharePictureButton } from "../components/SharePictureButton";
import { ScanToPhoneModal } from "../components/ScanToPhoneButton";
import { SampleTourNote } from "../components/SampleTourNote";
import { WallpaperMenuItems } from "../components/WallpaperMenu";
import { sharePictureText } from "../share";
import { fullResPngHint } from "../fullres";
import { removedOverlayCaption } from "../removed";
import { tiffDownloadHint } from "../tiffDownload";
import { Sparkline } from "../components/Sparkline";
import { DownloadMenuItem } from "../components/DownloadMenuItem";

export type RunSort = "newest" | "cleanest";

// The one-line "what this does" under a menu item's name — the wording that used
// to live in each button's hover tooltip, now readable without hovering (which a
// phone can't do anyway).
const MENU_HINT: CSSProperties = {
  display: "block", fontSize: "0.72rem", opacity: 0.6, whiteSpace: "normal",
};

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
  // Each panel is matched against its own subs, never against the others — say
  // so, since "gain-matched" on a mosaic otherwise sounds like the panels were
  // brightened to match each other, which is exactly what it must not do.
  if (typeof photometric.n_panels === "number" && photometric.n_panels > 1) {
    s += ` · each of ${photometric.n_panels} panels matched against its own subs`;
  }
  // Say who asked for it. A mosaic gets gain-matching automatically (panels are
  // shot through different air), so on those runs the user never chose it and
  // would otherwise wonder where the line came from.
  if (photometric.auto) {
    s += " · automatic for a mosaic";
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

// The "what was removed" caption now lives in `removed.ts`, because the tint is
// no longer only on this card — the full-screen viewer on the Gallery and the
// Target page show it too, and one picture must not be described two ways.
// Re-exported here so the surfaces (and tests) that have always read it from
// History keep working.
export { removedOverlayCaption };

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

/** Why a quality-weighted run's weighting didn't count.
 *
 * The engine stamps this only when weighting was on *and* the min/max
 * order-statistic path ran — it combines by rank, so per-frame weights have no
 * effect. On the walk-away chains (watcher auto-stack, one-click Process
 * target) the user never sees the Stack form's pick-time warning, so without
 * this line "weighting did nothing" looks exactly like "weighting was off".
 * The advice differs by how min/max got picked: an automatic pick fixes itself
 * with more subs, a manual tick needs the setting changed.
 */
export function weightingSkippedText(
  skipped: StackWeightingSkipped | null | undefined,
  nFrames?: number | null,
): string | null {
  if (!skipped) return null;
  const n =
    typeof nFrames === "number" && Number.isFinite(nFrames) && nFrames > 0 ? nFrames : null;
  const withCount = n ? ` with ${n.toLocaleString()} ${n === 1 ? "sub" : "subs"}` : "";
  const lead =
    `Quality weighting was on, but this stack${withCount} used min/max rejection, ` +
    `which combines by rank instead of by weight — so the weighting didn't change the result.`;
  const min = skipped.min_frames;
  if (skipped.auto && typeof min === "number" && Number.isFinite(min) && min > 0) {
    return (
      `${lead} That method was picked automatically because sigma clipping can't ` +
      `remove a lone satellite trail on a small stack; from ${min.toLocaleString()} subs ` +
      `it switches to sigma clipping and your weighting counts again.`
    );
  }
  if (skipped.auto) {
    return `${lead} It was picked automatically for a stack this small; with more subs, weighting counts again.`;
  }
  return `${lead} Use sigma clipping instead if you want your best subs to count for more.`;
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
// "Why is last night's picture a different size?" — the one thing an unattended
// run can change about the *shape* of the result without anyone watching.
//
// When a walk-away stack's drizzle canvas won't fit the memory budget, the engine
// now lowers the super-resolution scale to the largest one that does, rather than
// refusing outright with advice nobody is there to read (that refusal is still
// what a *watching* user gets — they can click the fix). The trade is real but
// small: the picture is slightly less zoomed-in and nothing else about it
// changes. Since the decision was made at 3 a.m., this line is the only place the
// owner can find out it happened, so it says what was asked for, what was used,
// and — crucially — that no data was lost.
//
// Returns null on every run that fitted (all of them on a healthy box) and on
// older masters that predate the cards. Pure so it can be unit-tested.
export function drizzleDegradedNote(
  dd: StackDrizzleDegraded | null | undefined,
): string | null {
  if (!dd) return null;
  const applied = dd.applied;
  if (typeof applied !== "number" || !Number.isFinite(applied) || applied <= 0) {
    return null;
  }
  const fmt = (n: number) => `×${Number(n.toFixed(2))}`;
  const requested = dd.requested;
  const asked =
    typeof requested === "number" && Number.isFinite(requested) && requested > applied
      ? ` instead of the ${fmt(requested)} it was set to`
      : "";
  return (
    `Super-resolution used ${fmt(applied)}${asked} — the bigger canvas didn't fit ` +
    `in memory, so AstroStack made the picture at this size rather than skipping ` +
    `the night. It's slightly less zoomed-in; none of your subs were left out.`
  );
}

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
  // Split the gap into the two causes that need *different* fixes. A sub whose
  // file simply wasn't on disk (cleared Stage-1 cache while the originals sit on
  // an offline share, an unmounted drive, moved files) is a storage problem —
  // sending that user to re-solve frames or hunt for mixed targets wastes their
  // evening. Absent on older masters → 0, so those read exactly as before.
  const unreadable = typeof fa.n_unreadable === "number" && fa.n_unreadable > 0
    ? Math.min(fa.n_unreadable, failed)
    : 0;
  const unaligned = failed - unreadable;
  const causes: string[] = [];
  if (unreadable > 0) causes.push(`${nf(unreadable)} couldn't be read`);
  if (unaligned > 0) causes.push(`${nf(unaligned)} couldn't be aligned`);
  const text = `${nf(used)} of ${nf(offered)} subs combined · ${causes.join(" · ")}`;
  // Guide a fix only when it's a materially large share and not a tiny stack
  // (one dud sub out of five is 20% but not worth a scary nudge).
  const missingConcern = offered >= 10 && unreadable / offered >= 0.05;
  const alignConcern = offered >= 10 && unaligned / offered >= 0.2;
  // When both fired, guide toward whichever explains more of the loss.
  const guidance = missingConcern && unreadable >= unaligned
    ? "Those subs' files weren't there when the stack ran — most often the " +
      "Stage-1 cache was cleared while the originals live on a drive or network " +
      "share that's offline. Reconnect the drive (or re-copy the files), scan " +
      "again, then re-stack to get them back."
    : alignConcern
      ? "Many subs didn't line up to the reference — this usually means two " +
        "targets' frames are in one folder, or some plate-solved to the wrong " +
        "place. Open the Frames table, sort by RA/Dec, and reject or re-solve the " +
        "ones whose centre is far from the rest."
      : null;
  return { text, concern: guidance !== null, guidance };
}

// The storage signal `frameAccountingNote` can't carry: subs whose file *was*
// on disk and then failed mid-read (a flaking network share, a bad sector, a
// half-written file). The engine has always recorded one raw string per failed
// read in the run's `errors` list — a list no screen has ever displayed — so a
// night of dropped reads reached the owner only as an unexplained thin stack.
//
// It sits next to the missing-files clause deliberately: both are "check the
// drive", and reading them as one story is what turns two mysteries into one
// fix. The recovered count is the reassuring half — a sub that blipped on one
// pass and read fine on the other IS in the picture, so the note must not imply
// a lost night when nothing was lost.
//
// Returns null when nothing errored, or on a master stacked before the counts
// were recorded (the cards are absent → the field is undefined).
export function readErrorNote(
  fa: StackFrameAccounting | null | undefined,
): FrameAccountingNote | null {
  if (!fa || typeof fa.n_offered !== "number" || fa.n_offered <= 0) return null;
  if (typeof fa.n_read_errors !== "number" || fa.n_read_errors <= 0) return null;
  const offered = fa.n_offered;
  const errored = Math.min(fa.n_read_errors, offered);
  const recovered = typeof fa.n_read_recovered === "number"
    ? Math.min(Math.max(fa.n_read_recovered, 0), errored) : 0;
  const nf = (n: number) => n.toLocaleString();
  const lost = errored - recovered;
  const tail = recovered <= 0
    ? ""
    : recovered === errored
      ? " · all of them read fine on the second try"
      : ` · ${nf(recovered)} read fine on the second try`;
  const text =
    `${nf(errored)} of ${nf(offered)} subs hit a read error${tail}`;
  // Guide a fix only when subs were actually *lost* to it and it's a material
  // share of a non-trivial stack — a single blip that recovered needs no nudge.
  const concern = offered >= 10 && lost > 0 && lost / offered >= 0.05;
  const guidance = concern
    ? "Those files were on disk but didn't read cleanly — that's usually the " +
      "drive or network share they live on, not the subs themselves. Check " +
      "the connection (or copy them somewhere local), then stack again to " +
      "get them back."
    : null;
  return { text, concern, guidance };
}

// One-line honest signal when sub-pixel refine had to leave some subs *only
// roughly aligned* — its measured shift exceeded the cap, so those frames
// stacked unshifted. The beginner sees slightly soft / doubled stars but has
// nothing pointing at alignment; this names it and, when it's a big share,
// nudges the likely cause (a less-steady mount, or subs that plate-solved a
// touch off). Pure so it can be unit-tested.
//
// Returns null when nothing's worth saying: no refine accounting recorded
// (older master / refine off), or every sub landed within the cap (the happy
// case needs no note). Only fires on a non-trivial share, so one stray sub out
// of thousands stays quiet.
export function roughlyAlignedNote(
  fa: StackFrameAccounting | null | undefined,
): FrameAccountingNote | null {
  if (!fa || typeof fa.n_offered !== "number" || fa.n_offered <= 0) return null;
  if (typeof fa.n_roughly_aligned !== "number" || fa.n_roughly_aligned <= 0) {
    return null;
  }
  const offered = fa.n_offered;
  const rough = Math.min(fa.n_roughly_aligned, offered);
  const nf = (n: number) => n.toLocaleString();
  const text =
    `${nf(rough)} of ${nf(offered)} subs were only roughly aligned · ` +
    `your stars may look a little soft`;
  // Guide a fix only when it's a materially large share and not a tiny stack
  // (one soft sub out of five isn't worth a scary nudge).
  const fraction = rough / offered;
  const concern = offered >= 10 && fraction >= 0.2;
  const guidance = concern
    ? "Many subs didn't quite line up to the reference, so the stacker used " +
      "them as-is — stars can end up a little soft or doubled. A steadier " +
      "mount, or re-solving these subs, usually tightens them up."
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
        const cal = calibrationSummaryText(
          data.cards, data.calibration_advice, data.calibration_skipped,
          data.calibration_warnings);
        if (!cal) return null;
        return (
          <Stack gap={2}>
            <Text size="xs" c="dimmed">
              {cal.text}
            </Text>
            {/* A calibration master the user explicitly chose but this run had to
                drop — the unattended binder skips it rather than failing the
                overnight job, so this is the only place the user learns why their
                picture is less calibrated than they asked for. */}
            {cal.skipped ? (
              <Text size="xs" c="yellow.7" fw={600}>
                {cal.skipped}
              </Text>
            ) : null}
            {/* And the opposite failure: a master that *was* applied but doesn't
                match the subs (a dark at the wrong exposure/temperature). The line
                above says "Calibrated with your master dark", so without this the
                run looks healthy while its pedestal is wrong on every frame. */}
            {cal.mismatch ? (
              <Text size="xs" c="yellow.7" fw={600}>
                {cal.mismatch}
              </Text>
            ) : null}
          </Stack>
        );
      })()}
      {weightingSummaryText(data.weighting, data.n_frames) ? (
        <Text size="xs" c="dimmed">
          {weightingSummaryText(data.weighting, data.n_frames)}
        </Text>
      ) : null}
      {weightingSkippedText(data.weighting_skipped, data.n_frames) ? (
        <Text size="xs" c="dimmed">
          {weightingSkippedText(data.weighting_skipped, data.n_frames)}
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
      {/* An unattended run that made a slightly smaller picture rather than no
          picture. Nobody saw the job decide it, so this is where the owner finds
          out why last night's image isn't the size of the one before. */}
      {drizzleDegradedNote(data.drizzle_degraded) ? (
        <Text size="xs" c="dimmed">
          {drizzleDegradedNote(data.drizzle_degraded)}
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
      {(() => {
        const re = readErrorNote(data.frame_accounting);
        if (!re) return null;
        return (
          <Stack gap={2}>
            <Text size="xs" c={re.concern ? "yellow.7" : "dimmed"} fw={re.concern ? 600 : undefined}>
              {re.text}
            </Text>
            {re.guidance ? (
              <Text size="xs" c="dimmed">{re.guidance}</Text>
            ) : null}
          </Stack>
        );
      })()}
      {(() => {
        const ra = roughlyAlignedNote(data.frame_accounting);
        if (!ra) return null;
        return (
          <Stack gap={2}>
            <Text size="xs" c={ra.concern ? "yellow.7" : "dimmed"} fw={ra.concern ? 600 : undefined}>
              {ra.text}
            </Text>
            {ra.guidance ? (
              <Text size="xs" c="dimmed">{ra.guidance}</Text>
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

function RunCard({ safe, run, onDelete, deleting, isCleanest, noiseDelta, compareToId, identity, focus }: {
  safe: string; run: StackRun; onDelete: () => void; deleting?: boolean;
  isCleanest?: boolean; noiseDelta?: number; compareToId?: number | null;
  identity?: ObjectInfo | null; focus?: FocusVerdict;
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
  const [copyingCaption, setCopyingCaption] = useState(false);
  // The "To phone" QR. It lives on the card rather than inside the Save / share
  // menu item that opens it, because the menu closes on click — a popover owned
  // by the item would be unmounted with the dropdown before it could be read.
  const [toPhone, setToPhone] = useState(false);
  // "What's in this picture?" (Identify) and "How big is this in the sky?"
  // (Scale) both come from the run's WCS via the same annotations endpoint —
  // lazily fetched once the user asks either (needs the FITS-header WCS, so gated
  // on has_fits).
  const [identify, setIdentify] = useState(false);
  const [scale, setScale] = useState(false);
  // "See what stacking removed" — tint the pixels outlier rejection dropped, so
  // the satellite trails and cosmic rays the stack quietly cleaned out stop being
  // an abstract percentage. Whether a run *has* such a map rides on the listing
  // row the page already fetched (alongside has_fits/has_preview), so offering
  // the toggle costs no request; the caption's fraction comes from the run-info
  // the Info panel reads, fetched only once the overlay is actually switched on.
  const [showRemoved, setShowRemoved] = useState(false);
  const hasRejectionMap = !!run.has_rejection_map;
  const removedInfo = useQuery({
    queryKey: ["stack-info", safe, run.id],
    queryFn: () => api.stackRunInfo(safe, run.id),
    enabled: showRemoved && hasRejectionMap,
    staleTime: Infinity,
  });
  const annotations = useQuery({
    queryKey: ["annotations", safe, run.id],
    queryFn: () => api.stackAnnotations(safe, run.id),
    enabled: (identify || scale) && run.has_fits,
    staleTime: Infinity,
  });
  const objects = annotations.data?.objects ?? [];
  const scaleBar = annotations.data?.scale_bar ?? null;
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
  // Is the picture on screen a *processed* one (the one-click "Process target"
  // Auto edit)? If so, the plain Save re-renders a flat stretch of the raw stack
  // over it — everywhere it's used, including a pinned cover — and says nothing.
  // Say it, and (when the recipe is still there) offer the save that keeps it.
  const processedPreview = !!suggestion.data?.processed_preview;
  const canKeepProcessed = !!suggestion.data?.can_keep_processed;
  const defStretch = typeof sugStretch === "number" ? sugStretch : DEFAULT_STRETCH;
  const defBlack = typeof sugBlack === "number" ? sugBlack : DEFAULT_BLACK;
  // Apply the suggestion the first time it arrives, but only while the user
  // hasn't touched the sliders yet (so it never yanks a value out from under them).
  // The ref answers that question inside the effect without re-running it; the
  // state mirrors it for *rendering*, because which picture the panel shows on a
  // processed run turns on the same "has anyone moved a slider?" fact.
  const touched = useRef(false);
  const [sliderTouched, setSliderTouched] = useState(false);
  const markTouched = (v: boolean) => { touched.current = v; setSliderTouched(v); };
  useEffect(() => {
    if (!touched.current && (typeof sugStretch === "number" || typeof sugBlack === "number")) {
      if (typeof sugStretch === "number") setStretch(sugStretch);
      if (typeof sugBlack === "number") setBlack(sugBlack);
    }
  }, [sugStretch, sugBlack]);

  const save = useMutation({
    mutationFn: (keepProcessed: boolean) =>
      api.saveStackPreview(safe, run.id, dStretch, dBlack, applyNorthUp, keepProcessed),
    onSuccess: (_data, keepProcessed) => {
      setCacheBust(Date.now());
      // The save records the North-up rotation it baked in on the run itself, so
      // the card's own row is stale the moment it lands.
      qc.invalidateQueries({ queryKey: ["runs", safe] });
      qc.invalidateQueries({ queryKey: ["sky"] });
      qc.invalidateQueries({ queryKey: ["gallery"] });
      // Either save can change whether this run's picture is still a processed
      // one, and the panel's warning — and which picture it shows — read that
      // flag. It's cached forever, so it has to be told.
      qc.invalidateQueries({ queryKey: ["render-suggestion", safe, run.id] });
      if (keepProcessed) {
        // The saved bytes are the processed picture, which the live slider
        // render on screen is not — so step out of the way and show it.
        setAdjust(false);
        notifications.show({ message: "Kept your processed picture", color: "teal" });
        return;
      }
      notifications.show({ message: "Preview updated", color: "teal" });
    },
    onError: () => notifications.show({ message: "Could not save preview", color: "red" }),
  });

  // Pin this run as the target's showcase "cover" — the picture the Library /
  // Dashboard tile shows, and the one that represents this target on the "My
  // best pictures" wall — or clear it back to the newest stack.
  const cover = useMutation({
    mutationFn: (pin: boolean) => api.setTargetCover(safe, pin ? run.id : null),
    onSuccess: (_data, pin) => {
      qc.invalidateQueries({ queryKey: ["runs", safe] });
      qc.invalidateQueries({ queryKey: ["targets"] });
      qc.invalidateQueries({ queryKey: ["target", safe] });
      // The wall picks its representative from the cover, so both the full wall
      // and the Dashboard strip are stale the moment this lands.
      qc.invalidateQueries({ queryKey: ["galleryBest"] });
      notifications.show({
        message: pin
          ? "Set as the target's cover — pinned to My best pictures too"
          : "Cover cleared — showing the newest stack",
        color: "teal",
      });
    },
    onError: () => notifications.show({ message: "Could not update cover", color: "red" }),
  });

  // "Copy caption" — one correct, friendly sentence to paste wherever the user
  // is sharing (chat, socials). Built purely from facts the app already knows:
  // the target's catalog identity, this run's frame count / integration / date,
  // and the scale bar. The scale clause needs the run's WCS (the same annotations
  // fetch that Identify/Scale use), so ensure it's loaded first — reusing the
  // cached result when the user already toggled Identify/Scale — then degrade
  // gracefully (drop the scale clause) if it can't be read.
  const copyCaption = async () => {
    setCopyingCaption(true);
    try {
      let scaleBar = annotations.data?.scale_bar ?? null;
      if (run.has_fits && !annotations.data) {
        try {
          const data = await qc.fetchQuery({
            queryKey: ["annotations", safe, run.id],
            queryFn: () => api.stackAnnotations(safe, run.id),
            staleTime: Infinity,
          });
          scaleBar = data.scale_bar ?? null;
        } catch {
          scaleBar = null;  // no WCS / read failed → caption omits the scale clause
        }
      }
      const text = postCaption({
        name: identity?.name,
        catalogId: identity?.id,
        type: identity?.type,
        nFrames: run.n_frames_used,
        integrationS: run.total_exposure_s,
        dateLabel: formatCaptionDate(run.timestamp_utc),
        scaleBar,
        fallbackName: safe,
      });
      try {
        await navigator.clipboard.writeText(text);
        notifications.show({
          message: "Caption copied — paste it wherever you're sharing.", color: "teal",
        });
      } catch {
        // Clipboard blocked (insecure context / permissions) — show the caption
        // so the user can still select and copy it by hand.
        notifications.show({
          title: "Copy this caption", message: text, color: "blue", autoClose: false,
        });
      }
    } finally {
      setCopyingCaption(false);
    }
  };

  // A best-effort caption to pre-fill the OS share sheet / lightbox share, so a
  // shared picture arrives with its words — the same accurate sentence as "Copy
  // caption", minus the scale clause unless the run's annotations happen to be
  // loaded already (the share flow is synchronous; we don't block it on a fetch).
  const shareCaption = postCaption({
    name: identity?.name,
    catalogId: identity?.id,
    type: identity?.type,
    nFrames: run.n_frames_used,
    integrationS: run.total_exposure_s,
    dateLabel: formatCaptionDate(run.timestamp_utc),
    scaleBar: annotations.data?.scale_bar ?? null,
    fallbackName: safe,
  });

  const previewSrc = `${api.stackArtifactUrl(safe, run.id, "preview")}${cacheBust ? `?v=${cacheBust}` : ""}`;
  // While the first suggestion fetch is still in flight, keep showing the STF
  // preview thumbnail rather than briefly rendering at the fixed defaults and
  // then jumping to the anchored sliders.
  const adjustOpen = adjust && run.has_fits && !suggestion.isLoading;
  // …and on a *processed* run, keep showing it until the user actually moves a
  // slider. The panel's two buttons save two different pictures there, and only
  // one of them is a slider render: someone who opens Adjust purely to turn the
  // picture (the one control anybody wants on a finished one) was being shown a
  // flat stretch of the raw stack, which is exactly what "Keep the processed
  // picture" does *not* write. Show the stored bytes — the picture that button
  // keeps — and switch to the live render the moment a slider says otherwise.
  const holdProcessed = adjustOpen && processedPreview && !sliderTouched;
  // The one thing the stored bytes can't show by themselves is the North-up
  // turn, so ask the server to rotate them on the way out (nothing on disk
  // changes) rather than falling back to a render of the linear master.
  const storedNorthUp = holdProcessed && applyNorthUp;
  const imgSrc = holdProcessed
    ? (storedNorthUp ? api.stackPreviewNorthUpUrl(safe, run.id)
       + (cacheBust ? `&v=${cacheBust}` : "") : previewSrc)
    : adjustOpen
    ? api.stackRenderUrl(safe, run.id, dStretch, dBlack, applyNorthUp)
    : previewSrc;
  // The *stored* preview can also be a crop of the canvas (the one-click
  // "Process target" auto-edit trims a mosaic's ragged border), which the pins
  // and bar are not measured on. Unlike a rotation this composes exactly, so
  // shift them into the trim rather than hiding them — and only while the stored
  // bytes are what's on screen; the live Adjust render is the full canvas.
  const showingStored = !adjustOpen || holdProcessed;
  // Is the picture *on screen* North-up? Three ways it can be, and the toggle
  // only knows one of them: the live adjustable render is rotating it now, this
  // request is rotating the stored bytes, or an earlier save baked the rotation
  // into the stored preview — which a fresh page load has no memory of
  // (`northUp` starts false). The pins and scale bar are measured on the
  // un-rotated FITS grid, so every case must suppress them.
  const savedNorthUp = !!run.preview_north_up_deg;
  const imageIsNorthUp = showingStored
    ? savedNorthUp || storedNorthUp
    : applyNorthUp;
  const view = croppedAnnotationView(
    showingStored ? run.preview_crop : null,
    objects, scaleBar,
    annotations.data?.width ?? run.canvas_w,
    annotations.data?.height ?? run.canvas_h,
  );
  // …and the one case that *can't* be composed: a stored preview whose geometry
  // isn't a crop of the canvas at all. Nothing measured on the FITS grid can be
  // placed on it honestly, so hide the pins/bar like a North-up save does.
  const geometryUnplaceable = showingStored && !!run.preview_geometry_unknown;
  const cantPlaceMarks = imageIsNorthUp || geometryUnplaceable;
  // The rejection tint is measured against the stored bytes, so it lands only
  // while those bytes are what's on screen — but it no longer has to step aside
  // for an on-the-fly North-up turn: the overlay endpoint takes the same turn
  // (on the drop-count plane, before the tint is built), so the two move
  // together. Unlike the pins and the scale bar, this one composes.
  const overlayPlaceable = showingStored;

  return (
    <Card withBorder padding="md" radius="md">
      <Card.Section>
        {run.has_preview || (adjust && run.has_fits) ? (
          <AnnotatedImage
            src={imgSrc} alt={run.output_basename}
            imgWidth={view.width}
            imgHeight={view.height}
            objects={view.objects} show={identify && !cantPlaceMarks} height={180}
            scaleBar={view.scaleBar} showScale={scale && !cantPlaceMarks}
            // The rose rides the same toggle as the bar — they are one idea
            // ("how big, and which way up?") and the *baked* share picture has
            // drawn them as a pair since v0.284.0. A crop doesn't turn a
            // picture, so the directions need no crop composition; the
            // rotation/unreconcilable cases hide it with everything else.
            directions={annotations.data?.directions ?? null}
            showCompass={scale && !cantPlaceMarks}
            // The server sizes the tint to the *stored* preview — including any
            // North-up turn a past save baked into it, and now the one this
            // request asks for on the way out — so it lands true on those bytes
            // however they are turned. The live Adjust render is a different
            // picture (full canvas, its own stretch), so the overlay still steps
            // aside there rather than landing somewhere the trail isn't.
            overlaySrc={showRemoved && hasRejectionMap && overlayPlaceable
              ? api.stackRejectionOverlayUrl(safe, run.id, storedNorthUp)
              : null}
            onClick={() => setLight(true)}
          />
        ) : (
          <Center h={180} bg="dark.6"><Text c="dimmed">No preview</Text></Center>
        )}
      </Card.Section>

      {cantPlaceMarks && (identify || scale) ? (
        // Object pins and the scale bar are computed on the un-rotated, un-cropped
        // FITS grid, so they'd land in the wrong place on a render that turned or
        // reshaped it. Hide them (rather than mis-plot) and say why — which differs
        // depending on whether it's the live toggle, a rotation a past save baked
        // in, or a processed picture whose geometry we can't reconcile at all.
        <Text size="xs" c="dimmed" mt={6}>
          {geometryUnplaceable && !imageIsNorthUp
            ? "This picture was reshaped when it was processed, so object pins, the scale bar and the compass can’t be placed on it — they’re measured on the original image. Open Adjust and save it again to use them."
            : applyNorthUp
            ? "Turn off “Rotate so North is up” to place object pins, the scale bar and the compass — they’re measured on the un-rotated image."
            : "This picture was saved rotated so North is up, so object pins, the scale bar and the compass can’t be placed on it — they’re measured on the un-rotated image. Open Adjust and save it un-rotated to use them."}
        </Text>
      ) : null}

      {showRemoved && hasRejectionMap ? (
        <Text size="xs" c={overlayPlaceable ? "cyan.4" : "dimmed"} mt={6}>
          {overlayPlaceable
            ? removedOverlayCaption(removedInfo.data?.rejection)
            : "Close Adjust to see what stacking removed — the marks are measured on the saved picture, not on the live render."}
        </Text>
      ) : null}

      {identify && !cantPlaceMarks && !annotations.isLoading && annotations.isSuccess ? (
        view.objects.length ? (
          // Plain-language "what else is in this picture?" list — the friendly
          // read of the same objects the overlay labels on the image, so a
          // beginner can tell what the other smudges are without squinting at
          // overlapping labels on a small preview.
          <Stack gap={2} mt={6}>
            <Text size="xs" c="cyan.4">
              In this picture — {view.objects.length} catalog object{view.objects.length === 1 ? "" : "s"}:
            </Text>
            {describeFieldObjects(
              view.objects, view.width, view.height,
            ).map((d) => (
              <Text key={d.catalogId} size="xs" c="dimmed">
                {d.label}{d.typePhrase ? ` — ${d.typePhrase}` : ""}, {d.positionPhrase}.
              </Text>
            ))}
            {view.objects.length > 5 ? (
              <Text size="xs" c="dimmed">…and {view.objects.length - 5} more.</Text>
            ) : null}
          </Stack>
        ) : (
          <Text size="xs" c="dimmed" mt={6}>No catalog objects fall inside this field</Text>
        )
      ) : null}

      {scale && !cantPlaceMarks && !annotations.isLoading && annotations.isSuccess ? (
        <Text size="xs" c={scaleBar ? "grape.3" : "dimmed"} mt={6}>
          {scaleBar
            // Capitalise the plain-language Moon sentence for the caption.
            ? scaleBar.moon_comparison.charAt(0).toUpperCase() + scaleBar.moon_comparison.slice(1)
            : "This picture has no sky coordinates, so its scale can't be measured"}
        </Text>
      ) : null}

      <Group justify="space-between" mt="sm" wrap="nowrap">
        <Text fw={600}>{run.output_basename}</Text>
        <Group gap={4} wrap="nowrap">
          <CleanestBadge isCleanest={!!isCleanest} />
          <FocusChip verdict={focus} />
          <RejectionBadge options={run.options} />
          <HazyNightBadge ratio={run.transparency_ratio} />
          <PanelSeamsBadge verdict={run.seam_verdict} />
          <CalibrationBadge calstat={run.calstat} />
          {/* Same honesty as the Target page's hero: this card's thumbnail is the
              baked preview, so a saved-but-never-exported edit isn't in it. The
              one-click finish lives on the hero; here it's just a truthful label
              next to the picture it applies to. */}
          <UnexportedEditBadge show={run.unexported_edit} />
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
              onChange={(v) => { markTouched(true); setStretch(v); }}
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
              onChange={(v) => { markTouched(true); setBlack(v); }}
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
          {processedPreview ? (
            // Said *before* the save, next to the button that does it: this
            // panel is the one reachable path that quietly costs a beginner
            // their finished picture, and its own hint ("from the full-range
            // FITS") reads like a view control.
            <Text size="xs" c="yellow.4" mt={4}>
              This picture was processed for you.{" "}
              {canKeepProcessed
                ? "“Save as preview” replaces it with a plain view of the raw stack — use “Keep the processed picture” below to change how it’s turned without losing it."
                : "“Save as preview” replaces it with a plain view of the raw stack. Your edit is kept — re-open it in the editor to get the processed look back."}
            </Text>
          ) : null}
          <Group gap="xs" mt={4}>
            {processedPreview && canKeepProcessed ? (
              // The one thing you actually want from this panel on a finished
              // picture is the rotation, so that save is the primary action
              // here — it re-bakes the run's own edit instead of the sliders.
              <Button
                size="xs" color="grape" leftSection={<IconSparkles size={14} />}
                loading={save.isPending && save.variables === true}
                onClick={() => save.mutate(true)}
              >
                Keep the processed picture
              </Button>
            ) : null}
            <Button
              size="xs" leftSection={<IconDeviceFloppy size={14} />}
              variant={processedPreview && canKeepProcessed ? "light" : "filled"}
              loading={save.isPending && save.variables === false}
              onClick={() => save.mutate(false)}
            >
              Save as preview
            </Button>
            <Button
              size="xs" variant="subtle"
              onClick={() => { markTouched(false); setStretch(defStretch); setBlack(defBlack); }}
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
          {/* Everything you can *do with the file* lives behind one menu. The
              card used to lay all fifteen of these out as buttons, four rows
              deep, per run — so a target with eight stacks was a wall of
              chrome. Nothing was removed: every item below is the control that
              used to be a button, with its own wording and behaviour. */}
          {(run.has_preview || run.has_fits || run.has_tiff) && (
            <Menu shadow="md" width={260} position="bottom-start">
              <Menu.Target>
                <Button
                  size="xs" variant="light"
                  leftSection={<IconDownload size={14} />}
                  rightSection={<IconChevronDown size={14} />}
                >
                  Save / share
                </Button>
              </Menu.Target>
              {/* Twelve items with a line of help each is taller than the space
                  under a card halfway down a laptop screen — measured in a real
                  browser, where the dropdown flipped upwards and lost its first
                  item off the top. Capping it scrolls instead of clipping, the
                  same way the Gallery's preset menu does. */}
              <Menu.Dropdown mah={420} style={{ overflowY: "auto" }}>
                <Menu.Label>Download</Menu.Label>
                {run.has_preview && (
                  <Menu.Item
                    leftSection={<IconPhotoDown size={16} />}
                    component="a" href={api.stackArtifactUrl(safe, run.id, "preview")}
                  >
                    PNG
                    <span style={MENU_HINT}>Quick preview, up to 1024 px wide</span>
                  </Menu.Item>
                )}
                {run.has_fits && (
                  <Menu.Item
                    leftSection={<IconPhotoDown size={16} />}
                    component="a" href={api.stackFullResPngUrl(safe, run.id, applyNorthUp)}
                  >
                    Full-res PNG
                    <span style={MENU_HINT}>
                      {fullResPngHint(run.canvas_w, run.canvas_h)}
                    </span>
                  </Menu.Item>
                )}
                {run.has_preview && (
                  <Menu.Item
                    leftSection={<IconPhotoDown size={16} />}
                    component="a"
                    href={api.stackArtifactUrl(safe, run.id, "jpeg", applyNorthUp, nameplate)}
                  >
                    JPEG
                    <span style={MENU_HINT}>
                      {applyNorthUp ? "North up — smaller, best for sharing" : "Smaller — best for sharing"}
                    </span>
                  </Menu.Item>
                )}
                {run.has_preview && (
                  /* The framed variant: matted on a dark card with this run's
                     name, date and total exposure set *beneath* the picture. It
                     carries its own caption, so it ignores the nameplate toggle
                     above rather than captioning the same facts twice. */
                  <Menu.Item
                    leftSection={<IconPhotoDown size={16} />}
                    component="a"
                    href={api.stackArtifactUrl(
                      safe, run.id, "jpeg", applyNorthUp, false, true)}
                  >
                    Framed keepsake
                    <span style={MENU_HINT}>
                      Its name, date and exposure printed on the picture
                    </span>
                  </Menu.Item>
                )}
                {run.has_preview && (
                  /* The scale bar and compass this page already draws *on
                     screen*, baked into the downloaded pixels — a browser
                     overlay doesn't travel with the file. Follows the North-up
                     toggle, so the rose points where the saved picture does. */
                  <Menu.Item
                    leftSection={<IconPhotoDown size={16} />}
                    component="a"
                    href={api.stackArtifactUrl(
                      safe, run.id, "jpeg", applyNorthUp, false, false, true)}
                  >
                    With scale &amp; compass
                    <span style={MENU_HINT}>
                      How big it is and which way is North, printed on the picture
                    </span>
                  </Menu.Item>
                )}
                {run.has_fits && (
                  <Menu.Item
                    leftSection={<IconDownload size={16} />}
                    component="a" href={api.stackArtifactUrl(safe, run.id, "fits")}
                  >
                    FITS
                    <span style={MENU_HINT}>Raw data — for re-processing, not sharing</span>
                  </Menu.Item>
                )}
                {run.has_tiff && (
                  <Menu.Item
                    leftSection={<IconDownload size={16} />}
                    component="a" href={api.stackArtifactUrl(safe, run.id, "tiff")}
                  >
                    TIFF
                    <span style={MENU_HINT}>{tiffDownloadHint(run.options)}</span>
                  </Menu.Item>
                )}
                {run.has_preview && (
                  <>
                    <Menu.Divider />
                    <Menu.Label>Share</Menu.Label>
                    <SharePictureButton
                      asMenuItem
                      url={api.stackArtifactUrl(safe, run.id, "jpeg", applyNorthUp, nameplate)}
                      {...sharePictureText(
                        run.output_basename,
                        formatStampDate(run.timestamp_utc),
                      )}
                      text={shareCaption}
                    />
                    {/* The QR opens in a modal owned by the card, not a popover
                        owned by this item — a menu closes on click, which would
                        unmount its own popover with it. */}
                    <Menu.Item
                      leftSection={<IconDeviceMobile size={16} />}
                      onClick={() => setToPhone(true)}
                    >
                      To phone
                      <span style={MENU_HINT}>Scan a QR to open it on your phone</span>
                    </Menu.Item>
                    <Menu.Item
                      leftSection={copyingCaption
                        ? <Loader size={14} />
                        : <IconClipboardText size={16} />}
                      onClick={copyCaption}
                    >
                      Copy caption
                      <span style={MENU_HINT}>A ready-to-post sentence about this picture</span>
                    </Menu.Item>
                    {/* Motion, for the places a still gets swiped past. Built and
                        cached server-side from this run's own preview, so it costs
                        no extra request to offer: every run with a picture has one. */}
                    <DownloadMenuItem
                      icon={<IconVideo size={16} />}
                      url={api.stackZoomClipUrl(safe, run.id)}
                      filename={`${run.output_basename || "stack"}_zoom.webp`}
                      label="Zoom clip"
                      hint="A few seconds gliding into your target — for posting"
                      busyHint="Building your clip — a few seconds the first time"
                      errorMessage="Couldn't build a zoom clip for this run."
                      hintStyle={MENU_HINT}
                    />
                    <Menu.Divider />
                    <WallpaperMenuItems safe={safe} runId={run.id} />
                  </>
                )}
              </Menu.Dropdown>
            </Menu>
          )}
          {/* And everything that tells you *about* the picture — or changes how
              this card shows it — lives behind the second. */}
          {(run.has_fits || run.has_preview) && (
            <Menu shadow="md" width={260} position="bottom-start">
              <Menu.Target>
                <Button
                  size="xs" variant="light"
                  leftSection={<IconInfoCircle size={14} />}
                  rightSection={<IconChevronDown size={14} />}
                >
                  About this stack
                </Button>
              </Menu.Target>
              <Menu.Dropdown>
                {run.has_fits && (
                  <Menu.Item
                    leftSection={<IconInfoCircle size={16} />}
                    rightSection={showInfo ? <IconCheck size={14} /> : null}
                    onClick={() => setShowInfo((s) => !s)}
                  >
                    Info
                    <span style={MENU_HINT}>How this stack was made</span>
                  </Menu.Item>
                )}
                {run.has_fits && (
                  <Menu.Item
                    leftSection={<IconTags size={16} />}
                    rightSection={identify ? <IconCheck size={14} /> : null}
                    onClick={() => setIdentify((v) => !v)}
                  >
                    Identify
                    <span style={MENU_HINT}>Label the catalog objects in the field</span>
                  </Menu.Item>
                )}
                {run.has_fits && (
                  <Menu.Item
                    leftSection={<IconRuler2 size={16} />}
                    rightSection={scale ? <IconCheck size={14} /> : null}
                    onClick={() => setScale((v) => !v)}
                  >
                    Scale &amp; compass
                    <span style={MENU_HINT}>How big this is in the sky, and which way is North</span>
                  </Menu.Item>
                )}
                {hasRejectionMap && (
                  <Menu.Item
                    leftSection={<IconSparkles size={16} />}
                    rightSection={showRemoved ? <IconCheck size={14} /> : null}
                    onClick={() => setShowRemoved((v) => !v)}
                  >
                    Show what was removed
                    <span style={MENU_HINT}>The satellite trails and cosmic rays stacking cleaned out</span>
                  </Menu.Item>
                )}
                {run.has_fits && (
                  <Menu.Item
                    leftSection={<IconAdjustments size={16} />}
                    rightSection={adjust ? <IconCheck size={14} /> : null}
                    onClick={() => setAdjust((a) => !a)}
                  >
                    Adjust
                    <span style={MENU_HINT}>Stretch / black point, from the full-range FITS</span>
                  </Menu.Item>
                )}
                {run.has_preview && (
                  <Menu.Item
                    leftSection={cover.isPending
                      ? <Loader size={14} />
                      : run.is_cover ? <IconStarFilled size={16} /> : <IconStar size={16} />}
                    onClick={() => cover.mutate(!run.is_cover)}
                  >
                    {run.is_cover ? "Cover" : "Set as cover"}
                    <span style={MENU_HINT}>
                      {run.is_cover
                        ? "This is the target's cover — show the newest stack instead"
                        : "Use this picture on the Library tile and My best pictures"}
                    </span>
                  </Menu.Item>
                )}
              </Menu.Dropdown>
            </Menu>
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
          {/* "Did I frame it well?" for *this* run. The verdict is per-run, and
              History is where a beginner compares two stacks of one target — the
              place "this one caught all of it, that one clipped it" earns its
              keep. The same component as the Target page's note, not a re-wording:
              one picture must read the same on both surfaces. Self-hides when the
              endpoint has no honest answer. */}
          <FramingVerdictNote safe={safe} runId={run.id} />
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
        fullResHref={run.has_fits ? api.stackFullResPngUrl(safe, run.id, applyNorthUp) : undefined}
        fullResCanvas={{ w: run.canvas_w, h: run.canvas_h }}
        rawHref={run.has_fits ? api.stackArtifactUrl(safe, run.id, "fits") : undefined}
        {...(run.has_preview
          ? (() => {
              const { title, filename } = sharePictureText(
                run.output_basename,
                formatStampDate(run.timestamp_utc),
              );
              return { shareFilename: filename, shareTitle: title, shareText: shareCaption };
            })()
          : {})}
        onClose={() => setLight(false)}
      />

      {run.has_preview ? (
        <ScanToPhoneModal
          url={api.stackArtifactUrl(safe, run.id, "jpeg", applyNorthUp, nameplate)}
          opened={toPhone}
          onClose={() => setToPhone(false)}
        />
      ) : null}
    </Card>
  );
}

export function HistoryView() {
  const { safe = "" } = useParams();
  const qc = useQueryClient();
  const [sort, setSort] = useState<RunSort>("newest");
  const runs = useQuery({ queryKey: ["runs", safe], queryFn: () => api.listStackRuns(safe) });
  // Only for the heading — the page works off `safe`, but the title has to say
  // the target's *name*. Shares the query key every other target screen uses, so
  // arriving from the Target page is a cache hit, and a failure leaves `safe`.
  const target = useQuery({ queryKey: ["target", safe], queryFn: () => api.getTarget(safe) });
  // The target's catalog identity (name/type), fetched once for the page so the
  // per-run "Copy caption" can name the object; null when nothing matches (the
  // caption then degrades to the target's own name). Never blocks the page.
  const identity = useQuery({
    queryKey: ["identify", safe],
    queryFn: () => api.identifyTarget(safe),
    staleTime: Infinity,
  });

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
  // Per-run focus chips are judged against each run's own priors, so compute
  // them from the API's chronological (newest-first) order, not the display sort.
  const focus = focusChips(list);
  const sorted = sortRuns(list, sort);
  const trend = noiseTrendSeries(list);
  // "Is this target still improving, or has it plateaued?" — a data-driven read
  // of the measured noise-vs-√time trend across this target's stacks. Null (and
  // hidden) unless two stacks both measured a σ and span a real time increase.
  const integration = integrationTrend(list);

  return (
    <Stack>
      <Group justify="space-between">
        <Title order={2}>Stack history — {target.data?.name ?? safe}</Title>
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
      {/* First-run coaching, on the sample demo only (see SampleTourNote): the
          last step of the tour — where finished pictures live, and what Export
          is for. */}
      <SampleTourNote step="history" safe={safe} />
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
              {integration ? (
                <Text
                  size="xs"
                  mt={4}
                  c={integration.level === "improving"
                    ? "teal"
                    : integration.level === "plateaued"
                      ? "orange"
                      : "dimmed"}
                >
                  {integration.sentence}
                </Text>
              ) : null}
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
              identity={identity.data ?? null}
              focus={focus.get(r.id)}
              compareToId={previousRunId(list, r.id)} />
          ))}
        </SimpleGrid>
      )}
    </Stack>
  );
}
