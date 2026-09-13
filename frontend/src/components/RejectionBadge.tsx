import { Badge } from "@mantine/core";

import { kappaMinFrames } from "../kappaMinFrames";

import { HintAnchor } from "./HintAnchor";

// A stack can be combined one of four ways, recorded in the run's stored
// options (and mirrored in the STACKER FITS card): a plain mean, κ-σ
// (sigma-clip) rejection, min/max (extremes) rejection, or drizzle. This badge
// lets a user see at a glance *how* each result was combined when comparing
// runs, complementing the calibration and noise chips.
//
// **Every rejection pass has a per-pixel depth below which it removes nothing,
// and this chip used to promise protection without mentioning any of them**
// (corrected 2026-09-13). v0.422.1 established the rule and fixed the surfaces
// that make a *verdict* about one run — the Stack form's pre-run caution
// (`rejection_reach`), the finished picture's `rejection_blind` note, and the
// `REJNEED`/`REJREACH` cards in the master's own header. This chip is not one
// of those: it renders in a *list*, from the run's stored options alone, with
// no depth to judge against — so it states the method's **rule** instead of a
// verdict about the run. A rule is true of every run, needs no data, and can
// never contradict the header's own answer sitting on the same card.
//
// The three bounds, all of them `seestack.stack.stacker.lone_outlier_min_depth`:
// a min/max trim of k needs `2k+1` samples on a pixel to have that many to
// spare (below 3 `MinMaxRejectAccumulator` falls through to a plain mean of
// whatever covered the pixel); κ-σ tests each sample against statistics that
// still include it, so a *lone* trail only stands out from `kappa_min_frames`
// samples up (11 at the default κ=3); and drizzle's two-pass clip is the same
// κ·σ test with the same κ, so it shares that bound exactly. On a mosaic every
// one of those counts is the subs on **one panel**, not the target's total —
// which is the owner's case, and why the sentences say so.

/** Format an option value for a badge label (round non-integer floats). */
function num(v: unknown): string {
  if (typeof v === "number") return Number.isInteger(v) ? String(v) : v.toFixed(1);
  return String(v ?? "");
}

/** The κ a run's κ-σ (or drizzle) clip used, from its stored options.
 *
 * Falls back to the app default for an absent or unreadable value, exactly as
 * `seestack.stackhealth._run_sigma_kappa` does and for its stated reason — the
 * figure this feeds is advisory, so a sensible default beats saying nothing —
 * and matching the label right beside it, which has always printed `κ3` for a
 * run with no stored κ. */
function runKappa(options: Record<string, unknown>): number {
  const k = options.sigma_kappa;
  return typeof k === "number" && Number.isFinite(k) && k > 0 ? k : 3;
}

/** "…a lone trail only stands out from about N subs on one pixel", the κ-σ
 * bound in words. Shared by the κ-σ and drizzle branches because they share the
 * bound (`lone_outlier_min_depth`), so one clip cannot be described two ways. */
function kappaReachSentence(options: Record<string, unknown>): string {
  const need = kappaMinFrames(runKappa(options));
  const howMany = need == null ? "enough subs overlap" : `about ${need} subs overlap`;
  return (
    ` A lone trail is tested against statistics that still include it, so it only`
    + ` stands out far enough to be clipped once ${howMany} on one pixel — on a`
    + " mosaic that's the subs on one panel, not the total."
  );
}

export interface RejectionInfo {
  label: string;
  title: string;
}

// Derive the *effective* combine method from a run's stored options, matching
// the engine's precedence (drizzle > min/max reject > sigma-clip > mean). Returns
// null for a plain mean (no per-pixel rejection) and for editor-recipe /
// channel-combine runs, which carry no stacking knobs — so the badge can be
// dropped in unconditionally and simply renders nothing when it doesn't apply.
export function rejectionBadge(options?: Record<string, unknown> | null): RejectionInfo | null {
  if (!options || typeof options !== "object") return null;
  if ("channel_combine" in options || "editor_recipe" in options) return null;
  if (options.drizzle) {
    return {
      label: `drizzle ×${num(options.drizzle_scale ?? 1)}`,
      title: options.drizzle_reject
        ? "Combined with drizzle (with κ-σ outlier rejection): sub-pixel resampling"
          + " onto a finer grid, rejecting satellites, planes and cosmic rays."
          + kappaReachSentence(options)
        : "Combined with drizzle: sub-pixel resampling onto a finer grid. No per-pixel outlier rejection unless drizzle rejection was enabled.",
    };
  }
  // When "Auto outlier removal" picked the method, the run stores auto_reject
  // alongside the resolved sigma_clip/min_max_reject, so note that in the tooltip.
  const autoNote = options.auto_reject
    ? " Auto outlier removal picked this from your number of subs."
    : "";
  if (options.min_max_reject) {
    // The default single drop shows as "min-max"; a top/bottom-k trim (k>1)
    // shows the count, e.g. "min-max ×3" for dropping the 3 highest and lowest.
    const k = typeof options.min_max_reject_count === "number"
      ? Math.max(1, Math.round(options.min_max_reject_count)) : 1;
    // …and the drop has a depth of its own: it needs `2k+1` samples on a pixel
    // to have k highest and k lowest to spare. Below that the accumulator
    // averages in whatever covered the pixel, so the guarantee above is simply
    // not in force there — which on a mosaic part-way through its panels is a
    // real part of the canvas, not a corner case.
    const need = 2 * k + 1;
    return {
      label: k > 1 ? `min-max ×${k}` : "min-max",
      title: (k > 1
        ? `Combined by dropping the ${k} highest and ${k} lowest values at each pixel before averaging — removes several satellite / plane trails crossing one pixel across a session.`
        : "Combined by dropping the single highest and lowest value at each pixel before averaging — removes a lone satellite / plane trail on small stacks where κ-σ can't.")
        + autoNote
        + ` It needs ${need} subs on a pixel to have that many to spare; anywhere`
        + " fewer overlap — a mosaic panel still part-shot — those samples are"
        + " averaged in as they are.",
    };
  }
  if (options.sigma_clip) {
    return {
      label: `σ-clip κ${num(options.sigma_kappa ?? 3)}`,
      title:
        "Combined with κ-σ rejection: at each pixel, values beyond κ standard deviations of the mean are rejected before averaging."
        + autoNote + kappaReachSentence(options),
    };
  }
  return null;
}

// A coarse, stable combine-method key for a run's stored options — the same
// precedence as rejectionBadge (drizzle > min/max > σ-clip > mean) but collapsed
// to a fixed set so it can drive a filter facet. Returns null for editor-recipe /
// channel-combine runs (no stacking knobs), which are simply excluded from the
// facet. Unlike rejectionBadge it returns "mean" (not null) for a plain average,
// so a mean stack is a filterable category.
export type CombineMethod = "drizzle" | "min-max" | "sigma-clip" | "mean";

export const COMBINE_METHOD_LABELS: Record<CombineMethod, string> = {
  drizzle: "Drizzle",
  "min-max": "Min/max",
  "sigma-clip": "σ-clip",
  mean: "Mean",
};

export function combineMethodKey(
  options?: Record<string, unknown> | null,
): CombineMethod | null {
  if (!options || typeof options !== "object") return null;
  if ("channel_combine" in options || "editor_recipe" in options) return null;
  if (options.drizzle) return "drizzle";
  if (options.min_max_reject) return "min-max";
  if (options.sigma_clip) return "sigma-clip";
  return "mean";
}

// Small violet chip for History / Gallery cards showing the combine method.
export function RejectionBadge({
  options,
  size = "xs",
}: {
  options?: Record<string, unknown> | null;
  size?: string;
}) {
  const info = rejectionBadge(options);
  if (!info) return null;
  return (
    <HintAnchor label={info.title} multiline w={280}>
      <Badge color="violet" variant="light" size={size}>
        {info.label}
      </Badge>
    </HintAnchor>
  );
}
