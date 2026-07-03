import { Badge, Text, Tooltip } from "@mantine/core";
import type { StackRun, GalleryItem } from "../api/client";

// The per-run background-noise σ is normalized to the image's own signal range
// (see seestack/edit/noise.estimate_noise_sigma), so it's comparable across
// gain/exposure but has no absolute meaning — lower is cleaner. We surface it as
// a within-target relative number, not a physical magnitude.

export function hasNoise(sigma?: number | null): boolean {
  return typeof sigma === "number" && sigma >= 0;
}

// Small dimmed "Noise 0.021" readout for a History / Gallery card. Renders
// nothing when the run predates the noise column (schema < 6), so it's safe to
// drop in unconditionally.
export function NoiseReadout({ sigma }: { sigma?: number | null }) {
  if (!hasNoise(sigma)) return null;
  return (
    <Tooltip
      label="Background-noise level of this stack, normalized so it's comparable across gain/exposure. Lower = cleaner. Compare several stacks of the same target to find the least noisy."
      multiline
      w={260}
    >
      <Text span size="xs" c="dimmed" style={{ cursor: "help" }}>
        Noise {(sigma as number).toFixed(3)}
      </Text>
    </Tooltip>
  );
}

// Plain-language "−18% noise vs your last stack" readout. `delta` is the
// fractional change in this run's background-noise σ against the same target's
// previous measured stack (negative = cleaner). Renders nothing when there's no
// prior stack to compare against. Green for an improvement, orange for a
// regression, dimmed when it's effectively unchanged. Safe to drop in
// unconditionally with an undefined delta.
export function NoiseDelta({ delta }: { delta?: number }) {
  if (typeof delta !== "number" || !Number.isFinite(delta)) return null;
  const pct = Math.round(delta * 100);
  // Below ~1% either way isn't worth calling a win or a loss.
  const flat = Math.abs(pct) < 1;
  const color = flat ? "dimmed" : delta < 0 ? "teal" : "orange";
  const sign = pct > 0 ? "+" : ""; // Math.round already carries a "−" for negatives.
  const text = flat
    ? "≈ same noise as your last stack"
    : `${sign}${pct}% noise vs your last stack`;
  return (
    <Tooltip
      label="Change in background-noise level compared with this target's previous stack. Negative means this stack is cleaner — a quick way to tell whether adding subs or changing settings actually helped."
      multiline
      w={260}
    >
      <Text span size="xs" c={color} style={{ cursor: "help" }}>
        {text}
      </Text>
    </Tooltip>
  );
}

// Green "Cleanest" badge for the single lowest-noise run among several stacks of
// one target. Renders nothing unless this run is the cleanest, so it's safe to
// drop in unconditionally.
export function CleanestBadge({ isCleanest, size = "xs" }: { isCleanest: boolean; size?: string }) {
  if (!isCleanest) return null;
  return (
    <Tooltip label="Lowest measured background noise of this target's stacks — the cleanest result." multiline w={220}>
      <Badge color="teal" variant="light" size={size}>
        Cleanest
      </Badge>
    </Tooltip>
  );
}

// Id of the run with the lowest noise σ among those that carry one. Returns null
// unless at least two runs have a measured σ (a "cleanest" badge is only
// meaningful as a comparison), so a lone stack is never singled out.
export function cleanestRunId(runs: Array<StackRun | GalleryItem>): number | null {
  const measured = runs.filter((r) => hasNoise(r.noise_sigma));
  if (measured.length < 2) return null;
  let best = measured[0];
  for (const r of measured) {
    if ((r.noise_sigma as number) < (best.noise_sigma as number)) best = r;
  }
  // StackRun carries `id`; GalleryItem carries `run_id`.
  return (best as StackRun).id ?? (best as GalleryItem).run_id;
}
