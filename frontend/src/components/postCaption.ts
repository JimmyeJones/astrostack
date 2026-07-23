/** "Ready-to-post caption" — one correct, friendly sentence a beginner can copy
 * verbatim to share their finished picture.
 *
 * The moment a non-expert goes to post their astrophoto to a friend, a group
 * chat, or social media, they're staring at a blank caption box — and they often
 * get the facts wrong (wrong object name, guessed integration time). This turns
 * data the app has *already* computed into an accurate, plain-language caption:
 *
 *   "The Orion Nebula (M42), an emission nebula — a stack of 240 subs (40 min
 *    total), shot on 20 Jul 2026 with a Seestar. The whole frame is about 5.4
 *    full Moons wide."
 *
 * Every fact is pulled from existing signals (catalog identity, the run's frame
 * count / integration / date, the already-computed scale bar), so there's no
 * guessing and no wrong numbers. Pure and threshold-free, so it's trivially
 * unit-tested and degrades gracefully — any clause whose datum is missing is
 * simply dropped (no identity → "your target"; no WCS → no scale clause;
 * unknown date → no date clause).
 */

import { formatIntegration } from "../format";

export interface PostCaptionInput {
  /** Catalog common name ("Orion Nebula"), or "" / null when the catalog has none. */
  name?: string | null;
  /** Catalog designation ("M42" / "NGC 7000"), or "" / null when unidentified. */
  catalogId?: string | null;
  /** Plain-language object type ("nebula", "galaxy"), or "" / null. */
  type?: string | null;
  /** Frames that actually went into the stack (`run.n_frames_used`). */
  nFrames?: number | null;
  /** Total integration in seconds (`run.total_exposure_s`), or null. */
  integrationS?: number | null;
  /** A pre-formatted, timezone-safe date label ("20 Jul 2026"), or null. */
  dateLabel?: string | null;
  /** The run's scale bar (from the annotations endpoint), or null. */
  scaleBar?: { moon_comparison?: string | null } | null;
  /** Fallback subject when the target isn't identified (the target's display
   *  name); a blank falls back to a sensible generic so we never post nothing. */
  fallbackName?: string | null;
}

const SHORT_MONTHS = [
  "Jan", "Feb", "Mar", "Apr", "May", "Jun",
  "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
];

/**
 * Format an ISO-8601 UTC timestamp as a friendly "20 Jul 2026" for the caption.
 * Reads the y/m/d straight off the string (never via `Date`) so the label can't
 * shift across a timezone boundary. Returns null for anything unparseable, so
 * the caller simply drops the date clause.
 */
export function formatCaptionDate(iso: string | null | undefined): string | null {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec((iso ?? "").trim());
  if (!m) return null;
  const day = parseInt(m[3], 10);
  const monthIdx = parseInt(m[2], 10) - 1;
  if (monthIdx < 0 || monthIdx > 11 || day < 1 || day > 31) return null;
  return `${day} ${SHORT_MONTHS[monthIdx]} ${m[1]}`;
}

/** "a"/"an" for a plain type word, from its first letter. */
function withArticle(type: string): string {
  const first = type.trim().charAt(0).toLowerCase();
  const article = "aeiou".includes(first) ? "an" : "a";
  return `${article} ${type.trim()}`;
}

function capitalise(s: string): string {
  return s.charAt(0).toUpperCase() + s.slice(1);
}

/**
 * Build the shareable caption from whatever facts are present. Never throws;
 * always returns a non-empty string (the generic fallback subject guarantees
 * that even a bare, unidentified, single-frame run gets a sensible sentence).
 */
export function postCaption(input: PostCaptionInput): string {
  const name = (input.name ?? "").trim();
  const catalogId = (input.catalogId ?? "").trim();
  const type = (input.type ?? "").trim();
  const identified = !!(name || catalogId);

  // Subject: prefer the common name with its designation in parentheses, then a
  // bare designation, then the fallback display name, then a generic.
  let subject: string;
  if (name && catalogId) subject = `${name} (${catalogId})`;
  else if (name) subject = name;
  else if (catalogId) subject = catalogId;
  else subject = (input.fallbackName ?? "").trim() || "My astrophoto";

  // Educational appositive — only when we actually identified the object, so we
  // never tack a type onto a bare user target name we're unsure about.
  if (identified && type) subject = `${subject}, ${withArticle(type)}`;

  // Stack clause: "a stack of N subs" (+ integration when known). Singular grammar.
  const clauses: string[] = [];
  const n = input.nFrames;
  if (typeof n === "number" && Number.isFinite(n) && n > 0) {
    const subs = `${n} sub${n === 1 ? "" : "s"}`;
    const integ = input.integrationS;
    if (typeof integ === "number" && Number.isFinite(integ) && integ > 0) {
      clauses.push(`a stack of ${subs} (${formatIntegration(integ)} total)`);
    } else {
      clauses.push(`a stack of ${subs}`);
    }
  }

  // Date + gear.
  const dateLabel = (input.dateLabel ?? "").trim();
  clauses.push(dateLabel ? `shot on ${dateLabel} with a Seestar` : "shot with a Seestar");

  const first = `${subject} — ${clauses.join(", ")}.`;

  // Scale sentence, when the run has a usable WCS.
  const moon = (input.scaleBar?.moon_comparison ?? "").trim();
  const second = moon ? `${capitalise(moon)}.` : "";

  return second ? `${first} ${second}` : first;
}
