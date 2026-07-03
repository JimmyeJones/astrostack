/** True when a param's current value already equals a data-driven suggestion
 * (within half the control's step, so the "From your data" button can read as
 * "already applied" rather than inviting a no-op click). A null/absent step
 * falls back to a tiny epsilon (exact match). Non-numeric current values (unset,
 * strings) never match, so the button stays active. */
export function matchesSuggestion(
  current: unknown,
  suggested: number,
  step?: number | null,
): boolean {
  if (typeof current !== "number" || !Number.isFinite(current)) return false;
  const tol = step && step > 0 ? step / 2 : 0;
  return Math.abs(current - suggested) <= tol + 1e-9;
}
