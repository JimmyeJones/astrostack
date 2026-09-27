/**
 * Pure helpers for the "night after night" deepening reel card — the looping
 * animation of one target getting cleaner and deeper across successive stacks.
 * Kept free of React/DOM so the caption/label logic is unit-tested directly.
 */

export interface DeepeningInfo {
  available: boolean;
  n_stacks: number;
  first_subs?: number;
  last_subs?: number;
  first_utc?: string | null;
  last_utc?: string | null;
  /** Which clock `first_utc`/`last_utc` are on: "capture" when every stack in the
   * series records when its subs were *shot* (and the reel is ordered by that),
   * "stack" when it falls back to when the stacks *ran*. Absent on an older
   * backend, where the range is left unqualified exactly as it always was. */
  dated_by?: "capture" | "stack" | null;
  format?: string;
}

/** Short human date ("28 Jul"), or null for a missing/unparseable timestamp. */
export function shortDate(utc: string | null | undefined): string | null {
  if (!utc) return null;
  const d = new Date(utc);
  if (Number.isNaN(d.getTime())) return null;
  return d.toLocaleDateString([], { day: "numeric", month: "short" });
}

function withThousands(n: number): string {
  return Math.round(n).toLocaleString();
}

/**
 * A one-line provenance caption for the reel, e.g.
 * "M31 · 3 stacks · 120 → 1,240 subs · shot 28 Jun → 28 Jul". Each clause is
 * dropped (rather than printed blank) when its data is missing, so an older run
 * without a sub count or date still gets a tidy caption.
 *
 * The date range is **named by its clock** (`dated_by`): "shot …" when the series
 * is ordered by when its subs were taken, "stacked …" when the app only knows
 * when the stacks ran. Those two differ by years on a re-stacked back catalogue,
 * and on a card called "night after night" an unqualified range reads as the
 * first — so the caption says which it is rather than letting the reader assume.
 * An older backend sends no `dated_by` and keeps the bare range it always had.
 */
export function deepeningCaption(
  name: string | null | undefined,
  info: DeepeningInfo,
): string {
  const parts: string[] = [];
  const clean = (name ?? "").trim();
  if (clean) parts.push(clean);
  parts.push(`${info.n_stacks} stack${info.n_stacks === 1 ? "" : "s"}`);

  const first = info.first_subs;
  const last = info.last_subs;
  if (typeof first === "number" && typeof last === "number" && last !== first) {
    parts.push(`${withThousands(first)} → ${withThousands(last)} subs`);
  } else if (typeof last === "number") {
    parts.push(`${withThousands(last)} subs`);
  }

  const d1 = shortDate(info.first_utc);
  const d2 = shortDate(info.last_utc);
  const when = info.dated_by === "capture" ? "shot "
    : info.dated_by === "stack" ? "stacked " : "";
  if (d1 && d2 && d1 !== d2) parts.push(`${when}${d1} → ${d2}`);
  else if (d2) parts.push(`${when}${d2}`);

  return parts.join(" · ");
}

/**
 * The reassuring lead sentence: how much deeper the newest stack is than the
 * first, in plain language. Falls back to a generic line when sub counts are
 * missing.
 */
export function deepeningBlurb(
  name: string | null | undefined,
  info: DeepeningInfo,
): string {
  const clean = (name ?? "").trim() || "your target";
  const first = info.first_subs;
  const last = info.last_subs;
  if (typeof first === "number" && typeof last === "number" && first > 0 && last > first) {
    const times = last / first;
    const factor = times >= 2 ? ` — that's about ${times.toFixed(times >= 10 ? 0 : 1)}× the subs` : "";
    return `Watch ${clean} get cleaner and deeper across ${info.n_stacks} stacks, from ${withThousands(first)} to ${withThousands(last)} subs${factor}.`;
  }
  return `Watch ${clean} get cleaner and deeper across your ${info.n_stacks} stacks — the same picture, more subs each time.`;
}

/** Filename + share text for the downloaded/shared deepening clip. */
export function deepeningClip(
  name: string | null | undefined,
  format?: string | null,
): { title: string; text: string; filename: string } {
  const clean = (name ?? "").trim() || "My astrophoto";
  const ext = (format ?? "").trim().toLowerCase() === "png" ? "png" : "webp";
  const slug = clean.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "");
  return {
    title: `${clean}, night after night`,
    text: `${clean} getting deeper night after night, stacked with AstroStack`,
    filename: `${slug || "astrophoto"}-deepening.${ext}`,
  };
}
