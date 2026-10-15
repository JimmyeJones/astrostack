/**
 * Sections 4 and 6 of the owner-approved Settings redesign
 * (`docs/design/settings-redesign.md`): "Where you observe from" and "How hard
 * your NAS works". The data and the arithmetic, free of React, so each sentence
 * and each drawn shape can be tested as a value; `ObservingSite.tsx` and
 * `NasSection.tsx` draw them.
 *
 * Two facts about the code these sentences describe, checked before they were
 * written (the spec's "every warning must be true of the code" rule):
 *
 * - **A typed location always wins.** `webapp/routers/plan.py::_resolve_observer_detail`
 *   uses `site_lat`/`site_lon` when *both* are set and only otherwise reads the
 *   subs' `SITELAT`/`SITELONG` headers. So "Read it from my photos" is exactly
 *   "clear both boxes", and a half-typed location (one box) still reads from
 *   the photos — which is why the mode below needs both.
 * - **Height above sea level is used either way.** The photo probe reads only
 *   latitude and longitude; the observer's elevation is `site_elevation_m` in
 *   both branches, so that box is shown whichever way the location is found.
 */

import type { ObservingSite, SystemInfo } from "../../api/client";
import { siteUnknownCopy } from "../../siteUnknown";
import type { SettingsForm, SettingsPatch } from "./moreSettings";

export type SiteMode = "photos" | "typed";

const isNum = (v: unknown): v is number => typeof v === "number" && Number.isFinite(v);

/** True when the form holds a full typed location — the one the planner obeys. */
export function hasTypedLocation(form: SettingsForm): boolean {
  return isNum(form.site_lat) && isNum(form.site_lon);
}

/**
 * Which of the two buttons is lit. A full typed location is "typed"; so is a
 * half-typed one the owner is part-way through (`typedChosen`, set by pressing
 * "Type it in"), so the boxes don't vanish under them between the two fields.
 */
export function siteMode(form: SettingsForm, typedChosen: boolean): SiteMode {
  if (hasTypedLocation(form)) return "typed";
  if (typedChosen || isNum(form.site_lat) || isNum(form.site_lon)) return "typed";
  return "photos";
}

/** What "Read it from my photos" writes: both boxes cleared. */
export const READ_FROM_PHOTOS_PATCH: SettingsPatch = { site_lat: null, site_lon: null };

/**
 * Whether to show the latitude/longitude boxes. Always in "typed" mode — and
 * also in "photos" mode whenever the photos have **not** given a location
 * (or we couldn't ask): that is exactly when the Tonight planner sends somebody
 * here to type one in, and landing them on a page with no box to type into
 * would be the dead end the deep link exists to avoid.
 */
export function showTypedBoxes(mode: SiteMode, site: ObservingSite | undefined): boolean {
  if (mode === "typed") return true;
  return !site?.from_photos;
}

/** `51.5° N, 0.1° W` — one decimal, which is about 10 km: plenty to plan a night. */
export function formatLatLon(lat: number, lon: number): string {
  const ns = lat >= 0 ? "N" : "S";
  const ew = lon >= 0 ? "E" : "W";
  return `${Math.abs(lat).toFixed(1)}° ${ns}, ${Math.abs(lon).toFixed(1)}° ${ew}`;
}

/**
 * The "Currently:" line — what the planner will use **once this form is
 * saved**, so pressing a button previews its effect like every other control
 * on the page. `site` is `GET /api/plan/site`, which reports what the photos
 * say even while a typed location is winning; undefined while it loads, on an
 * older backend, or on a failed request.
 */
export function currentLocationLine(
  form: SettingsForm, mode: SiteMode, site: ObservingSite | undefined,
): { text: string; known: boolean } {
  if (hasTypedLocation(form)) {
    return {
      text: `Typed in: ${formatLatLon(form.site_lat as number, form.site_lon as number)}`,
      known: true,
    };
  }
  if (mode === "typed") {
    return {
      text: "Type both latitude and longitude — until then it's read from your photos.",
      known: false,
    };
  }
  const p = site?.from_photos;
  if (p) {
    return {
      text: `Read from your Seestar's photos: ${formatLatLon(p.lat_deg, p.lon_deg)}`,
      known: true,
    };
  }
  if (!site) {
    return { text: "Read from your photos, once AstroStack has some to read.", known: false };
  }
  const reason = site.photos_reason === "found" ? null : site.photos_reason;
  if (reason === "unreadable") {
    // `siteUnknownCopy` deliberately doesn't offer Settings as the fix here:
    // the frames being unreachable is the problem worth knowing about.
    return {
      text: `${siteUnknownCopy(reason).title} just now — it will be read from them `
        + "once they're reachable again.",
      known: false,
    };
  }
  return {
    text: `${siteUnknownCopy(reason).title} — type it in below so the night planner can work.`,
    known: false,
  };
}

// ---------------------------------------------------------------------------
// The horizon drawing
// ---------------------------------------------------------------------------

/** The drawing's geometry: a half-dome of sky over a flat horizon. */
export const HORIZON = { cx: 160, cy: 160, r: 140 } as const;

/**
 * The lit band: the wedge of sky higher than `altDeg` above the horizon, seen
 * side-on — from the observer at the centre, between the two directions that
 * are `altDeg` above the horizon on either side. Clamped to the field's own
 * 0–80° so a stored value outside a slider's range still draws.
 */
export function altitudeBandPath(altDeg: number): string {
  const a = Math.max(0, Math.min(80, isNum(altDeg) ? altDeg : 30)) * (Math.PI / 180);
  const { cx, cy, r } = HORIZON;
  const dx = r * Math.cos(a);
  const dy = r * Math.sin(a);
  const f = (n: number) => n.toFixed(1);
  // Right point → arc over the top (sweep 0 = counter-clockwise in SVG's
  // y-down frame) → left point → back to the observer.
  return `M${f(cx)} ${f(cy)} L${f(cx + dx)} ${f(cy - dy)} `
    + `A${r} ${r} 0 0 0 ${f(cx - dx)} ${f(cy - dy)} Z`;
}

/** The slider's sentence, and how a beginner reads the number. */
export function altitudeLine(altDeg: number): string {
  return `Only suggest targets higher than ${altDeg}°`;
}

export function altitudeHint(altDeg: number): string {
  if (altDeg < 15) return "Close to the horizon: more targets, but through thick, hazy air.";
  if (altDeg <= 40) return "Above most trees, roofs and low haze.";
  return "Only high targets — sharper, but fewer to choose from each night.";
}

// ---------------------------------------------------------------------------
// Section 6 — the memory bar
// ---------------------------------------------------------------------------

export interface MemoryBar {
  /** Each a share of total RAM, 0–100, summing to 100. */
  otherPct: number;
  roomPct: number;
  freePct: number;
  otherGb: number;
  roomGb: number;
  freeGb: number;
  totalGb: number;
  /** The budget is more than is free right now, so the "room" is clipped to it. */
  clipped: boolean;
}

const round1 = (n: number) => Math.round(n * 10) / 10;

/**
 * The NAS's memory as three parts: what other apps hold now, the room one stack
 * may use (the engine's own `stack_budget_gb`, not a re-derivation — the
 * browser cannot see the container's environment), and what is kept free.
 * `null` on an older backend that doesn't report all three figures, so the
 * section falls back to its sentences rather than drawing a guess.
 */
export function memoryBar(memory: SystemInfo["memory"] | undefined): MemoryBar | null {
  const total = memory?.total_gb;
  const avail = memory?.available_gb;
  const budget = memory?.stack_budget_gb;
  if (!isNum(total) || !isNum(avail) || !isNum(budget) || total <= 0) return null;
  const free = Math.max(0, Math.min(avail, total));
  const other = total - free;
  const room = Math.max(0, Math.min(budget, free));
  const pct = (n: number) => round1((n / total) * 100);
  const otherPct = pct(other);
  const roomPct = pct(room);
  return {
    otherPct, roomPct, freePct: round1(Math.max(0, 100 - otherPct - roomPct)),
    otherGb: round1(other), roomGb: round1(room), freeGb: round1(free - room),
    totalGb: round1(total), clipped: budget > free,
  };
}

/**
 * The headline over the bar: Automatic, or the number in the form. The figure a
 * blank budget comes to *today* is `stackBudgetNote`'s sentence, just under it,
 * so it is not said twice.
 */
export function memoryHeadline(form: SettingsForm): string {
  const set = form.max_stack_memory_gb;
  if (isNum(set)) return `at most ${set} GB per stack.`;
  return "Automatic — measured from what's free before each stack.";
}
