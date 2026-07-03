/** Neutral ("identity") values for the Levels op: black at 0, white at 1, and
 * gamma (midtones) at 1 leave the tones untouched. A beginner who over-drags the
 * black/white/gamma sliders needs a one-click way back to this, symmetric with
 * the header's "Auto levels" (which *sets* data-driven points). */
export const LEVELS_IDENTITY = { black: 0, white: 1, gamma: 1 } as const;

/** True when the Levels params already sit at the neutral identity, so the
 * "Reset points" action can dim rather than invite a no-op click. */
export function levelsAtIdentity(params: Record<string, unknown> | undefined | null): boolean {
  const p = params ?? {};
  return Number(p.black ?? 0) === 0
    && Number(p.white ?? 1) === 1
    && Number(p.gamma ?? 1) === 1;
}

/** Return a copy of the Levels params with black/white/gamma reset to identity,
 * preserving any other params the op may carry. */
export function resetLevelsPoints(
  params: Record<string, unknown> | undefined | null,
): Record<string, unknown> {
  return { ...(params ?? {}), ...LEVELS_IDENTITY };
}
