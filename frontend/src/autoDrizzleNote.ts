import { formatEtaSeconds } from "./jobEta";
import type { AutoDrizzleCost } from "./api/client";

/**
 * "Drizzling ×1.5 — about 14 h (a plain stack would take about 2 h)".
 *
 * An unattended run may now choose to drizzle itself when the subs can pay for
 * it ("Auto, when worth it", v0.494.0), and v0.494.2 measured what that costs:
 * about **×7 the per-sub time of a plain stack**, which on the owner's 5,477-sub
 * target turns about an hour of stacking into most of a day's. Asked whether a
 * hands-off run should decline a long one, he chose *"tell me the estimate
 * before it starts and let it run"* — no refusal, no threshold.
 *
 * So this is the whole of the owner's answer in one sentence, and the rules are
 * about not overclaiming, exactly as `stackTimeLine`'s are:
 *
 * - the **comparison** is the point. A bare "about 14 h" reads as the app being
 *   slow; "…where a plain stack would take about 2 h" is the fact he asked for,
 *   which is why the backend only ever sends the two numbers together;
 * - with **no timed history** there is no number, and the sentence says what the
 *   measurement alone supports — "several times longer than a normal stack".
 *   Silence is the one wrong answer here: the point of his choice is that an
 *   automatic drizzle never starts a long run without saying so;
 * - it names the **build** when the rate came from a different one, because
 *   across one real upgrade his own identical restacks came back 8–36 % slower
 *   (observer issue #933).
 *
 * The actions live with the surfaces that draw it — cancel the run, and "don't
 * auto-drizzle this target" — because this function only owns the wording, and
 * both the Jobs row and the Stack page's job card read it from here so the two
 * can never say different things about one run.
 */
export function autoDrizzleCostLine(cost: AutoDrizzleCost | null | undefined): string | null {
  if (!cost) return null;
  const scale = formatDrizzleScale(cost.scale);
  const head = scale ? `Drizzling ×${scale}` : "Drizzling";
  const { drizzle_seconds: drizzled, plain_seconds: plain } = cost;
  if (
    drizzled === null || plain === null
    || !Number.isFinite(drizzled) || !Number.isFinite(plain)
    || drizzled <= 0 || plain <= 0
  ) {
    // Nothing of this target's has been timed in a comparable shape, so the
    // honest sentence is the ratio the engine measured, with no hours in it.
    return `${head} — this will take several times longer than a normal stack.`;
  }
  const olderBuild = cost.same_engine === false
    ? " These came from a different version of AstroStack, so the real time may differ."
    : "";
  return `${head} — about ${formatEtaSeconds(drizzled)}`
    + ` (a plain stack would take about ${formatEtaSeconds(plain)}).`
    + olderBuild;
}

/** `1.5` → `"1.5"`, `2` → `"2"`, nonsense → `""` (and the sentence drops the
 * scale rather than printing `×NaN`). */
export function formatDrizzleScale(scale: number): string {
  if (!Number.isFinite(scale) || scale <= 0) return "";
  return String(Math.round(scale * 100) / 100);
}

/** The standing explanation under the line — why a run nobody asked chose to
 * spend this long, and that it is still his call. Kept here with the sentence so
 * both surfaces say it the same way. */
export const AUTO_DRIZZLE_WHY =
  "Your subs are deep and well dithered enough for drizzle to pull out real detail, "
  + "so this run turned it on by itself. It costs several times a plain stack's time. "
  + "Let it run, stop it, or keep this target on plain stacks from now on.";
