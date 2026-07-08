// Pure helpers for the 'Tonight' night-planner page — kept out of the component
// so they're easy to unit-test without rendering.

import type { PlannedTarget } from "./api/client";

// A short, friendly Moon-phase label from the illuminated fraction (0..1).
export function moonPhaseLabel(illum: number | null): string {
  if (illum == null || !Number.isFinite(illum)) return "—";
  const pct = Math.round(illum * 100);
  if (pct <= 3) return `New Moon (${pct}%)`;
  if (pct < 45) return `Crescent (${pct}%)`;
  if (pct <= 55) return `Quarter Moon (${pct}%)`;
  if (pct < 97) return `Gibbous (${pct}%)`;
  return `Full Moon (${pct}%)`;
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
