import { Badge, Tooltip } from "@mantine/core";

// A run whose median transparency sits well below the target's clear-sky
// baseline was shot through haze / thin cloud. Same threshold as the Stack
// form's pre-run hint, so a browsed run carries the same verdict at a glance.
export const HAZY_RATIO = 0.6;

export function isHazy(ratio?: number | null): boolean {
  return typeof ratio === "number" && ratio > 0 && ratio < HAZY_RATIO;
}

// Small "Hazy night" badge for History / Gallery cards. Renders nothing unless
// the run's transparency_ratio marks it as hazy, so it's safe to drop in
// unconditionally.
export function HazyNightBadge({ ratio, size = "xs" }: { ratio?: number | null; size?: string }) {
  if (!isHazy(ratio)) return null;
  const pctBelow = Math.round((1 - (ratio as number)) * 100);
  return (
    <Tooltip
      label={`Shot through haze — median transparency ~${pctBelow}% below this target's clearest nights. Quality weighting or rejecting the haziest subs can help.`}
      multiline
      w={260}
    >
      <Badge color="orange" variant="light" size={size}>
        Hazy night
      </Badge>
    </Tooltip>
  );
}
