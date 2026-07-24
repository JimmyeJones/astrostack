// Turns the backend's structured stack-memory `memory_fix` into a one-click
// action for the Stack form: the button label (naming the lever and the memory
// the run lands at) plus which StackOption to set. Kept pure and separate so it
// can be unit-tested and so the pre-submit button stays worded consistently with
// the run-time refusal message (both derive from the same engine `MemoryFix`).

export interface MemoryFixInfo {
  kind: "drizzle_scale" | "reduce_outlier_passes" | "reference_canvas";
  value: number | null;
  peak_bytes: number;
  peak_gb: number;
}

export interface MemoryFixAction {
  label: string; // button text, including the resulting peak ("fits at ~X GB")
  optionKey: string; // the StackOptions form key to change
  optionValue: unknown; // the value to set it to
}

function fitsAt(peakGb: number): string {
  return `fits at ~${peakGb.toFixed(peakGb < 1 ? 2 : 1)} GB`;
}

/**
 * Map a `memory_fix` payload to a single one-click action, or null when there is
 * no actionable fix. Covers all three levers the engine surfaces — the smaller
 * drizzle scale, dropping the extra min/max outlier passes, and cropping a mosaic
 * to its reference canvas — always naming the memory the run would land at.
 */
export function memoryFixAction(fix: MemoryFixInfo | null | undefined): MemoryFixAction | null {
  if (!fix) return null;
  const fits = fitsAt(fix.peak_gb);
  switch (fix.kind) {
    case "drizzle_scale":
      if (fix.value == null) return null;
      return {
        label: `Use drizzle ×${fix.value} instead — ${fits}`,
        optionKey: "drizzle_scale",
        optionValue: fix.value,
      };
    case "reduce_outlier_passes":
      return {
        label: `Lower Extra outlier passes to 1 — ${fits}`,
        optionKey: "min_max_reject_count",
        optionValue: 1,
      };
    case "reference_canvas":
      return {
        label: `Use the reference canvas instead — ${fits}`,
        optionKey: "mosaic_canvas",
        optionValue: "reference",
      };
    default:
      return null;
  }
}
