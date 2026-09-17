import { Badge } from "@mantine/core";

import { HintAnchor } from "./HintAnchor";

// A run whose median transparency sits well below the target's clear-sky
// baseline was shot through haze / thin cloud. Same threshold as the Stack
// form's pre-run hint, so a browsed run carries the same verdict at a glance.
//
// The server owns this bar now (`seestack.stackhealth.HAZY_RATIO`) and sends
// the decision as `hazy_verdict`, because it is the only half that can tell a
// hazy night from a **mosaic** panel with a poorer star field on a figure
// written before v0.304.2. This copy is the fallback for a response that
// carries no verdict — an older backend — and stays byte-identical to what it
// always was so such a response behaves exactly as it does today.
export const HAZY_RATIO = 0.6;

export function isHazy(ratio?: number | null): boolean {
  return typeof ratio === "number" && ratio > 0 && ratio < HAZY_RATIO;
}

// Small "Hazy night" badge for History / Gallery cards. Renders nothing unless
// the run's transparency_ratio marks it as hazy, so it's safe to drop in
// unconditionally.
//
// `verdict` is the server's answer and wins whenever the response carries the
// field at all — including when it is `null`, which is the whole point: that is
// how a figure nobody can date says "nothing honest to claim here". Only an
// `undefined` (a backend that predates the field) falls back to reading the
// ratio directly.
export function HazyNightBadge({
  ratio,
  verdict,
  size = "xs",
}: {
  ratio?: number | null;
  verdict?: string | null;
  size?: string;
}) {
  const hazy = verdict === undefined ? isHazy(ratio) : verdict === "hazy";
  if (!hazy) return null;
  // The percentage is a reading of the same figure the verdict was taken from,
  // so it is only offered when there is one; a verdict without a ratio (nothing
  // sends one today, but the two are separate fields) keeps the sentence and
  // drops the number rather than printing "NaN% below".
  const pctBelow = typeof ratio === "number" ? Math.round((1 - ratio) * 100) : null;
  return (
    <HintAnchor
      label={
        pctBelow === null
          ? "Shot through haze — this run's median transparency sits well below this target's clearest nights. Quality weighting or rejecting the haziest subs can help."
          : `Shot through haze — median transparency ~${pctBelow}% below this target's clearest nights. Quality weighting or rejecting the haziest subs can help.`
      }
      multiline
      w={260}
    >
      <Badge color="orange" variant="light" size={size}>
        Hazy night
      </Badge>
    </HintAnchor>
  );
}
