import {
  ActionIcon, Alert, Anchor, Badge, Button, Center, Group, Loader, Paper, Progress, Stack, Switch,
  Text, Title, Tooltip,
} from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { IconActivity, IconDownload, IconFlask, IconPhoto, IconX } from "@tabler/icons-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { type ReactNode, useRef, useState } from "react";
import { api, type Job } from "../api/client";
import { QueryError } from "../components/QueryError";
import { settingsLink } from "../settingsSections";
import { CalibrationSkippedNote } from "../components/CalibrationSkippedNote";
import { StackNoiseBadge } from "../components/StackNoiseBadge";
import { thinStackWarning, type ThinStackWarning } from "../components/target/thinStack";
import { rejectionNote } from "../components/target/rejectionNote";
import { type EtaSample, etaLabel, updateEtaAnchor } from "../jobEta";
import {
  isJobNotifyEnabled, notificationsSupported, requestNotificationPermission,
  setJobNotifyEnabled,
} from "../jobNotify";

const COLOR: Record<string, string> = {
  running: "violet",
  queued: "gray",
  done: "teal",
  error: "red",
  cancelled: "orange",
  interrupted: "orange",
};

// Plain-language names for the engine's internal job kinds. The backend submits
// jobs under snake_case identifiers (webapp/pipeline.py) — `pipeline`, `qc_solve`,
// `editor_png` … — which mean nothing to a Seestar beginner, and Jobs is the very
// first screen a new user lands on (clicking "Scan incoming" navigates here). Every
// other screen already translates engine jargon (History's combineMethodLabel,
// Target's rejectReasonLabel); this brings Jobs into line. Unknown kinds fall back
// to the raw identifier so a future job type is still shown, just untranslated.
const KIND_LABEL: Record<string, string> = {
  pipeline: "Importing & processing new frames",
  qc_solve: "Quality check & plate-solve",
  process_target: "Processing target (check, solve & stack)",
  stack: "Stacking",
  reprocess_all: "Reprocessing all targets",
  editor_png: "Rendering full-resolution PNG",
  editor_export: "Exporting edited image",
  editor_batch: "Batch export",
  build_master: "Building calibration master",
  channel_combine: "Channel combine",
  video_stack: "Stacking Moon/Sun video",
  video_grade: "Checking Moon/Sun video",
};

/** Human-readable name for an engine job kind (pure, tested). */
export function jobKindLabel(kind: string): string {
  return KIND_LABEL[kind] ?? kind;
}

// Plain-language text for each *known fatal* failure category. Keyed by the stable
// canonical `error_kind` the backend now stamps on a failed job (webapp/jobs.py),
// so a beginner sees a sentence + next step instead of a bare Python exception like
// `MemoryError: stack output canvas 8000×6000 …` or `ValueError: no accepted,
// plate-solved frames to stack`.
/** A failed job's plain-language explanation, its next step, and — when the next
 * step is "change a setting" — a link straight to the section that holds it.
 * `next` stays a plain string (it is pinned by tests and read as prose); the
 * link is a sibling, the same shape `StackHealthCard`'s `noteAction` uses. */
export interface JobErrorHelp {
  message: string;
  next?: string;
  action?: { label: string; href: string };
}

const JOB_ERROR_KIND: Record<string, JobErrorHelp> = {
  // Stack refused *before running* because the output canvas would exceed the
  // memory budget (the OOM guard in stacker.py, raised as MemoryError).
  memory_budget: {
    message:
      "This stack needs more memory than the budget allows, so it was refused "
      + "before running rather than risk crashing the app.",
    next:
      "Lower the drizzle scale, set Canvas mode to “reference”, reject off-target "
      + "frames, or raise the memory limit in Settings, then stack again.",
    // "…in Settings" is one of seven pages; the memory budget lives on Stacking.
    action: { label: "Open Settings → Stacking →", href: settingsLink("stacking") },
  },
  // Nothing accepted + plate-solved to stack.
  no_solved_frames: {
    message: "There are no accepted, plate-solved frames to stack yet.",
    next:
      "Run Quality check & plate-solve first, and make sure at least one accepted "
      + "frame solved successfully.",
  },
  // Alignment produced nothing usable (non-overlapping / different fields).
  no_alignment: {
    message: "None of the frames could be aligned into a stack.",
    next:
      "This usually means the frames don’t overlap or solved to different fields — "
      + "check they’re all the same target, then re-run plate-solve and stack again.",
  },
  // Reference frame has no usable WCS to align the others against.
  no_reference_wcs: {
    message: "The reference frame isn’t plate-solved, so the stack has nothing to align to.",
    next: "Re-run Quality check & plate-solve, then stack again.",
  },
  // A "Build master" job was pointed at a folder with no FITS frames.
  no_fits_in_folder: {
    message: "No FITS frames were found in that folder.",
    next:
      "Point it at the folder that holds your calibration frames (the .fits darks, "
      + "flats or bias subs) and build the master again.",
  },
};

// Translate a failed job into a plain sentence + next step. Prefer the backend's
// stable `error_kind` (reword-proof, classified server-side where the exception
// *type* is known); fall back to matching the raw `error` string for an older
// backend that doesn't stamp the field. Anything unrecognised falls through to the
// raw text verbatim so no information is ever hidden.
export function friendlyJobError(
  raw: string, kind?: string | null,
): JobErrorHelp {
  if (kind && JOB_ERROR_KIND[kind]) return JOB_ERROR_KIND[kind];
  const s = raw.toLowerCase();
  if (s.includes("memoryerror") || s.includes("working memory")) {
    return JOB_ERROR_KIND.memory_budget;
  }
  if (s.includes("plate-solve") || s.includes("plate solved")
      || s.includes("plate-solved")) {
    return JOB_ERROR_KIND.no_solved_frames;
  }
  if (s.includes("no frames could be aligned") || s.includes("no usable frames")
      || s.includes("did not intersect the canvas")
      || s.includes("produced no usable frames")) {
    return JOB_ERROR_KIND.no_alignment;
  }
  if (s.includes("missing wcs") || s.includes("wcs could not be parsed")
      || s.includes("reference wcs")) {
    return JOB_ERROR_KIND.no_reference_wcs;
  }
  if (s.includes("no fits files found")) {
    return JOB_ERROR_KIND.no_fits_in_folder;
  }
  return { message: raw };
}

/** Plain-language outcome of a finished reprocess-all batch (pure, tested). */
export function reprocessSummary(r: Record<string, unknown>): {
  line: string; failed: string[];
} {
  const total = Number(r.total ?? 0);
  const stacked = Number(r.stacked ?? 0);
  const skipped = Number(r.skipped ?? 0);
  const rescanned = Number(r.rescanned ?? 0);
  const autoEdited = Number(r.auto_edited ?? 0);
  const failedArr = Array.isArray(r.failed) ? r.failed : [];
  const failed = failedArr
    .map((f) => (f && typeof f === "object"
      ? String((f as Record<string, unknown>).target ?? "") : ""))
    .filter(Boolean);
  let line = `Restacked ${stacked}/${total} target${total === 1 ? "" : "s"}`;
  if (r.cancelled) line += " (cancelled early)";
  // Only present when the deep-rescan option was used (re-ran QC/solve/grade first).
  if (rescanned > 0) line += ` — re-ran QC/solve/grade on ${rescanned}`;
  // Only present when the auto-edit option was used (finished pictures, not linear).
  if (autoEdited > 0) line += ` — auto-edited ${autoEdited}`;
  if (skipped > 0) line += ` — ${skipped} already up to date`;
  if (failed.length) line += ` — ${failed.length} failed`;
  return { line: `${line}.`, failed };
}

/** Plain-language outcome of a finished one-click "Process target" job (pure,
 * tested). Mirrors `reprocessSummary` for the single-target chain: says whether a
 * master was produced and, when it wasn't, why — so the user isn't left with a
 * bare "done" and no idea where the result is (or why there isn't one). */
export function processTargetSummary(r: Record<string, unknown>): {
  line: string; stacked: boolean; thin: ThinStackWarning | null;
  cleaned: string | null; storage: { title: string; message: string } | null;
  calMismatch: string | null;
} {
  const stacked = Boolean(r.stacked);
  const solved = Number(r.solved_accepted ?? 0);
  const graded = Number(r.auto_graded ?? 0);
  if (stacked) {
    const stack = r.stack && typeof r.stack === "object"
      ? (r.stack as Record<string, unknown>) : {};
    const used = Number(stack.n_frames_used ?? 0) || solved;
    let line = `Stacked ${used} frame${used === 1 ? "" : "s"} into a new master`;
    if (graded > 0) line += ` (auto-grade dropped ${graded})`;
    // A thin auto-stack (≤4 combined frames) is the owner's "gibberish" case:
    // the Jobs page would otherwise cheerfully report a green "Stacked 1 frame"
    // with a View-result link and no hint the picture is just noise. Surface the
    // same honest heads-up the Target page shows, right where the result lands.
    const thin = thinStackWarning(used);
    // Name the invisible outlier-rejection clean-up (e.g. the lone satellite/
    // plane trail a small walk-away auto-stack removed with min/max) — the honest
    // counterpart to "some frames were left out". Omit it on a thin stack, where
    // the "this is basically one noisy sub" warning is the message that matters.
    const cleaned = thin ? null : rejectionNote(
      typeof stack.rejection_mode === "string" ? stack.rejection_mode : null,
      typeof stack.rejection_fraction === "number" ? stack.rejection_fraction : null,
      Number(stack.n_frames_used ?? 0) || null,
    );
    // The walk-away user's only cue that their subs didn't come off the disk
    // cleanly — files that weren't there at all (Stage-1 cache cleared while the
    // originals sit on an offline share, a drive unmounted) and files that were
    // there and blew up mid-read. Both diagnoses in ONE alert, because a share
    // that unmounts mid-scan produces both and they are one story about one
    // drive. Self-omits when everything read fine, and on an older backend that
    // doesn't report the counts.
    const storage = storageTroubleAlert(
      Number(stack.n_unreadable ?? 0) || 0,
      Number(stack.n_read_errors ?? 0) || 0,
      Number(stack.n_read_recovered ?? 0) || 0,
      Number(stack.n_offered ?? 0) || 0,
    );
    // A master dark that *was* applied but doesn't match these subs (wrong
    // exposure, or shot at a very different sensor temperature) over/under-
    // subtracts its pedestal on every frame. The engine has always measured it
    // and written it to the server log — which is exactly the place a walk-away
    // user never looks — so say it where the finished picture lands.
    const calMismatch = calibrationMismatchNote(stack.calibration_warnings);
    return { line: `${line}.`, stacked, thin, cleaned, storage, calMismatch };
  }
  const reason = typeof r.stack_skipped_reason === "string"
    ? r.stack_skipped_reason : null;
  let line: string;
  if (reason === "cancelled") {
    line = "Cancelled before stacking.";
  } else if (reason === "no_solved_frames") {
    line = "Checked and solved, but no frames could be plate-solved yet — "
      + "so there was nothing to stack.";
  } else {
    line = "Finished, but no stack was produced.";
  }
  return {
    line, stacked, thin: null, cleaned: null, storage: null, calMismatch: null,
  };
}

/** The run's master-vs-subs calibration mismatches as one sentence, or null when
 * everything matched (pure, tested).
 *
 * The engine writes these already-plain-language sentences ("Master dark is 30s
 * but your subs are 10s — its pedestal will be over-subtracted on every frame…"),
 * so this only joins and guards them. Returns null for an older backend that
 * doesn't report the field, a non-list value, and a list of nothing but blanks. */
export function calibrationMismatchNote(warnings: unknown): string | null {
  if (!Array.isArray(warnings)) return null;
  const parts = warnings
    .filter((w): w is string => typeof w === "string")
    .map((w) => w.trim())
    .filter(Boolean);
  return parts.length ? parts.join(" ") : null;
}

/** Plain-language note when some of a target's subs had no file on disk at all
 * when the stack ran, so they couldn't be combined (pure, tested).
 *
 * `readable_frame_path` falls back from the Stage-1 cache to the original
 * source, and the stacker quietly skips a frame with neither — so a cleared
 * cache plus an offline NAS share (or an unmounted drive) silently thins the
 * stack. The engine now counts them up front; this turns the count into the one
 * sentence that names the cause *and* the fix. Returns null when nothing was
 * missing, or when the count/total isn't reported (older backend). */
export function missingSubsNote(nUnreadable: number, nOffered: number): string | null {
  if (!Number.isFinite(nUnreadable) || nUnreadable <= 0) return null;
  if (!Number.isFinite(nOffered) || nOffered <= 0) return null;
  const missing = Math.min(Math.round(nUnreadable), Math.round(nOffered));
  const nf = (n: number) => n.toLocaleString();
  return `${nf(missing)} of ${nf(nOffered)} subs couldn't be read — their files `
    + "weren't on disk. If they live on a drive or network share, check it's "
    + "connected, then scan and stack again.";
}

/** Plain-language note when some subs' files *were* on disk and then failed
 * mid-read, so the stacker recorded a per-frame error for them (pure, tested).
 *
 * The sibling of `missingSubsNote`: that one is "the file wasn't there", this one
 * is "the file was there and the read blew up" — a flaking network share, a bad
 * sector, a half-written file. The engine has always recorded these as raw
 * per-file strings in the run's `errors` list, which no screen reads, so a night
 * of dropped reads reached the owner only as an unexplained thin stack. This
 * turns the count into the one sentence that names the cause and the fix, and
 * says how many read fine on the run's other pass — those subs *are* in the
 * picture, which is the difference between "check the drive tomorrow" and "your
 * night is gone". Returns null when nothing errored, or when the counts aren't
 * reported (older backend). */
export function readErrorsNote(
  nReadErrors: number, nRecovered: number, nOffered: number,
): string | null {
  if (!Number.isFinite(nReadErrors) || nReadErrors <= 0) return null;
  if (!Number.isFinite(nOffered) || nOffered <= 0) return null;
  const errored = Math.min(Math.round(nReadErrors), Math.round(nOffered));
  const recovered = Number.isFinite(nRecovered)
    ? Math.min(Math.max(Math.round(nRecovered), 0), errored) : 0;
  const nf = (n: number) => n.toLocaleString();
  const subs = `${nf(errored)} sub${errored === 1 ? "" : "s"}`;
  const lead = `${subs} hit a read error while stacking`;
  const recoveredClause = recovered > 0
    ? recovered === errored
      ? ` — all of them read fine on the second try, so they're in your picture`
      : ` — ${nf(recovered)} of them read fine on the second try, so those are `
        + `in your picture`
    : "";
  return `${lead}${recoveredClause}. The files are there but didn't read `
    + "cleanly — worth checking the drive or network share they live on.";
}

/** The run's storage trouble as ONE alert — title and body — or null when every
 * sub read fine (pure, tested).
 *
 * `missingSubsNote` and `readErrorsNote` are deliberately different diagnoses
 * ("the file wasn't there" vs. "the file was there and the read blew up"), and on
 * a healthy install at most one ever fires. But a share that unmounts mid-scan
 * fires **both**, and two stacked yellow alerts that each end by telling the owner
 * to go check the same drive read as two problems and bury the one action under
 * twice the words. When both fire this composes them into a single alert that
 * keeps the two counts and their two causes distinct — they really are different
 * failures — and says the shared fix once. When only one fires it is that note,
 * unchanged, under its own title.
 *
 * Both underlying helpers stay exported and untouched: History renders them as
 * separate lines beside its align clause, where the one-story problem doesn't
 * arise. */
export function storageTroubleAlert(
  nUnreadable: number, nReadErrors: number, nRecovered: number, nOffered: number,
): { title: string; message: string } | null {
  const missing = missingSubsNote(nUnreadable, nOffered);
  const readErrors = readErrorsNote(nReadErrors, nRecovered, nOffered);
  if (!missing && !readErrors) return null;
  if (missing && !readErrors) {
    return { title: "Some subs couldn't be read", message: missing };
  }
  if (readErrors && !missing) {
    return { title: "Some subs didn't read cleanly", message: readErrors };
  }
  // Both. Rebuild the clauses rather than concatenating the two notes, so the
  // "check the drive" sentence is said once instead of twice.
  const offered = Math.round(nOffered);
  const gone = Math.min(Math.round(nUnreadable), offered);
  const errored = Math.min(Math.round(nReadErrors), offered);
  const recovered = Number.isFinite(nRecovered)
    ? Math.min(Math.max(Math.round(nRecovered), 0), errored) : 0;
  const nf = (n: number) => n.toLocaleString();
  const recoveredClause = recovered > 0
    ? recovered === errored
      ? " (all of them read fine on the second try, so they're in your picture)"
      : ` (${nf(recovered)} of them read fine on the second try, so those are `
        + "in your picture)"
    : "";
  return {
    title: "Trouble reading your subs",
    message: `${nf(gone)} of ${nf(offered)} subs couldn't be read at all — their `
      + `files weren't on disk. Another ${nf(errored)} sub`
      + `${errored === 1 ? " was" : "s were"} there but hit a read error while `
      + `stacking${recoveredClause}. Both point at the same place: check the drive `
      + "or network share these files live on is connected, then scan and stack "
      + "again.",
  };
}

/** How many subs the stack-then-solve bootstrap rescued in this job result, or
 * 0 when it never engaged (pure, tested).
 *
 * The bootstrap only engages when *most* subs failed to plate-solve on their own:
 * it stacks the un-located ones into a deeper image, solves that once, and
 * propagates the result back. Single-target jobs (`qc_solve`, `process_target`)
 * carry the engine's own `bootstrap_propagated`; the whole-library scan reports
 * `bootstrap_rescued` as a per-target map. Both shapes are read here so one
 * helper covers every surface. */
export function bootstrapRescuedCount(r: Record<string, unknown>): number {
  const direct = Number(r.bootstrap_propagated ?? 0) || 0;
  const perTarget = r.bootstrap_rescued && typeof r.bootstrap_rescued === "object"
    ? Object.values(r.bootstrap_rescued as Record<string, unknown>)
        .reduce<number>((sum, n) => sum + (Number(n) || 0), 0)
    : 0;
  return Math.max(0, direct + perTarget);
}

/** The plain-language credit for that rescue, or null when it didn't happen.
 *
 * Without this the beginner who turned the setting on (because their faint
 * targets came out noisy) just sees a suddenly-thicker stack with no idea why —
 * and the Target page's "N not located yet" badge silently drops instead of
 * saying what fixed it. Says what happened in one calm sentence, no jargon. */
export function bootstrapRescueNote(r: Record<string, unknown>): string | null {
  const n = bootstrapRescuedCount(r);
  if (n <= 0) return null;
  return n === 1
    ? "Located 1 more sub by combining your un-located frames into a deeper "
      + "image — it's in your stack now."
    : `Located ${n} more subs by combining your un-located frames into a `
      + "deeper image — they're in your stack now.";
}

/** Plain-language outcome of a finished "Quality check & plate-solve" job
 * (pure, tested), or null when the result carries nothing to report.
 *
 * Every other finished job kind states its outcome in plain language; this one
 * used to show a bare "done" unless the stack-then-solve bootstrap happened to
 * engage, so a user who pressed "Check & locate" and waited had no idea what
 * came of it.
 *
 * Honest about the numbers: `solve_done`/`qc_done` are *progress* counters
 * (frames attempted), so a field where every solve failed still finishes with
 * `solve_done === solve_total`. The located figure therefore comes from
 * `solve_ok` — the count of frames that really came back with a usable plate
 * solution — and the whole located clause is omitted on an older backend that
 * doesn't report it, rather than passing off "attempted" as "located". */
export function qcSolveSummary(r: Record<string, unknown>): string | null {
  const n = (v: unknown) => (typeof v === "number" && Number.isFinite(v) ? v : null);
  const qcTotal = n(r.qc_total);
  const solveTotal = n(r.solve_total);
  if (qcTotal == null && solveTotal == null) return null;  // older backend

  const sentences: string[] = [];
  if (qcTotal != null && qcTotal > 0) {
    sentences.push(`Checked ${qcTotal} sub${qcTotal === 1 ? "" : "s"}.`);
  }
  const ok = n(r.solve_ok);
  if (solveTotal != null && solveTotal > 0 && ok != null) {
    const missed = Math.max(0, solveTotal - ok);
    if (missed === 0) {
      sentences.push(solveTotal === 1
        ? "Located it in the sky."
        : `Located all ${solveTotal} of them in the sky.`);
    } else if (ok > 0) {
      sentences.push(`Located ${ok} of ${solveTotal} in the sky — ${missed} `
        + "couldn't be placed.");
    } else {
      sentences.push(solveTotal === 1
        ? "It couldn't be placed in the sky."
        : `None of the ${solveTotal} could be placed in the sky.`);
    }
  }
  if (!sentences.length) {
    // Everything had already been checked and located: a real, reassuring
    // outcome rather than a bare "done".
    return "Everything was already checked and located — nothing new to do.";
  }
  return sentences.join(" ");
}

/** The follow-up guidance for a Check & locate job that left a lot of subs
 * un-located, or null when there's nothing worth saying (pure, tested).
 *
 * An un-located sub can't stack, so a mostly-failed solve is the single most
 * common reason a beginner's picture stays thin and noisy — and the app already
 * has the cure (the opt-in deep-image rescue). Only speaks up when the miss rate
 * is high enough to actually be the problem; a couple of stragglers on an
 * otherwise good night are normal and get no lecture. Stays silent when the
 * bootstrap already rescued them — that note says its own piece. */
export function qcSolveNudge(r: Record<string, unknown>): string | null {
  const total = typeof r.solve_total === "number" ? r.solve_total : 0;
  const ok = typeof r.solve_ok === "number" ? r.solve_ok : null;
  if (ok == null || total <= 0) return null;
  const missed = Math.max(0, total - ok);
  if (missed === 0 || missed < total / 2) return null;
  if (bootstrapRescuedCount(r) > 0) return null;
  return "Subs that can't be placed in the sky are left out of your stack. "
    + "This is usual on a faint or star-poor target — turning on "
    + "\"Rescue faint fields with a deep-image solve\" in Settings lets the app "
    + "locate them together instead of one at a time.";
}

/** How many subs auto-grade *put back* in this job result, or 0 when it gave
 * none back (pure, tested).
 *
 * Auto-grade reconsiders its own earlier rejections on every re-grade: a sub it
 * dropped against a small, noisy population stops being an outlier once the rest
 * of the night arrives, and gets re-accepted. Single-target jobs (`qc_solve`,
 * `process_target`) carry a plain count; the whole-library scan reports a
 * per-target map. Both shapes are read here so one helper covers every surface. */
export function autoRegradedBackCount(r: Record<string, unknown>): number {
  const v = r.auto_regraded_back;
  if (v && typeof v === "object") {
    return Math.max(0, Object.values(v as Record<string, unknown>)
      .reduce<number>((sum, n) => sum + (Number(n) || 0), 0));
  }
  return Math.max(0, Number(v ?? 0) || 0);
}

/** The plain-language note for that re-accept, or null when nothing came back.
 *
 * The app says so when auto-grade takes a sub away ("auto-grade dropped 3"), so
 * it should say so when it gives one back — otherwise the frame simply
 * reappears and the counts the user remembers stop adding up. */
export function autoRegradedBackNote(r: Record<string, unknown>): string | null {
  const n = autoRegradedBackCount(r);
  if (n <= 0) return null;
  return n === 1
    ? "Put 1 sub back: with more of your night to compare against, it's no "
      + "longer an outlier."
    : `Put ${n} subs back: with more of your night to compare against, they're `
      + "no longer outliers.";
}

/** Plain-language outcome of a finished "Build master" job (pure, tested). A
 * beginner building a master from a Dark/Flat folder should see how many of
 * their frames were actually combined — and, when some were set aside (wrong
 * size / unreadable), how many and why — rather than a bare "done" hiding a
 * silently smaller master. */
export function buildMasterSummary(r: Record<string, unknown>): string {
  const kind = typeof r.kind === "string" && r.kind ? r.kind : "master";
  const n = Number(r.n_frames ?? 0) || 0;
  const skipped = Number(r.n_skipped ?? 0) || 0;
  // A very large dark/flat set is evenly sampled down to a memory bound before
  // combining. That's a sound default, but it was only ever written to the log —
  // so someone who dropped 200 darks read "built from 64 frames" and reasonably
  // concluded 136 had failed. Say it, and say it as sufficiency rather than
  // loss: the frames weren't wasted, they just weren't needed.
  const supplied = Number(r.n_supplied ?? 0) || 0;
  const sampled = supplied > n + skipped;
  let line = sampled
    ? `Built a master ${kind} from ${n} of the ${supplied} frames you gave`
      + " (evenly sampled across the whole set — plenty for a clean master)"
    : `Built a master ${kind} from ${n} frame${n === 1 ? "" : "s"}`;
  if (skipped > 0) {
    const buckets = r.skipped_buckets && typeof r.skipped_buckets === "object"
      ? (r.skipped_buckets as Record<string, unknown>) : {};
    const parts = Object.entries(buckets)
      .filter(([, c]) => (Number(c) || 0) > 0)
      .map(([reason, c]) => `${Number(c)} ${reason}`);
    const detail = parts.length ? ` (${parts.join(", ")})` : "";
    line += ` · ${skipped} frame${skipped === 1 ? "" : "s"} set aside${detail}`;
  }
  return `${line}.`;
}

/** One target the walk-away auto-stack is holding back because too few of its
 * subs have been located (plate-solved) to make anything but single-frame
 * speckle — the `auto_stack_held_thin` entries the pipeline job records. */
export interface HeldForSubs { target: string; frames: number; min: number; }

/** One target the walk-away auto-stack is holding back because some of its subs
 * have **no file on disk right now** — a share that unmounted, a drive that
 * dropped out, a folder moved or archived mid-session. Stacking without them
 * would quietly publish a thinner, noisier picture than the one the target
 * already has, so the scan holds off and retries once the files come back
 * (`auto_stack_held_unreadable`). */
export interface HeldForFiles {
  target: string; offered: number; readable: number; unreadable: number;
}

/** One target the scan re-stacked because its newest picture had come out much
 * thinner than one the same target already made — the state a storage hiccup
 * leaves behind — and all of its subs are readable again
 * (`auto_stack_healed`). */
export interface HealedThin {
  target: string; frames: number; newest: number; best: number;
}

/** Plain-language outcome of a finished "Importing & processing new frames"
 * (`pipeline`) scan job (pure, tested). A hands-off scan otherwise shows a bare
 * "done" with no hint of what it did — how many frames came in, how many targets
 * it auto-stacked, and (the part that used to be invisible) which targets it
 * *held back* for more located subs rather than publish as noise. Surfacing the
 * held-back state is the Jobs-page half of the v0.183.0 minimum-frames guard:
 * the Target page already explains the wait per target, but a beginner who kicks
 * off a scan and watches Jobs had no signal there. */
export function pipelineSummary(r: Record<string, unknown>): {
  line: string; held: HeldForSubs[]; heldFiles: HeldForFiles[]; healed: HealedThin[];
} {
  const scanned = Number(r.scanned ?? 0) || 0;
  const stacked = Array.isArray(r.auto_stacked) ? r.auto_stacked.length : 0;
  const autoEdited = Number(r.auto_edited ?? 0) || 0;
  const held: HeldForSubs[] = Array.isArray(r.auto_stack_held_thin)
    ? (r.auto_stack_held_thin as unknown[])
        .filter((h): h is Record<string, unknown> => !!h && typeof h === "object")
        .map((o) => ({
          target: typeof o.target === "string" ? o.target : "",
          frames: Number(o.frames ?? 0) || 0,
          min: Number(o.min ?? 0) || 0,
        }))
    : [];
  const heldFiles: HeldForFiles[] = Array.isArray(r.auto_stack_held_unreadable)
    ? (r.auto_stack_held_unreadable as unknown[])
        .filter((h): h is Record<string, unknown> => !!h && typeof h === "object")
        .map((o) => ({
          target: typeof o.target === "string" ? o.target : "",
          offered: Number(o.offered ?? 0) || 0,
          readable: Number(o.readable ?? 0) || 0,
          unreadable: Number(o.unreadable ?? 0) || 0,
        }))
    : [];
  const healed: HealedThin[] = Array.isArray(r.auto_stack_healed)
    ? (r.auto_stack_healed as unknown[])
        .filter((h): h is Record<string, unknown> => !!h && typeof h === "object")
        .map((o) => ({
          target: typeof o.target === "string" ? o.target : "",
          frames: Number(o.frames ?? 0) || 0,
          newest: Number(o.newest ?? 0) || 0,
          best: Number(o.best ?? 0) || 0,
        }))
    : [];
  // Failed targets across both unattended passes (QC/solve + auto-stack).
  const countErrs = (v: unknown) =>
    v && typeof v === "object" ? Object.keys(v as object).length : 0;
  const errors = countErrs(r.stack_errors) + countErrs(r.qc_errors);

  const clauses: string[] = [
    scanned > 0 ? `Imported ${scanned} new frame${scanned === 1 ? "" : "s"}` : "No new frames",
  ];
  if (stacked > 0) clauses.push(`auto-stacked ${stacked} target${stacked === 1 ? "" : "s"}`);
  if (autoEdited > 0) {
    clauses.push(`finished ${autoEdited} into ${autoEdited === 1 ? "a picture" : "pictures"}`);
  }
  if (held.length > 0) clauses.push(`held ${held.length} for more subs`);
  if (heldFiles.length > 0) {
    clauses.push(`held ${heldFiles.length} — some subs aren't on disk`);
  }
  if (healed.length > 0) {
    clauses.push(
      `re-made ${healed.length} picture${healed.length === 1 ? "" : "s"} that came out thin`);
  }
  if (errors > 0) clauses.push(`${errors} couldn't finish`);
  return { line: `${clauses.join(" · ")}.`, held, heldFiles, healed };
}

/** Result-specific actions for finished editor jobs (download / view). */
function JobResultActions({ job }: { job: Job }) {
  if (job.state !== "done" || !job.result) return null;
  const r = job.result as Record<string, unknown>;
  if (job.kind === "process_target") {
    const { line, stacked, thin, cleaned, storage, calMismatch } =
      processTargetSummary(r);
    // Deep-link straight to the finished run's editor when we know its id
    // (v0.85.3+ backend); fall back to the target's History on an older backend.
    const stack = r.stack && typeof r.stack === "object"
      ? (r.stack as Record<string, unknown>) : {};
    const runId = stacked && typeof stack.run_id === "number" ? stack.run_id : null;
    const to = !job.target
      ? null
      : !stacked
        ? `/targets/${job.target}`
        : runId != null
          ? `/targets/${job.target}/edit/${runId}`
          : `/targets/${job.target}/history`;
    const rescue = bootstrapRescueNote(r);
    const putBack = autoRegradedBackNote(r);
    return (
      <Stack gap={4} mt="xs">
        <Text size="sm">{line}</Text>
        {/* Credit the stack-then-solve rescue where the result lands, so a
            suddenly-thicker stack has a visible cause. */}
        {rescue ? <Text size="xs" c="dimmed">{rescue}</Text> : null}
        {/* The other half of "auto-grade dropped N": say when it handed subs
            back, so the numbers the user remembers keep adding up. */}
        {putBack ? <Text size="xs" c="dimmed">{putBack}</Text> : null}
        {thin ? (
          <Alert color={thin.level === "single" ? "orange" : "yellow"} p="xs"
            title="Very few frames stacked">
            <Text size="xs">{thin.message}</Text>
          </Alert>
        ) : null}
        {/* Names a storage problem as a storage problem — otherwise a cleared
            cache over an offline share just looks like a mysteriously thin
            stack. Shown above the reassuring notes because it's actionable, and
            deliberately ONE alert: a flaking drive produces both the
            missing-file and the failed-read counts, and two stacked yellow
            blocks that both end in "go check the drive" read as two problems. */}
        {storage ? (
          <Alert color="yellow" p="xs" title={storage.title}>
            <Text size="xs">{storage.message}</Text>
          </Alert>
        ) : null}
        {/* The opposite of the skipped-master note below: a master that *was*
            applied but doesn't match these subs. The summary line above says the
            stack succeeded, so without this a wrong-exposure dark quietly
            crushing every frame's background reads as a clean run. */}
        {calMismatch ? (
          <Alert color="yellow" p="xs" title="Your master dark doesn't match these subs">
            <Text size="xs">{calMismatch}</Text>
          </Alert>
        ) : null}
        {/* The honest "we quietly removed the trails" trust cue — self-omits on a
            thin stack (warning wins) and when no rejection pass cleaned anything. */}
        {cleaned ? (
          <Text size="xs" c="dimmed">{cleaned}</Text>
        ) : null}
        {/* The satisfying "stacking cut your noise ~N×" payoff, right where the
            finished picture lands (self-omits for a thin stack — small ratio). */}
        {job.target && stacked && runId != null ? (
          <StackNoiseBadge safe={job.target} runId={runId}
            nFrames={Number(stack.n_frames_used ?? 0) || null} />
        ) : null}
        {/* A calibration master the user explicitly saved but this unattended run
            had to drop. The binder is fail-soft by design, so this is the only
            cue the walk-away user gets that their picture is less calibrated than
            they asked for — and this page, not History's Info panel, is where
            they land. Self-hides on a run that skipped nothing. */}
        {job.target && stacked && runId != null ? (
          <CalibrationSkippedNote safe={job.target} runId={runId} />
        ) : null}
        {to ? (
          <Group>
            <Button size="xs" variant="light" leftSection={<IconPhoto size={14} />}
              component={Link} to={to}>
              {stacked ? "View result" : "Open target"}
            </Button>
          </Group>
        ) : null}
      </Stack>
    );
  }
  if (job.kind === "reprocess_all") {
    const { line, failed } = reprocessSummary(r);
    return (
      <Stack gap={2} mt="xs">
        <Text size="sm">{line}</Text>
        {failed.length ? (
          <Text size="xs" c="red">Failed: {failed.join(", ")}</Text>
        ) : null}
      </Stack>
    );
  }
  if (job.kind === "pipeline") {
    const { line, held, heldFiles, healed } = pipelineSummary(r);
    const autoEdited = Number(r.auto_edited ?? 0) || 0;
    const rescue = bootstrapRescueNote(r);
    const putBack = autoRegradedBackNote(r);
    return (
      <Stack gap={4} mt="xs">
        <Text size="sm">{line}</Text>
        {rescue ? <Text size="xs" c="dimmed">{rescue}</Text> : null}
        {putBack ? <Text size="xs" c="dimmed">{putBack}</Text> : null}
        {held.length ? (
          <Alert color="blue" variant="light" p="xs"
            title="Waiting for more of your subs to be located">
            <Text size="xs">
              {held.length === 1
                ? "One target isn't ready to auto-stack yet"
                : `${held.length} targets aren't ready to auto-stack yet`}
              {" — the hands-off auto-stack is holding off rather than making a "}
              {"picture out of one or two frames (that would just be noise). "}
              {"Run Plate Solve to locate more subs, or open the target and use "}
              {'"Stack" to make one now anyway:'}
            </Text>
            <Stack gap={0} mt={4}>
              {held.map((h) => (
                <Text size="xs" key={h.target}>
                  {h.target ? (
                    <Anchor component={Link} to={`/targets/${h.target}`}>{h.target}</Anchor>
                  ) : "This target"}
                  {`: ${h.frames} of your subs located so far — needs ${h.min}.`}
                </Text>
              ))}
            </Stack>
          </Alert>
        ) : null}
        {heldFiles.length ? (
          <Alert color="yellow" variant="light" p="xs"
            title="Some of your subs aren't on disk right now">
            <Text size="xs">
              {"Stacking without them would have made a thinner, noisier picture "}
              {"than the one you already have, so it was left alone. This usually "}
              {"means a drive or network share went off-line, or a folder was "}
              {"moved. Put it back and the next scan will stack the full set "}
              {"automatically — nothing has been lost:"}
            </Text>
            <Stack gap={0} mt={4}>
              {heldFiles.map((h) => (
                <Text size="xs" key={h.target}>
                  {h.target ? (
                    <Anchor component={Link} to={`/targets/${h.target}`}>{h.target}</Anchor>
                  ) : "This target"}
                  {`: ${h.unreadable} of ${h.offered} subs couldn't be read `}
                  {`(${h.readable} still readable).`}
                </Text>
              ))}
            </Stack>
          </Alert>
        ) : null}
        {healed.length ? (
          <Alert color="green" variant="light" p="xs"
            title="Re-made a picture that had come out thin">
            <Text size="xs">
              {"All of these subs are readable again, and the newest picture had "}
              {"been made from far fewer of them than this target managed before "}
              {"— usually because a drive or share was off-line at the time. It "}
              {"was stacked again from the full set, so the better picture is "}
              {"back. Your earlier pictures are all still in History:"}
            </Text>
            <Stack gap={0} mt={4}>
              {healed.map((h) => (
                <Text size="xs" key={h.target}>
                  {h.target ? (
                    <Anchor component={Link} to={`/targets/${h.target}`}>{h.target}</Anchor>
                  ) : "This target"}
                  {`: last picture used ${h.newest} subs, this one used all ${h.frames} `}
                  {`(its best before was ${h.best}).`}
                </Text>
              ))}
            </Stack>
          </Alert>
        ) : null}
        {autoEdited > 0 ? (
          <Group>
            <Button size="xs" variant="light" leftSection={<IconPhoto size={14} />}
              component={Link} to="/gallery">
              View in Gallery
            </Button>
          </Group>
        ) : null}
      </Stack>
    );
  }
  if (job.kind === "qc_solve") {
    // A Check/Plate-solve job used to finish with a bare "done" unless the
    // stack-then-solve bootstrap happened to engage. Lead with what the job
    // actually did (checked N, located M), then the rescue — the user ran this
    // *because* subs weren't located, so "12 more are located now" is the answer
    // they came for — then the guidance when most subs still couldn't be placed.
    const summary = qcSolveSummary(r);
    const rescue = bootstrapRescueNote(r);
    const putBack = autoRegradedBackNote(r);
    const nudge = qcSolveNudge(r);
    if (!summary && !rescue && !putBack) return null;
    return (
      <Stack gap={2} mt="xs">
        {summary ? <Text size="sm">{summary}</Text> : null}
        {rescue ? <Text size="sm">{rescue}</Text> : null}
        {putBack ? <Text size="sm">{putBack}</Text> : null}
        {nudge ? (
          <>
            <Text size="xs" c="dimmed">{nudge}</Text>
            {/* The nudge names a switch; this is the way to it, rather than
                leaving the reader to find which Settings page holds it. */}
            <Anchor component={Link} to={settingsLink("plate-solving")} size="xs" fw={500}>
              Turn it on in Settings &rarr; Plate solving &rarr;
            </Anchor>
          </>
        ) : null}
      </Stack>
    );
  }
  if (job.kind === "build_master") {
    const skipped = Number(r.n_skipped ?? 0) || 0;
    return (
      <Stack gap={4} mt="xs">
        <Text size="sm" c={skipped > 0 ? "orange" : undefined}>
          {buildMasterSummary(r)}
        </Text>
        <Group>
          <Button size="xs" variant="light" leftSection={<IconFlask size={14} />}
            component={Link} to="/calibration">
            View masters
          </Button>
        </Group>
      </Stack>
    );
  }
  let action: ReactNode = null;
  if (job.kind === "editor_png" && r.png_path && r.safe && r.run_id != null) {
    action = (
      <Button size="xs" variant="light" leftSection={<IconDownload size={14} />}
        component="a" href={api.editPngUrl(String(r.safe), Number(r.run_id), job.id)}>
        Download PNG
      </Button>
    );
  } else if (job.kind === "editor_export" && r.safe) {
    action = (
      <Button size="xs" variant="light" leftSection={<IconPhoto size={14} />}
        component={Link} to={`/targets/${r.safe}/history`}>
        View result
      </Button>
    );
  } else if (job.kind === "editor_batch") {
    const n = Array.isArray(r.exported) ? r.exported.length : 0;
    action = (
      <Button size="xs" variant="light" leftSection={<IconPhoto size={14} />}
        component={Link} to="/gallery">
        View {n} in Gallery
      </Button>
    );
  }
  return action ? <Group mt="xs">{action}</Group> : null;
}

/** A failed job's error, translated to plain language where we recognise it. */
function JobError({ raw, kind }: { raw: string; kind?: string | null }) {
  const { message, next, action } = friendlyJobError(raw, kind);
  return (
    <>
      <Text c="red" size="sm" mt="xs">{message}</Text>
      {next ? <Text c="dimmed" size="xs" mt={2}>{next}</Text> : null}
      {action ? (
        <Anchor component={Link} to={action.href} size="xs" fw={500}>{action.label}</Anchor>
      ) : null}
    </>
  );
}

export function JobRow(
  { job, onCancel, eta }: { job: Job; onCancel: () => void; eta?: string | null },
) {
  const pct = job.total ? Math.round((job.done / job.total) * 100) : 0;
  const active = job.state === "running" || job.state === "queued";
  return (
    <Paper withBorder p="md">
      <Group justify="space-between">
        <Group>
          <Badge color={COLOR[job.state] ?? "gray"}>{job.state}</Badge>
          <Text fw={500}>{jobKindLabel(job.kind)}</Text>
          {job.target ? <Text c="dimmed" size="sm">{job.target}</Text> : null}
        </Group>
        <Group>
          <Text size="sm" c="dimmed">
            {job.phase} {job.total ? `${job.done}/${job.total}` : ""}
            {/* Per-step "time left" — shown next to this step's count so it reads
                unambiguously as the current step, not the whole job. */}
            {job.state === "running" && eta ? ` · ${eta}` : ""}
          </Text>
          {active ? (
            <ActionIcon variant="subtle" color="red" onClick={onCancel} aria-label="Cancel job">
              <IconX size={16} />
            </ActionIcon>
          ) : null}
        </Group>
      </Group>
      {active ? <Progress value={job.state === "queued" ? 0 : pct} animated mt="xs" /> : null}
      {job.error ? <JobError raw={job.error} kind={job.error_kind} /> : null}
      {job.detail ? <Text c="dimmed" size="xs" mt={4}>{job.detail}</Text> : null}
      <JobResultActions job={job} />
    </Paper>
  );
}

// Per-job "time left" for the running jobs. We can't estimate this whole-job
// (each step restarts its own done/total — see jobEta.ts), so we anchor on the
// first observation of the *current* step and project from the rate since then.
// The anchors persist across the 1.5 s poll in a ref (a display cache, not
// render-affecting state); finished jobs are pruned so it can't grow unbounded.
function useJobEtas(jobs: Job[]): Record<string, string | null> {
  const store = useRef<Map<string, { anchor: EtaSample; cur: EtaSample }>>(new Map());
  const now = Date.now();
  const out: Record<string, string | null> = {};
  const live = new Set<string>();
  for (const j of jobs) {
    if (j.state !== "running") continue;
    live.add(j.id);
    const obs = { phase: j.phase ?? "", total: j.total ?? 0, done: j.done ?? 0 };
    const rec = store.current.get(j.id);
    // Reuse the stored observation timestamp while nothing has changed, so the
    // estimate doesn't drift upward on re-renders between polls.
    const cur: EtaSample =
      rec && rec.cur.phase === obs.phase && rec.cur.total === obs.total && rec.cur.done === obs.done
        ? rec.cur
        : { ...obs, tMs: now };
    const anchor = updateEtaAnchor(rec ? rec.anchor : null, cur);
    store.current.set(j.id, { anchor, cur });
    out[j.id] = etaLabel(anchor, cur);
  }
  for (const id of [...store.current.keys()]) {
    if (!live.has(id)) store.current.delete(id);
  }
  return out;
}

/** The "Notify me when done" opt-in toggle.
 *
 * This only owns the switch state + the permission request; the actual
 * notification firing lives in the always-mounted `GlobalJobNotifier` (App.tsx),
 * so a job pings regardless of which page is open — and, being the single firing
 * site, a job can never double-notify. The toggle persists to localStorage, which
 * the global watcher reads fresh each poll, so flipping it here takes effect
 * app-wide with no shared React state. */
function useJobFinishNotifications() {
  const [enabled, setEnabled] = useState(isJobNotifyEnabled);

  const toggle = async (on: boolean) => {
    if (!on) {
      setJobNotifyEnabled(false);
      setEnabled(false);
      return;
    }
    const perm = await requestNotificationPermission();
    if (perm === "granted") {
      setJobNotifyEnabled(true);
      setEnabled(true);
    } else {
      setJobNotifyEnabled(false);
      setEnabled(false);
      notifications.show({
        color: "gray",
        message: perm === "unsupported"
          ? "This browser doesn't support desktop notifications."
          : "Your browser blocked notifications — allow them for this site to get a ping when a job finishes.",
      });
    }
  };

  return { enabled, toggle, supported: notificationsSupported() };
}

export function JobsView() {
  const qc = useQueryClient();
  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: ["jobs"],
    // Wrap so the default limit applies — a bare `api.listJobs` would receive
    // TanStack's query context as its `limit` argument.
    queryFn: () => api.listJobs(),
    refetchInterval: 1500,
  });
  const notify = useJobFinishNotifications();
  const cancel = useMutation({
    mutationFn: (id: string) => api.cancelJob(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["jobs"] }),
    onError: (e: Error) => notifications.show({ message: e.message, color: "red" }),
  });
  const clear = useMutation({
    mutationFn: () => api.clearJobs(),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["jobs"] }),
  });
  const finished = (data ?? []).filter(
    (j) => !["running", "queued"].includes(j.state),
  ).length;
  // Computed every render (before the early returns) so the hook order is stable.
  const etas = useJobEtas(data ?? []);

  if (isError && !data) {
    return <QueryError error={error} onRetry={() => refetch()} />;
  }
  if (isLoading) {
    return (
      <Center h={300}>
        <Loader />
      </Center>
    );
  }

  const jobs = data ?? [];

  return (
    <Stack>
      <Group justify="space-between">
        <Title order={2}>Jobs</Title>
        <Group gap="md">
          {notify.supported ? (
            <Tooltip
              label="Get a desktop notification when a job finishes, so you can switch tabs while it runs."
              multiline w={240} withArrow
            >
              <Switch
                size="sm"
                checked={notify.enabled}
                onChange={(e) => { void notify.toggle(e.currentTarget.checked); }}
                label="Notify me when done"
              />
            </Tooltip>
          ) : null}
          {finished > 0 ? (
            <Button size="xs" variant="subtle" color="gray" loading={clear.isPending}
              onClick={() => clear.mutate()}>
              Clear all finished
            </Button>
          ) : null}
        </Group>
      </Group>
      {jobs.length === 0 ? (
        <Paper withBorder p="xl">
          <Stack align="center" gap="sm">
            <IconActivity size={40} color="var(--mantine-color-dark-3)" />
            <Text c="dimmed">No jobs running.</Text>
            <Text c="dimmed" size="sm" ta="center" maw={420}>
              Click “Scan incoming” in the header to import and process your Seestar
              frames — ingest, quality check and plate-solve run here as jobs. No NAS
              share? <Anchor component={Link} to="/library">Upload FITS files</Anchor> from your
              computer in the Library instead.
            </Text>
          </Stack>
        </Paper>
      ) : (
        jobs.map((j) => (
          <JobRow key={j.id} job={j} onCancel={() => cancel.mutate(j.id)} eta={etas[j.id]} />
        ))
      )}
    </Stack>
  );
}
