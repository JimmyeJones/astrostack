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
