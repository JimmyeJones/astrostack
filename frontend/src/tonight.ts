// Pure helpers for the 'Tonight' night-planner page — kept out of the component
// so they're easy to unit-test without rendering.

import type { NightPlan, PlannedTarget } from "./api/client";

// A short, friendly Moon-phase label from the illuminated fraction (0..1).
//
// When the waxing/waning state is known it's woven into the intermediate phases
// ("Waxing crescent", "First Quarter", "Waning gibbous", …), which for planning
// matters more than the raw fraction: a waxing Moon sets in the evening (so
// early-night targets stay dark) while a waning Moon rises after midnight. New
// and Full read the same either way, so they never take a prefix. Passing
// `waxing` null/undefined keeps the plain, direction-agnostic labels.
export function moonPhaseLabel(illum: number | null, waxing?: boolean | null): string {
  if (illum == null || !Number.isFinite(illum)) return "—";
  const pct = Math.round(illum * 100);
  if (pct <= 3) return `New Moon (${pct}%)`;
  if (pct < 45) {
    const name = waxing == null ? "Crescent" : waxing ? "Waxing crescent" : "Waning crescent";
    return `${name} (${pct}%)`;
  }
  if (pct <= 55) {
    const name = waxing == null ? "Quarter Moon" : waxing ? "First Quarter" : "Last Quarter";
    return `${name} (${pct}%)`;
  }
  if (pct < 97) {
    const name = waxing == null ? "Gibbous" : waxing ? "Waxing gibbous" : "Waning gibbous";
    return `${name} (${pct}%)`;
  }
  return `Full Moon (${pct}%)`;
}

// One short line naming *when* the Moon rises or sets during tonight's dark
// window — the concrete time the phase label can't give. `null` when there's no
// useful cue (no window computed), so the caller can omit the line entirely.
//
//   sets ~23:40   → dark skies after that time (a waxing Moon leaving the night)
//   rises ~01:10  → clean until then (a waning Moon spoiling the small hours)
//   up all night  → the Moon never leaves the dark window (worst case)
//   down all night→ below the horizon throughout — no interference at all
export function moonWindowNote(
  mw: NightPlan["moon_window"] | null | undefined,
): string | null {
  if (mw == null) return null;
  if (mw.down_all_night) return "Below the horizon all night";
  if (mw.up_all_night) return "Above the horizon all night";
  const parts: string[] = [];
  if (mw.set_utc) parts.push(`sets ~${formatClock(mw.set_utc)}, dark after`);
  if (mw.rise_utc) parts.push(`rises ~${formatClock(mw.rise_utc)}, dark before`);
  if (parts.length === 0) return null;
  // Capitalise the first word of the combined sentence.
  const s = parts.join("; ");
  return s.charAt(0).toUpperCase() + s.slice(1);
}

// A short, dimmed per-row Moon cue from a target's `moon_up_fraction` (0..1) —
// the share of its usable window the Moon is actually above the horizon. The
// Moon column shows the separation at a single mid-window instant, which can
// read scary ("12°") for a target the planner *didn't* penalise because the
// Moon was down while it was up; this reconciles the number with the ranking.
// `null` (omit the line) when the fraction is unknown — no usable window, or an
// older backend — or when the Moon is up for essentially the whole window,
// where the separation alone already tells the story.
export function moonCueForTarget(frac: number | null | undefined): string | null {
  if (frac == null || !Number.isFinite(frac)) return null;
  const pct = Math.round(Math.max(0, Math.min(1, frac)) * 100);
  if (pct <= 5) return "Moon down for its window";
  if (pct >= 95) return null;
  return `Moon up ${pct}% of its window`;
}

// A short "HH:MM–HH:MM" cue for *when* tonight a target is usable, from its
// usable-window clock bounds (UTC ISO). Complements the single transit time: a
// target up for hours could clear the floor at 21:00 or not until 01:00. `null`
// (omit the line) when either bound is missing — never usable, or an older
// backend. Times render in the viewer's local zone, like the rest of the page.
export function usableWindowNote(
  start: string | null | undefined,
  end: string | null | undefined,
): string | null {
  if (!start || !end) return null;
  const a = formatClock(start);
  const b = formatClock(end);
  if (a === "—" || b === "—") return null;
  return `${a}–${b}`;
}

// The furthest ahead the date picker lets you plan, matching the backend's
// `_MAX_LOOKAHEAD_DAYS` cap (keeps the offline ephemeris cheap; further out is
// almost always a typo).
export const MAX_PLAN_LOOKAHEAD_DAYS = 60;

// Local calendar date (YYYY-MM-DD) for a Date — the value a native date input
// expects. Uses the viewer's own timezone, so "today" is their today.
export function isoDate(d: Date): string {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

// The [min, max] the date picker should accept: today through +N days. `now` is
// injectable so the bounds are testable without touching the clock.
export function planDateBounds(now: Date): { min: string; max: string } {
  const max = new Date(now.getTime());
  max.setDate(max.getDate() + MAX_PLAN_LOOKAHEAD_DAYS);
  return { min: isoDate(now), max: isoDate(max) };
}

// A friendly label for which night the plan is for. Tonight (empty/today) reads
// "tonight"; a future pick names the date ("the night of Sat 15 Aug"). `now` is
// injectable for testing. Returns "" for tonight so callers can keep their
// existing "…tonight" copy unchanged.
export function planNightLabel(date: string | null | undefined, now: Date): string {
  if (!date || date === isoDate(now)) return "";
  const d = new Date(`${date}T12:00:00`);
  if (Number.isNaN(d.getTime())) return "";
  return d.toLocaleDateString([], { weekday: "short", day: "numeric", month: "short" });
}

export interface MinAltOption {
  value: string;
  label: string;
}

// The round preset floors the Tonight "Minimum altitude" picker offers.
const BASE_MIN_ALT: MinAltOption[] = [
  { value: "10", label: "10° (low)" },
  { value: "20", label: "20°" },
  { value: "30", label: "30° (default)" },
  { value: "40", label: "40°" },
  { value: "50", label: "50° (high only)" },
];

// Build the "Minimum altitude" options, guaranteeing the currently-active floor
// is always selectable. The user's `min_target_altitude_deg` setting is any
// integer 0–80 (the Settings input steps by 5, so 15° / 45° / 55° are all
// reachable), but this picker only lists round presets — so an active floor
// that isn't one of them would otherwise leave the Select rendering blank. When
// the active floor isn't already a preset, splice it in (numerically sorted) so
// the control always shows the real floor the plan was computed for.
export function minAltOptions(active: number | null | undefined): MinAltOption[] {
  if (active == null || !Number.isFinite(active)) return BASE_MIN_ALT;
  const rounded = Math.round(active);
  if (BASE_MIN_ALT.some((o) => Number(o.value) === rounded)) return BASE_MIN_ALT;
  const extra: MinAltOption = { value: String(rounded), label: `${rounded}°` };
  return [...BASE_MIN_ALT, extra].sort((a, b) => Number(a.value) - Number(b.value));
}

// A Mantine colour bucketing an observability score (0..100) into
// good / fair / poor, so the ranking reads at a glance.
export function scoreColor(score: number): string {
  if (score >= 70) return "teal";
  if (score >= 40) return "yellow";
  return "gray";
}

// Format a minutes count as "3.2 h" / "45 min" / "—".
export function formatMinutes(minutes: number): string {
  if (!Number.isFinite(minutes) || minutes <= 0) return "—";
  if (minutes >= 90) return `${(minutes / 60).toFixed(1)} h`;
  return `${Math.round(minutes)} min`;
}

// Local wall-clock HH:MM for a UTC ISO timestamp (in the viewer's timezone).
export function formatClock(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

// The nearest 8-point compass label (N, NE, E, …) for an azimuth in degrees, so
// the horizon-mask editor reads "S" rather than a bare "180°". Wraps at 360°.
export function compassPoint(az: number): string {
  if (!Number.isFinite(az)) return "";
  const dirs = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"];
  return dirs[Math.round((((az % 360) + 360) % 360) / 45) % 8];
}

export interface SplitTargets {
  already: PlannedTarget[];
  fresh: PlannedTarget[];
}

// Split a ranked plan into the user's own targets ("already targeted") and the
// bundled-catalog suggestions ("not yet targeted"), preserving score order.
export function splitTargets(targets: PlannedTarget[]): SplitTargets {
  return {
    already: targets.filter((t) => t.already_targeted),
    fresh: targets.filter((t) => !t.already_targeted),
  };
}
