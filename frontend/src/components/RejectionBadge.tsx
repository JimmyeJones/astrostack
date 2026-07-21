import { Badge, Tooltip } from "@mantine/core";

// A stack can be combined one of four ways, recorded in the run's stored
// options (and mirrored in the STACKER FITS card): a plain mean, κ-σ
// (sigma-clip) rejection, min/max (extremes) rejection, or drizzle. This badge
// lets a user see at a glance *how* each result was combined when comparing
// runs, complementing the calibration and noise chips.

/** Format an option value for a badge label (round non-integer floats). */
function num(v: unknown): string {
  if (typeof v === "number") return Number.isInteger(v) ? String(v) : v.toFixed(1);
  return String(v ?? "");
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
        ? "Combined with drizzle (with κ-σ outlier rejection): sub-pixel resampling onto a finer grid, rejecting satellites, planes and cosmic rays."
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
    return {
      label: k > 1 ? `min-max ×${k}` : "min-max",
      title: (k > 1
        ? `Combined by dropping the ${k} highest and ${k} lowest values at each pixel before averaging — removes several satellite / plane trails crossing one pixel across a session.`
        : "Combined by dropping the single highest and lowest value at each pixel before averaging — removes a lone satellite / plane trail on small stacks where κ-σ can't.") + autoNote,
    };
  }
  if (options.sigma_clip) {
    return {
      label: `σ-clip κ${num(options.sigma_kappa ?? 3)}`,
      title:
        "Combined with κ-σ rejection: at each pixel, values beyond κ standard deviations of the mean are rejected before averaging." + autoNote,
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
    <Tooltip label={info.title} multiline w={280}>
      <Badge color="violet" variant="light" size={size}>
        {info.label}
      </Badge>
    </Tooltip>
  );
}
