/** Pure helpers for the "Try something new tonight" discovery card.
 *
 * The suggester's companion to the "Plan your next night" phrasing: where that
 * one plans a target you *already* work, this introduces a *new* famous showpiece
 * that's well-placed right now. All phrasing lives here (no React, no I/O) so it's
 * unit-testable in isolation. Altitudes/times are as the offline planner computed
 * them; the copy stays jargon-free for a beginner reading it on a clear night.
 */
import type { SuggestedTarget } from "../api/client";

/** The display label: the friendly common name, or the catalog id when a famous
 * object simply has no proper name (e.g. "M106"). Never empty. */
export function suggestionLabel(s: SuggestedTarget): string {
  return s.name?.trim() || s.id;
}

/** A short "M27, the Dumbbell Nebula" style heading: id + name when both exist
 * and differ, else whichever we have. */
export function suggestionHeading(s: SuggestedTarget): string {
  const name = s.name?.trim();
  if (name && name !== s.id) return `${s.id} · ${name}`;
  return s.id;
}

/** How long the target is up tonight, rounded to a friendly figure:
 * "up about 7 h tonight" / "up about 45 min tonight". Assumes a usable window
 * (the card only shows suggestions that clear the floor). */
export function upForPhrase(minutesAboveMinAlt: number): string {
  const mins = Math.max(0, Math.round(minutesAboveMinAlt));
  if (mins < 90) {
    const rounded = Math.max(10, Math.round(mins / 10) * 10);
    return `up about ${rounded} min tonight`;
  }
  const halfHours = Math.round(mins / 30) / 2; // nearest half-hour
  return `up about ${halfHours} h tonight`;
}

/** How the Moon relates to this target tonight, or "" when it's not worth a word.
 * We only have the Moon's up-fraction and angular separation here (not its phase),
 * so we speak only to what we know: it's out of the way, or it's well clear. */
export function suggestionMoonPhrase(s: SuggestedTarget): string {
  const up = s.moon_up_fraction;
  if (up != null && up <= 0.1) return "Moon out of the way";
  if (s.moon_separation_deg >= 60) return "well clear of the Moon";
  return "";
}

/** One plain-language observability line for a suggestion:
 * "Climbs to 64°, up about 7 h tonight. Moon out of the way." */
export function describeSuggestion(s: SuggestedTarget): string {
  const alt = Math.round(s.max_altitude_deg);
  const moon = suggestionMoonPhrase(s);
  const moonClause = moon ? ` ${moon.charAt(0).toUpperCase()}${moon.slice(1)}.` : "";
  return `Climbs to ${alt}°, ${upForPhrase(s.minutes_above_min_alt)}.${moonClause}`;
}
