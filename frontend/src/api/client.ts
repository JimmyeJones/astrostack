// Tiny typed fetch wrapper around the AstroStack API.

import type { SkyImage, SkyStar } from "../sky/projection";
import type { UniverseData } from "../sky/universe";

/** One target whose most recent stack attempt failed (see webapp/stackfailure.py).
 *  `unattended` means it failed on the walk-away path, where nobody read it. */
export interface StackFailure {
  safe: string;
  name: string;
  message: string;
  kind?: string | null;
  when_utc?: string | null;
  unattended?: boolean;
}

export interface StackFailuresData {
  failures: StackFailure[];
}

export interface SkyData {
  stars: SkyStar[];
  images: SkyImage[];
}

export interface PlannedTarget {
  id: string;
  name: string;
  ra_deg: number;
  dec_deg: number;
  type: string;
  con: string;
  already_targeted: boolean;
  max_altitude_deg: number;
  transit_utc: string | null;
  minutes_above_min_alt: number;
  moon_separation_deg: number;
  score: number;
  // Share (0..1) of this target's usable window the Moon is above the horizon —
  // the overlap that weights its Moon penalty. Lets the UI explain why a
  // bright-Moon night still ranked a target well (the Moon was down while it was
  // up). null/absent when the target has no usable window or on an older backend.
  moon_up_fraction?: number | null;
  // Clock bounds (UTC ISO) of when the target is actually shootable tonight — the
  // first/last moment it clears the floor — complementing the peak transit time.
  // null/absent when never usable or on an older backend.
  usable_start_utc?: string | null;
  usable_end_utc?: string | null;
  target_safe: string | null;
  frames_accepted: number | null;
  total_exposure_s: number | null;
  // The user's own integration goal for this target (seconds), when they set one
  // — so this row's readiness hint uses the same goal as the Target page and the
  // Dashboard overview. null/absent for a catalog row, for a target with no goal
  // set, and on an older backend; the per-object-type default then applies.
  goal_s?: number | null;
  // This target's recent productive pace (median kept integration per clear
  // night, seconds), so the row can say how many more clear nights would finish
  // it instead of only that it's "Nearly there". null/absent for a catalog row,
  // for a target without enough night history, and on an older backend.
  recent_pace_s?: number | null;
  // How many single-frame field-fulls of sky this target's newest stack
  // covers — 1.0 for a single field, ~4.0 for a 2×2 no-overlap mosaic. Lets
  // the row's readiness hint scale the per-object-type goal by the panel
  // count, so a four-panel mosaic at 1 h/panel is judged against 4 × 4 h
  // rather than told "Plenty — try something new" at a quarter of the light
  // it needs. null/absent for a catalog row, for a target with no stacked
  // picture yet, and on an older backend — the readiness code then falls back
  // to the un-scaled goal (today's behaviour).
  field_fulls?: number | null;
  // "Will it fit in one Seestar frame?" — major-axis size (arcmin) and the
  // verdict, for catalog candidates the bundled catalog has a size for. Absent
  // on library rows and older backends. See FramingHint.
  size_arcmin?: number | null;
  framing?: FramingHint | null;
  // The panel grid this object needs, for one bigger than a single frame;
  // absent/null when it fits or has no vetted size (older backends omit it —
  // treat as "nothing to say").
  mosaic?: MosaicPlan | null;
  // "How hard is this target for a Seestar?" — easy/moderate/challenging, for
  // catalog candidates the vetted table/type-rule has a verdict for; absent on
  // library rows, un-vetted objects, and older backends (treat as "no verdict").
  difficulty?: DifficultyHint | null;
  // "Last time it landed off-centre — nudge about 1.0° south before you start."
  // The framing advice from this target's newest picture, brought forward to the
  // screen you read while pointing the scope (the card that says it today is
  // read the morning after). null/absent for a catalog row, for a picture that
  // framed well, and on an older backend — never a guessed direction.
  recentre_nudge?: StackRecentreNudge | null;
}

/** One of the user's own targets, judged as "worth pointing at right now". */
export interface TonightPick {
  safe: string;
  name: string;
  ra_deg: number;
  dec_deg: number;
  // Altitude at the moment the ranking was made; null when no location is known
  // (the depth-only fallback) rather than a fabricated number.
  altitude_now_deg: number | null;
  minutes_usable_left: number;
  hours_captured: number;
  frames_accepted: number;
  // Fractional noise cut one more hour of subs would buy (0..1).
  noise_gain: number;
  score: number;
  // One plain-language sentence, shown verbatim.
  reason: string;
}

/** `GET /api/plan/best-tonight` — "best use of your scope right now". */
export interface BestTonight {
  location_source: "settings" | "fits" | "none";
  observer: { lat_deg: number; lon_deg: number; elevation_m: number } | null;
  generated_utc: string;
  dark_now: boolean;
  dark_minutes_left: number;
  min_altitude_deg: number;
  picks: TonightPick[];
  // Why the picks carry no placement, for the whole answer rather than per pick
  // (it used to be repeated inside every `reason`). Absent on the ordinary placed
  // path — and on a backend too old to send it, hence optional.
  note?: string | null;
}

/** One target's showing on one night — `GET /api/plan/week`. */
export interface WeekTargetPick {
  safe: string;
  name: string;
  usable_start_utc: string | null;
  usable_end_utc: string | null;
  minutes_above_min_alt: number;
  max_altitude_deg: number;
  moon_up_fraction: number | null;
  score: number;
}

/** One night of the week ahead, with the best-placed target on it. */
export interface WeekNight {
  // Local calendar date of the *evening* the night belongs to (YYYY-MM-DD).
  date: string;
  dark_start_utc: string;
  dark_end_utc: string;
  dark_minutes: number;
  moon_illumination: number;
  n_usable: number;
  // null when nothing of yours clears the altitude floor for long enough —
  // an honest "skip this one", not a promoted target that never rises.
  best: WeekTargetPick | null;
}

/** A target's single best night in the range — "M 31: Thursday". */
export interface TargetBestNight {
  safe: string;
  name: string;
  date: string;
  minutes_above_min_alt: number;
  score: number;
}

/** `GET /api/plan/week` — "which of my targets, on which night". */
export interface PlanWeek {
  location_source: "settings" | "fits" | "none";
  observer: { lat_deg: number; lon_deg: number; elevation_m: number } | null;
  generated_utc: string;
  min_altitude_deg: number;
  horizon_active: boolean;
  nights_scanned: number;
  nights: WeekNight[];
  targets: TargetBestNight[];
  // How many library targets were actually scanned vs how many could have been
  // (the scan is capped), so the card can be honest about a big library.
  n_targets_considered: number;
  n_targets_with_position: number;
}

export interface NightPlan {
  location_source: "settings" | "fits" | "none";
  observer: { lat_deg: number; lon_deg: number; elevation_m: number } | null;
  generated_utc: string;
  dark_window: {
    start_utc: string;
    end_utc: string;
    duration_minutes: number;
    sun_alt_threshold_deg: number;
  } | null;
  moon_illumination: number | null;
  // Whether the Moon is waxing (sets in the evening) or waning (rises after
  // midnight); null when no plan could be computed. Lets the UI say "Waxing
  // gibbous" vs "Waning gibbous" — the fraction alone can't tell them apart.
  moon_waxing?: boolean | null;
  // When the Moon rises/sets during tonight's dark window (concrete UTC times),
  // or that it stays up / down for the whole window. Absent/null when no dark
  // window could be computed. Complements the phase with the actual clock time.
  moon_window?: {
    rise_utc: string | null;
    set_utc: string | null;
    up_all_night: boolean;
    down_all_night: boolean;
  } | null;
  min_altitude_deg: number;
  // True when a horizon/tree mask (Settings → Observing site) shaped the usable
  // windows, so the UI can note that low-sky obstructions were accounted for.
  horizon_active?: boolean;
  targets: PlannedTarget[];
  // This owner's *typical* clear-night output (median of the per-target paces,
  // seconds of kept integration), so a row for a target they have not started —
  // an oversized one needing a mosaic — can still say roughly how many clear
  // nights it would take. Null when no target has a measured pace yet; absent on
  // an older backend, and the clause then simply doesn't render.
  usual_pace_s?: number | null;
}

// One upcoming night a target is well-placed in a dark window — the forward-
// looking companion to the retrospective trend cards. All times are UTC ISO.
export interface NextObservingWindow {
  dark_start_utc: string;
  dark_end_utc: string;
  usable_start_utc: string | null;
  usable_end_utc: string | null;
  max_altitude_deg: number;
  minutes_above_min_alt: number;
  moon_illumination: number;
  moon_up_fraction: number | null;
  score: number;
}

export interface NextSession {
  location_source: "settings" | "fits" | "none";
  observer: { lat_deg: number; lon_deg: number; elevation_m: number } | null;
  // False when the library has no RA/Dec for this target (never solved) — the
  // card then can't say *when*, only *how much* is left.
  target_has_position: boolean;
  min_altitude_deg: number;
  nights_scanned: number;
  // The next few nights it's shootable, soonest first; empty when no location is
  // set, the target has no position, or nothing clears the floor in the horizon.
  windows: NextObservingWindow[];
}

// One not-yet-captured showpiece that's well-placed tonight — a "try something
// new" discovery suggestion (from /api/plan/suggest). Carries the friendly
// catalog blurb ("what am I looking at?") plus tonight's observability.
export interface SuggestedTarget {
  id: string;
  name: string;
  ra_deg: number;
  dec_deg: number;
  type: string;
  con: string;
  blurb: string;
  max_altitude_deg: number;
  transit_utc: string | null;
  minutes_above_min_alt: number;
  moon_separation_deg: number;
  moon_up_fraction: number | null;
  usable_start_utc: string | null;
  usable_end_utc: string | null;
  score: number;
  size_arcmin?: number | null;
  framing?: FramingHint | null;
  // The panel grid this object needs, when it's bigger than a single frame;
  // absent/null when it fits or has no vetted size (older backends omit it).
  mosaic?: MosaicPlan | null;
  // "How hard is this target for a Seestar?" — shown next to the framing hint on a
  // discovery suggestion; absent for un-vetted objects / older backends.
  difficulty?: DifficultyHint | null;
}

export interface SuggestResponse {
  location_source: "settings" | "fits" | "none";
  observer: { lat_deg: number; lon_deg: number; elevation_m: number } | null;
  min_altitude_deg: number;
  // A few famous showpieces the user hasn't captured that are up tonight,
  // best-first; empty when no location is set or nothing new is well-placed.
  suggestions: SuggestedTarget[];
  // This owner's *typical* clear-night output (median of the per-target paces,
  // seconds of kept integration), so a row for a target they have not started —
  // an oversized one needing a mosaic — can still say roughly how many clear
  // nights it would take. Null when no target has a measured pace yet; absent on
  // an older backend, and the clause then simply doesn't render.
  usual_pace_s?: number | null;
}

// One month's observability for a target (from /api/plan/best-months) — the
// building block of the "best time of year" seasonal strip. max_transit_alt_deg
// is the peak altitude *during that month's darkness* (a target that only
// culminates in daylight reads low here — exactly the point).
export interface MonthObservability {
  month: number; // 1..12
  max_transit_alt_deg: number;
  usable_dark_minutes: number;
  dark_minutes: number;
}

export interface BestMonths {
  location_source: "settings" | "fits" | "none";
  observer: { lat_deg: number; lon_deg: number; elevation_m: number } | null;
  // False when the library has no RA/Dec for this target (never solved).
  target_has_position: boolean;
  min_altitude_deg: number;
  year: number;
  // Twelve rows, month 1→12; empty when no location is set or the target has no
  // position (the strip self-hides).
  months: MonthObservability[];
}

// "Is the Moon going to wash this out tonight?" (from /api/plan/moon) — one
// honest verdict + sentence for a target, evaluated at tonight's darkest moment.
export interface MoonInterference {
  illumination: number; // 0..1 illuminated fraction of the disk tonight
  waxing: boolean;      // waxing (evening Moon) vs waning (after-midnight)
  phase_name: string;   // "Full Moon" / "waxing crescent" / …
  moon_altitude_deg: number; // < 0 ⇒ below the horizon (can't affect the shot)
  separation_deg: number;    // angular sep between the Moon and this target
  level: "good" | "ok" | "poor"; // coarse verdict
  text: string;         // one plain-language sentence for the card
  at_utc: string;       // the darkest moment used for the readout (UTC ISO)
}

export interface MoonInterferenceResponse {
  location_source: "settings" | "fits" | "none";
  observer: { lat_deg: number; lon_deg: number; elevation_m: number } | null;
  // False when the library has no RA/Dec for this target (never solved).
  target_has_position: boolean;
  // null when no location is set or the target has no position (card self-hides).
  moon: MoonInterference | null;
}

// Plain-language "why were some frames left out?" breakdown (from
/** A plain-language read on how bright the sky was on this target's most recent
 * observing night, relative to its other nights (`/frames/sky-brightness`).
 * Purely relative — the app makes no absolute sky-brightness claim. */
export interface SkyBrightnessRead {
  level: "darker" | "typical" | "brighter" | "much_brighter";
  label: string;
  text: string;
  /** ISO date (YYYY-MM-DD) of the observing night being reported. */
  night: string;
  /** How many of this target's nights the comparison is based on. */
  nights: number;
  /** That night's sky rate divided by the median night's. */
  ratio: number;
}

// /frames/reject-summary). Buckets are non-zero and pre-ordered by the server.
export interface RejectionBucket {
  key: string;
  label: string;
  count: number;
  note: string;
}
export interface RejectionSummary {
  used: number;
  dropped: number;
  dropped_fraction: number;
  verdict: { tone: "good" | "ok" | "warn"; text: string };
  buckets: RejectionBucket[];
}

export interface Target {
  safe_name: string;
  name: string;
  ra_deg: number | null;
  dec_deg: number | null;
  n_frames: number;
  n_frames_accepted: number;
  total_exposure_s: number;
  last_activity_utc: string | null;
  has_preview: boolean;
  notes: string | null;
  tags: string[];
  cover_stack_run_id?: number | null;
  // How many single-frame field-fulls of sky this target's newest stack
  // covers — served by the Target detail endpoint (never on the light Library
  // list) so the "Is it enough yet?" card can scale the per-object-type goal
  // by the panel count. null/absent for a target with no stack yet, on an
  // older backend, or on a list-shape response — the card then falls back to
  // the un-scaled goal (today's behaviour).
  field_fulls?: number | null;
}

export interface MergeSuggestionTarget {
  safe: string;
  name: string;
  n_frames_accepted: number;
  total_exposure_s: number;
}

// A "these look like the same object — combine them?" suggestion: a cluster of
// ≥2 targets whose plate-solved centres agree. `targets` are ordered
// deepest-integration first, so `targets[0].safe` is the natural merge `into`.
export interface MergeSuggestion {
  object_name: string | null;
  center_ra_deg: number;
  center_dec_deg: number;
  max_sep_arcmin: number;
  targets: MergeSuggestionTarget[];
}

export interface CleanupSuggestion {
  safe: string;
  name: string;
  n_frames: number;
  reason:
    | "video"
    | "photo"
    | "on_device_output"
    | "temp_folder"
    | "duplicate_sub"
    | "legacy_mixed_drop";
  detail: string;
}

export interface FramingHint {
  level: "fits" | "tight" | "mosaic";
  text: string;
}

export interface LightTravel {
  distance_ly: number;
  // The friendly duration alone, e.g. "2.5 million years".
  years: string;
  // The ready-to-render sentence.
  text: string;
}

/** "How big is it, really?" — a target's span in full Moons, the one angular
 *  yardstick a non-astronomer already owns. */
export interface AngularSize {
  // The catalog major axis this was built from.
  size_arcmin: number;
  // That size in full-Moon widths, unrounded.
  moons: number;
  // A complete sentence: "In the sky it's about as wide as 6 full Moons."
  text: string;
}

/** "How big a mosaic?" — the panel grid a too-big target's span needs. */
export interface MosaicPlan {
  // Panels along the frame's long edge, and along its short edge.
  cols: number;
  rows: number;
  panels: number;
  // A complete sentence: "About a 3×2 mosaic (6 panels) covers all of it."
  text: string;
}

export interface DifficultyHint {
  level: "easy" | "moderate" | "challenging";
  // One-word badge text, e.g. "Easy".
  label: string;
  text: string;
}

export interface ObjectInfo {
  id: string;
  name: string;
  type: string;
  constellation: string;
  constellation_abbr: string;
  ra_deg: number;
  dec_deg: number;
  matched_by: "name" | "coords";
  // Major-axis size (arcmin) and the "will it fit in one frame?" verdict, when
  // the catalog records a size for this object; absent otherwise (older backends
  // omit both — treat as "no framing hint").
  size_arcmin?: number | null;
  framing?: FramingHint | null;
  // The panel grid this object needs, for one bigger than a single frame;
  // absent/null when it fits or has no vetted size (older backends omit it —
  // treat as "nothing to say").
  mosaic?: MosaicPlan | null;
  // A plain-language, beginner-friendly one-liner about the object ("what am I
  // looking at?"), for the popular targets; absent/"" when the catalog has none
  // (older backends omit it — the card reads fine from type + constellation).
  blurb?: string;
  // "How hard is this target for a Seestar?" — easy/moderate/challenging plus one
  // honest sentence, for the vetted popular objects; absent/null otherwise (older
  // backends omit it — treat as "no difficulty verdict").
  difficulty?: DifficultyHint | null;
  // Which per-frame background-flatten mode suits this target, when its catalog
  // type/size say the default per-channel fit would bend into it; absent/null
  // for everything else (older backends omit it — treat as "no advice").
  background_mode_hint?: BackgroundModeHint | null;
  // "How far did you see?" — the light in this picture left N years ago, from
  // the catalog's vetted distance; absent/null for an object without one (older
  // backends omit it — the card shows nothing either way).
  light_travel?: LightTravel | null;
  // "How big is it, really?" — the object's span in full Moons; absent/null
  // when the catalog has no vetted size or the object is too small for the
  // comparison to help (older backends omit it — the card shows nothing).
  angular_size?: AngularSize | null;
}

export interface BackgroundModeHint {
  // A StackOptions.background_mode value, so the Stack form's one-click fix can
  // apply it without re-deriving the choice.
  mode: string;
  text: string;
}

export interface SessionQualityDrift {
  kind: string;
  latest_fwhm_px: number;
  baseline_fwhm_px: number;
  n_latest: number;
  n_baseline: number;
}

/** Why the last hands-off scan held this target's stack back because some of
 * its subs had no file on disk right now (`GET /api/targets/{safe}/autostack-hold`;
 * `null` when the newest scan didn't hold it). */
export interface AutoStackHold {
  offered: number;
  readable: number;
  unreadable: number;
  reason?: string | null;
  when_utc?: string | null;
}

/** The newest stack is materially cleaner than the target's pinned cover
 * (`GET /api/targets/{safe}/cleanest-shot`; `null` when there's nothing to say
 * — nothing pinned, the newest already *is* the cover, or the gap is small).
 * Purely a suggestion: taking it goes through the same `setTargetCover` the
 * History page uses, and the app never swaps a cover by itself. */
export interface CleanestShot {
  run_id: number;
  cover_run_id: number;
  noise_sigma: number;
  cover_noise_sigma: number;
  percent_cleaner: number;
  n_frames_used: number;
  cover_n_frames_used: number;
  timestamp_utc: string;
}

/** The newest stack — which, with nothing pinned, *is* the cover — came out
 * materially grainier than an earlier one this target already has
 * (`GET /api/targets/{safe}/grainier-newest`; `null` when there's nothing to say
 * — something is pinned, there's no earlier stack, or the newest is the cleanest).
 * The mirror of `CleanestShot`, and mutually exclusive with it: one needs a pin,
 * this one needs none. Purely a suggestion — the app never pins by itself. */
export interface GrainierNewest {
  run_id: number;
  newest_run_id: number;
  noise_sigma: number;
  newest_noise_sigma: number;
  percent_grainier: number;
  n_frames_used: number;
  newest_n_frames_used: number;
  timestamp_utc: string;
}

export interface SessionRecap {
  n_frames: number;
  n_kept: number;
  n_set_aside: number;
  session_exposure_s: number;
  kept_exposure_s: number;
  total_kept_exposure_s: number;
  start_utc: string | null;
  end_utc: string | null;
  night_date?: string | null;
  reject_buckets: Record<string, number>;
  quality_drift: SessionQualityDrift | null;
  /** "Was the Moon washing this out?" — one plain-language sentence, present only
   *  when a bright Moon was genuinely up and close to this target while it was
   *  being shot. Null/absent on every other night (and on an older backend), so
   *  the card simply doesn't show the line. */
  moon_note?: string | null;
}

/** How the last handful of subs have been going — the rolling "is it working
 *  right now?" read behind "Tonight, live". `verdict` is one of good / mixed /
 *  poor / unknown, and `unknown` means "too few recent subs to say", never bad. */
export interface LiveConditions {
  verdict: string;
  n_recent: number;
  n_recent_kept: number;
  median_fwhm_px: number | null;
  recent_buckets: Record<string, number>;
}

/** The capture session in progress (or the trailing one, if it has gone quiet).
 *  `active` is what separates "tonight, live" from the ordinary recap. */
export interface LiveSession {
  active: boolean;
  n_frames: number;
  n_kept: number;
  n_set_aside: number;
  kept_exposure_s: number;
  session_exposure_s: number;
  total_kept_exposure_s: number;
  start_utc: string | null;
  latest_utc: string | null;
  minutes_since_latest: number | null;
  conditions: LiveConditions;
  reject_buckets: Record<string, number>;
  newest_kept_frame_id: number | null;
  goal_exposure_s: number | null;
  /** "Capture seems to have gone quiet": this session was *mid-run* and the subs
   *  stopped, judged against the cadence this target had been keeping. Narrower
   *  than `!active` — a night finished on purpose never sets it. Optional:
   *  absent on an older backend, which reads as "nothing to say". */
  quiet?: boolean;
  /** The cadence behind that verdict, in minutes between subs. */
  typical_gap_minutes?: number | null;
  /** How long the silence had to run before it was worth mentioning. */
  quiet_after_minutes?: number | null;
}

/** What re-stacking this target's newest picture would *give* the owner.
 *  A picture stacked before the app recorded when its subs were shot can never
 *  say which night it is from — and unlike the coverage share and the seam
 *  figure, that can't be healed from disk. `null` when there is nothing honest
 *  to offer, including when the subs aren't datable enough for a re-stack to
 *  fill the gap. */
export interface RestackGain {
  run_id: number;
  timestamp_utc: string;
  /** How many subs the old picture combined. */
  n_frames_used: number;
  /** How many accepted subs a re-stack would combine — the cost half. */
  n_frames_ready: number;
  missing_capture_window: boolean;
  missing_night_count: boolean;
}

export interface HealthNote {
  kind: string;
  severity: "good" | "info";
  message: string;
  action: string | null;
}

export interface DarkSpec {
  exposure_s: number | null;
  gain: number | null;
}

export interface StackHealth {
  run_id: number | null;
  notes: HealthNote[];
  // The exposure/gain to shoot darks at, for the "How to add darks" guide.
  // Optional — older backends omit it (treat as no pre-filled numbers).
  dark_spec?: DarkSpec | null;
}

export interface BestFrame {
  frame_id: number | null;
  captured_utc: string | null;
  fwhm_px: number | null;
  star_count: number | null;
  n_accepted: number;
}

export interface TargetNight {
  name: string;
  safe: string;
  n_frames: number;
  n_kept: number;
  n_set_aside: number;
  exposure_s: number;
  kept_exposure_s: number;
}

export interface NightSummary {
  start_utc: string | null;
  end_utc: string | null;
  // ISO `YYYY-MM-DD` observing night (noon-to-noon local, same bucketing as the
  // imaging calendar). Optional: an older backend doesn't send it.
  night_date?: string | null;
  n_frames: number;
  n_kept: number;
  n_set_aside: number;
  exposure_s: number;
  kept_exposure_s: number;
  median_fwhm_px: number | null;
  verdict: string; // "sharp" | "soft" | "hazy" | "" (too few measured)
  // What the verdict was measured against — the median of the target's OTHER
  // nights' median FWHMs. Optional: an older backend doesn't send it, and it is
  // null when this is the only judgeable night.
  typical_fwhm_px?: number | null;
  is_best: boolean;
  reject_buckets: Record<string, number>;
  // Set on the newest row only, when that night stopped notably earlier than
  // this target's own recent nights. Optional: an older backend doesn't send it.
  ended_early?: NightEarlyStop | null;
}

/** The Dashboard "Last night" early-stop measurement, as carried on a night row
 *  of a target's own page (so without the name/safe the Dashboard needs). */
export interface NightEarlyStop {
  /** The last sub of that night, ISO 8601 UTC. */
  stopped_utc: string;
  /** How much earlier than this target's usual stop, in minutes. */
  minutes_earlier: number;
  n_nights_compared: number;
}

export interface FocusTrendPoint {
  t_utc: string;
  fwhm_px: number;
}

export interface FocusTrend {
  verdict: string; // "steady" | "softened" | "improved"
  points: FocusTrendPoint[];
  n_points: number;
  median_fwhm_px: number;
  early_fwhm_px: number;
  late_fwhm_px: number;
  start_utc: string | null;
  end_utc: string | null;
  soft_after_utc: string | null;
  // Did the target's newest genuine stack actually count worse subs less?
  // "applied" | "not_applied" | "unstacked" | "unknown" — absent from an older
  // backend, which reads as "unknown" and gets the general wording. The card's
  // "counted less in your stack" reassurance is only earned by "applied".
  weighting?: string;
}

export interface TransparencyTrendPoint {
  t_utc: string;
  transparency: number;
}

export interface TransparencyTrend {
  verdict: string; // "clear" | "degraded" | "cleared"
  points: TransparencyTrendPoint[];
  n_points: number;
  median_transparency: number;
  early_transparency: number;
  late_transparency: number;
  start_utc: string | null;
  end_utc: string | null;
  degraded_after_utc: string | null;
  // The same "did the stack really down-weight them?" datum the focus card
  // carries, for the identical promise this card makes about hazy subs.
  weighting?: string;
  // How many mosaic panels this night's subs split into (0, or absent from an
  // older backend, for the ordinary single-pointing target). A mosaic's panels
  // are different patches of sky, so their star flux differs by pointing rather
  // than by weather — non-zero means the scores above were levelled panel by
  // panel before the verdict was taken.
  n_pointings?: number;
}

export interface LibrarySessionRecap {
  n_targets: number;
  n_frames: number;
  n_kept: number;
  n_set_aside: number;
  session_exposure_s: number;
  kept_exposure_s: number;
  start_utc: string | null;
  end_utc: string | null;
  night_date?: string | null;
  targets: TargetNight[];
  reject_buckets: Record<string, number>;
  /** One target whose newest night stopped notably earlier than its own recent
   *  nights do — the morning form of the live "capture has gone quiet" note,
   *  which self-hides before the owner wakes up. Absent on an ordinary night
   *  and on an older backend, so every read site must tolerate `undefined`. */
  early_stop?: EarlyStop | null;
}

export interface EarlyStop {
  name: string;
  safe: string;
  /** The last sub of the night just gone, ISO 8601 UTC. */
  stopped_utc: string;
  /** How much earlier than this target's usual stop, in minutes. */
  minutes_earlier: number;
  n_nights_compared: number;
}

export interface TargetProgress {
  safe: string;
  name: string;
  total_exposure_s: number;
  object_type: string | null;
  goal_s: number | null;
  // Median kept integration per clear night over this target's recent nights,
  // or null when there isn't enough history to call it a pace. Optional: an
  // older backend simply doesn't send it, and the card then says nothing about
  // how many more nights a target needs.
  recent_pace_s?: number | null;
  // How many single-frame field-fulls of sky this target's newest stack
  // covers — the readiness verdict scales its per-object-type goal by this, so
  // a mosaic is judged against a per-panel depth rather than told "plenty"
  // when each panel is a fraction of the goal. null/absent for a target with
  // no stacked picture yet, or on an older backend — the card then falls back
  // to the un-scaled goal (today's behaviour).
  field_fulls?: number | null;
}

export interface NightActivity {
  date: string; // observing-night date, ISO YYYY-MM-DD
  exposure_s: number;
  n_frames: number;
  targets: string[];
  // Typical star size that night (median of the subs QC measured), in pixels.
  // Optional: an older backend doesn't send it.
  median_fwhm_px?: number | null;
  n_measured?: number;
}

export interface ActivityCalendar {
  start_date: string;
  end_date: string;
  months: number;
  nights: NightActivity[];
  n_nights: number;
  total_exposure_s: number;
  nights_this_month: number;
  best_streak_nights: number;
  // "Your best night" — the window's sharpest night, or null/absent when too
  // little was measured to name one honestly (or on an older backend).
  sharpest_night?: NightActivity | null;
}

export interface SummaryTarget {
  safe: string;
  name: string;
  total_exposure_s: number;
  integration_hours: number;
  n_frames_accepted: number;
  thumbnail_url: string | null;
}

export interface LibrarySummary {
  n_targets_imaged: number;
  n_subs_kept: number;
  total_integration_s: number;
  integration_hours: number;
  first_light_utc: string | null;
  longest_target: SummaryTarget | null;
  most_imaged_target: SummaryTarget | null;
  heroes: SummaryTarget[];
  /** Finished Moon/Sun stills. They aren't library targets, so no other tally
   * here counts them — but they are pictures, and the "download all my
   * pictures" archive includes them. Optional: an older backend omits it. */
  n_finished_stills?: number;
}

/** One target whose accepted subs the library still lists but disk no longer
 * has. Part of `LibraryMissingFiles`; the list is capped worst-first, so it is
 * for *naming* a single-target outage, never for counting. */
export interface MissingFilesTarget {
  safe: string;
  name: string;
  n_missing: number;
}

/** Library-wide storage preflight: are the subs this library lists actually on
 * disk right now? An unmounted drive or an offline share takes out every target
 * at once, and the per-target note on the Target page can only speak for the
 * target you happen to be looking at. */
export interface LibraryMissingFiles {
  n_missing: number;
  n_accepted: number;
  n_targets_missing: number;
  targets: MissingFilesTarget[];
}

/** The shareable "your sky, so far" recap — the poster's own figures plus the
 * copy-paste caption to post beside it. `has_anything` is false until some light
 * has been collected, which is the card's cue to hide. */
export interface LibraryRecap {
  has_anything: boolean;
  caption: string;
  since: string;
  stats: { value: string; label: string }[];
  window_months: number;
  n_nights: number;
  n_targets: number;
  n_subs_kept: number;
  total_integration_s: number;
  top_target_name: string | null;
  top_target_integration_s: number | null;
  /** "Also shot: M 42, NGC 7000 and 5 more" — what else you pointed at, or ""
   * on a one-target library. Optional: an older backend omits it. */
  also_shot?: string;
}

/** A target seen for the first time in a given year. `safe` is null when the
 * registry no longer has it, in which case the chip isn't a link. */
export interface YearFirstLight {
  name: string;
  safe: string | null;
}

/** "Your year under the stars" — one calendar year of imaging. `has_anything`
 * is false for a year with no imaged nights; `empty_message` then names the
 * years that do have data, so the page can offer them instead of zeros. */
export interface YearRecap {
  year: number;
  has_anything: boolean;
  headline: string;
  empty_message: string;
  stats: { value: string; label: string }[];
  first_light_line: string;
  n_nights: number;
  total_exposure_s: number;
  n_frames: number;
  n_targets: number;
  target_names: string[];
  first_lights: YearFirstLight[];
  longest_night: NightActivity | null;
  sharpest_night: NightActivity | null;
  years_with_data: number[];
}

export interface DashboardStats {
  n_targets: number;
  n_frames: number;
  n_frames_accepted: number;
  total_exposure_s: number;
  integration_hours: number;
  acceptance_rate: number | null;
  n_stack_runs: number;
  n_targets_with_stacks: number;
  active_jobs: number;
  // Finished Moon/Sun stills. Optional: an older backend never sends it, and
  // every reader treats a missing value as 0. These are pictures the deep-sky
  // counters above genuinely cannot see (a video ingests no FITS, solves
  // nothing and creates no stack run).
  n_video_stills?: number;
  recent_stacks: {
    safe: string;
    target_name: string;
    run_id: number;
    output_basename: string;
    timestamp_utc: string;
    n_frames_used: number;
    has_preview: boolean;
    has_fits?: boolean;
    preview_url: string;
    /** The run's own canvas, so the download menu can word the "Full-res PNG"
     *  honestly (that render is capped — see `fullres.ts`). Optional: an older
     *  backend omits them and the copy falls back to the common wording. */
    canvas_w?: number;
    canvas_h?: number;
    /** When this picture's subs were **shot** (observing nights, ISO
     *  `YYYY-MM-DD`) — as opposed to `timestamp_utc`, when the stack ran.
     *  Absent on an older backend or a run with no recorded window. */
    capture_night_start?: string | null;
    capture_night_end?: string | null;
    /** How many observing **nights** those subs came from. The window above
     *  cannot say — 15→18 Nov is equally consistent with two nights and with
     *  four — and the count is what makes a picture sound like the work it was.
     *  Absent for a run recorded before the app tracked it; say nothing then. */
    capture_nights?: number | null;
  }[];
  disk: {
    total_gb?: number; used_gb?: number; free_gb?: number;
    /** Raw counts (additive; absent on an older backend). Prefer these — the
     *  `*_gb` fields are decimal, the rest of the UI is binary. */
    free_bytes?: number; total_bytes?: number;
  };
}

export interface SampleStatus {
  loaded: boolean;
  safe: string | null;
  n_frames: number;
}

export interface TargetStorage {
  safe: string;
  name: string;
  total_bytes: number;
  output_bytes: number;
  cache_bytes: number;
  stage1_bytes: number;
  stage2_bytes: number;
  thumbs_bytes: number;
  /** The editor's live-preview proxies. Optional: an older backend omits it. */
  proxies_bytes?: number;
  n_stack_runs: number;
}

export interface StorageInfo {
  targets: TargetStorage[];
  total_bytes: number;
  output_bytes: number;
  cache_bytes: number;
  disk: {
    total_gb?: number;
    used_gb?: number;
    free_gb?: number;
    free_bytes?: number;
    // Estimated recent library growth, bytes/night; null when history is too thin.
    nightly_bytes?: number | null;
  };
}

export interface SeestarTelemetry {
  device_name: string | null;
  model: string | null;
  firmware: string | null;
  temp_c: number | null;
  battery_pct: number | null;
  charging: boolean | null;
  charger_status: string | null;
  free_storage_mb: number | null;
  total_storage_mb: number | null;
  mode: string | null;
  state: string | null;
  stage: string | null;
  target_name: string | null;
  stacked_frames: number | null;
  dropped_frames: number | null;
  ra_hours: number | null;
  dec_deg: number | null;
}

export interface SeestarDevice {
  id: string;
  ip: string;
  device_name: string | null;
  model: string | null;
  firmware: string | null;
  reachable: boolean;
  connected: boolean;
  reconnecting?: boolean;
  last_seen_utc: string | null;
  telemetry: SeestarTelemetry | null;
  error: string | null;
}

export interface SeestarDevices {
  enabled: boolean;
  control_enabled: boolean;
  devices: SeestarDevice[];
}

export interface Frame {
  id: number;
  name: string;
  timestamp_utc: string | null;
  /** The observing night this sub belongs to (`YYYY-MM-DD`), bucketed
   *  noon-to-noon in the observer's local time — the same night the picture
   *  above the table is dated by. Optional: an older backend omits it. */
  night_date?: string | null;
  exposure_s: number | null;
  gain: number | null;
  width_px: number | null;
  height_px: number | null;
  bayer_pattern: string | null;
  solved: boolean;
  ra_center_deg: number | null;
  dec_center_deg: number | null;
  ra_hint_deg: number | null;
  dec_hint_deg: number | null;
  fwhm_px: number | null;
  star_count: number | null;
  sky_adu_median: number | null;
  eccentricity_median: number | null;
  transparency_score: number | null;
  streak_detected: boolean;
  accept: boolean;
  reject_reason: string | null;
  user_override: boolean;
}

export interface GradeReason {
  metric: string;
  label: string;
  value: number;
  typical: number;
  z: number;
}

export interface GradeRecommendation {
  frame_id: number;
  name: string;
  reasons: GradeReason[];
}

export interface GradeReport {
  sensitivity: string;
  n_accepted: number;
  n_considered: number;
  recommendations: GradeRecommendation[];
  metrics_used: string[];
  metrics_skipped: Record<string, string>;
  capped: boolean;
  /** Mosaic panels graded against themselves rather than against the whole
   * target (panels are different patches of sky, so a star-poor one is not
   * cloud). 0 — or absent, on an older backend — means ordinary target-wide
   * grading. */
  pointing_groups?: number;
  changed_ids: number[] | null;
}

export interface StackRun {
  id: number;
  timestamp_utc: string;
  output_basename: string;
  n_frames_used: number;
  canvas_w: number;
  canvas_h: number;
  coverage_min: number;
  coverage_max: number;
  has_fits: boolean;
  has_tiff: boolean;
  has_preview: boolean;
  // True when this run recorded *where* outlier rejection dropped samples (the
  // `_rejected.fits` sibling), so the card can offer "show what was removed".
  // Absent on an older backend, which reads the same as false — nothing to offer.
  has_rejection_map?: boolean;
  is_cover?: boolean;
  notes: string | null;
  total_exposure_s?: number | null;
  reusable?: boolean;
  // When this picture's subs were **shot** — the observing nights (ISO
  // `YYYY-MM-DD`) of its first and last sub, bucketed server-side with the same
  // noon-to-noon rule the Nights card uses. Equal when the whole stack came from
  // one night. Null/absent for a run recorded before the app knew (schema < 18)
  // or whose subs carry no capture time, and callers then drop the clause —
  // never falling back to `timestamp_utc`, which is when the stack *ran*.
  capture_night_start?: string | null;
  capture_night_end?: string | null;
  /** How many observing **nights** those subs came from. The window above
   *  cannot say — 15→18 Nov is equally consistent with two nights and with
   *  four — and the count is what makes a picture sound like the work it was.
   *  Absent for a run recorded before the app tracked it; say nothing then. */
  capture_nights?: number | null;
  transparency_ratio?: number | null;
  noise_sigma?: number | null;
  // This stack's own measured median star size (FWHM) in native-frame pixels,
  // lower = sharper. Null for runs recorded before the column existed (schema
  // < 14) or when too few stars to fit. Comparable across a target's runs.
  stack_fwhm_px?: number | null;
  // The North-up rotation (degrees) baked into this run's *stored preview PNG*
  // by a previous "Adjust" save — 0/null when it was saved un-rotated. The
  // object pins and scale bar are measured on the un-rotated FITS grid, so they
  // can't be drawn on a picture that was saved turned.
  preview_north_up_deg?: number | null;
  // What the *stored preview PNG* shows of the stack canvas when the one-click
  // "Process target" auto-edit trimmed its ragged border: fractional bounds of
  // the canvas, or null/absent (the common case) for a plain full-canvas
  // downscale. The object pins and the scale bar are measured on the un-cropped
  // FITS grid, so they have to be shifted into this rectangle to land right.
  preview_crop?: { x0: number; y0: number; x1: number; y1: number } | null;
  // True when the stored preview came out of a recipe whose geometry can't be
  // reduced to a crop of the canvas, so nothing measured on the FITS grid can
  // honestly be placed on it — hide the pins/bar rather than mis-plot them.
  preview_geometry_unknown?: boolean;
  // How flat this *mosaic's* panel joins came out, read for us by the backend:
  // "flat" (the sky matches across the joins), "check" (a step big enough to show
  // once stretched), or null/absent when there's nothing honest to say — a
  // single-field stack, a pre-schema-15 run, or the ambiguous middle band. The
  // verdict is computed server-side from the same thresholds the "How's my
  // stack?" seam notes use, so the chip and the note can never disagree.
  seam_verdict?: string | null;
  calstat?: string | null;
  options?: Record<string, unknown>;
  engine_version?: string | null;
  // True when an edit was saved for this run in the editor but never exported —
  // so the preview shown here (and on History and the Gallery) is still the plain
  // auto-stretch of the linear stack, not the picture the user made. Absent on an
  // older backend, which reads as "no unfinished edit" and shows nothing.
  unexported_edit?: boolean;
}

export interface StackInfoCard {
  key: string;
  value: string | number | boolean;
  comment: string | null;
}

export interface ReprocessStatus {
  current_version: string;
  outdated: number;      // targets whose current image was made by an older version
  up_to_date: number;    // targets already stacked on the running version
  total_targets: number;
}

export interface AutoCastSummary {
  measured: number;                  // auto-edited runs with a usable sky-cast reading
  neutral: number;                   // of those, how many landed background-neutral
  cast: number;                      // of those, how many carried a residual colour cast
  by_cast: Record<string, number>;   // dominant-tint counts among the cast runs
  median_deviation: number | null;   // median largest per-channel departure from grey
}

export interface StackWeightingSummary {
  mode: string;
  n_downweighted?: number;
  min?: number;
  max?: number;
  median?: number;
}

// Quality weighting was on, but the method that ran ignored it (min/max is an
// order statistic, so it combines by rank rather than by weight). Present only
// on such a run — its absence means either weighting was off or it applied.
export interface StackWeightingSkipped {
  reason: string;
  // True when min/max was picked automatically from the frame count (so it
  // switches back to weight-respecting sigma clipping at `min_frames` subs),
  // false when the user ticked "Min/max rejection" themselves.
  auto?: boolean;
  min_frames?: number;
}

export interface StackPhotometricSummary {
  mode: string;
  n_adjusted?: number;
  min?: number;
  max?: number;
  median?: number;
  // True when the mosaic path turned normalization on itself rather than the
  // user ticking the box. Absent on masters written before v0.271.0.
  auto?: boolean;
  // How many mosaic panels were matched against their own subs rather than
  // against each other. Absent on single-field runs and older masters.
  n_panels?: number;
}

export interface StackDarkScalingSummary {
  mode: string;
  dark_exposure?: number;
  light_exposure?: number;
}

export interface StackRejectionSummary {
  mode: string;
  n_rejected?: number;
  n_contributed?: number;
  fraction?: number;
  // Whether this run also kept the *spatial* record of those drops beside the
  // picture (`StackOptions.record_rejection_map`, off by default), so the card
  // can offer "show me what was removed". Absent on every run recorded before
  // the option existed, which reads the same as false — no overlay to offer.
  has_map?: boolean;
}

export interface PrintSize {
  // The paper size, e.g. "A4" or "10×8 in" — what the user picks.
  name: string;
  // The DPI this picture would actually be printed at on that paper.
  dpi: number;
  // "A4 · 240 DPI", built server-side so one voice describes it everywhere.
  label: string;
  width_in: number;
  height_in: number;
}

/** The next print size up, and what it would take to reach it. */
export interface BiggerPrint {
  /** The next paper size up, e.g. "A3". */
  name: string;
  /** Times more pixels per side than the picture has now. */
  scale: number;
  width_px: number;
  height_px: number;
  /** The finished sentence — names *resolution* as the lever, never more subs. */
  text: string;
}

export interface PrintSizes {
  // Largest first, so the head of the list is the recommended print.
  sizes: PrintSize[];
  // One plain-language line: "Best print size for this picture: up to A4 at
  // 240 DPI." — or, for a picture too small to print well, why not yet.
  advice: string;
  // The motivating half: how close the picture is to the next size up and which
  // lever gets it there. Absent/null when it already prints at the largest size
  // offered, when the gap is too big to be worth naming, or on an older backend.
  bigger?: BiggerPrint | null;
}

/** An unattended run that lowered its drizzle scale to fit the memory budget. */
export interface StackDrizzleDegraded {
  reason: string;
  /** The super-resolution scale the run actually used. */
  applied?: number;
  /** The scale it was asked for, when the run recorded it. */
  requested?: number;
}

export interface StackFrameAccounting {
  // Subs the stacker attempted to combine (after lucky/mosaic-outlier filtering).
  n_offered: number;
  // Of those, how many couldn't be aligned (load failure or a footprint that
  // missed the canvas — usually a stray sub or a bad plate-solve).
  n_align_failed?: number;
  // Of `n_align_failed`, how many had no file on disk at all when the stack ran
  // (neither the Stage-1 cache nor the original source) — a cleared cache with
  // the originals on an offline share, an unmounted drive, moved files. Absent
  // on masters stacked before this was recorded.
  n_unreadable?: number;
  // Subs whose file *was* on disk and then failed mid-read (a flaking network
  // share, a bad sector, a half-written file). Counted per sub, not per error
  // line, so a sub that failed both passes counts once. Absent on masters
  // stacked before this was recorded.
  n_read_errors?: number;
  // Of `n_read_errors`, how many a two-pass run read fine on its *other* pass
  // and combined anyway — so their light is in the picture after all.
  n_read_recovered?: number;
  // How many contributing subs sub-pixel refine had to leave *only roughly*
  // aligned (its measured shift exceeded the cap, so the frame stacked
  // unshifted → possibly soft/doubled stars). Present only when refine ran.
  n_roughly_aligned?: number;
  // How many reference patches sub-pixel refine built — one for a single field,
  // one per substantial panel on a mosaic — and how many contributing subs fell
  // outside all of them (so they stacked at whole-pixel alignment). Present only
  // when refine ran; absent on masters stacked before this was recorded.
  n_refine_patches?: number;
  n_refine_out_of_reach?: number;
}

export interface StackProcessingStep {
  op: string;
  label: string;
}

/** One catalog deep-sky object that falls inside a stack's field. */
export interface FieldObject {
  catalog_id: string;   // catalog designation, e.g. "M31" / "NGC 891"
  name: string;         // friendly name when the catalog has one, else ""
  type: string;         // "galaxy" / "nebula" / …
  ra_deg: number;
  dec_deg: number;
  x_px: number;         // 0-based pixel x on the FITS grid (width_px below)
  y_px: number;         // 0-based pixel y on the FITS grid (height_px below)
}

/** "How big is this in the sky?" — a round angular scale bar for a run. */
export interface ScaleBar {
  arcsec: number;          // the bar's length in arcseconds (a round number)
  label: string;           // a friendly label ("30′" / "2°" / "45″")
  fraction: number;        // bar length as a fraction of the image width (0–1)
  frame_arcmin: number;    // the whole frame's width in arcminutes
  moon_comparison: string; // one plain sentence comparing the frame to the Moon
}

/** "Which way is up?" — where North and East point on a run's own pixel grid.
 *  Angles are degrees counter-clockwise from screen-right with screen-up
 *  positive (the engine's `seestack.skymarks` convention), so "North is up" is
 *  `north_deg === 90`. The shared JPEG bakes the same two numbers. */
export interface SkyDirections {
  north_deg: number;
  east_deg: number;
}

/** "What's in this picture?" — objects + the grid their pixel coords live on. */
export interface StackAnnotations {
  width: number;        // the run's FITS pixel width (x_px domain)
  height: number;       // the run's FITS pixel height (y_px domain)
  objects: FieldObject[];
  // The scale bar for this run, or null when it has no usable celestial WCS
  // (older/edited runs) — the overlay then simply doesn't offer it. Measured on
  // the full FITS canvas, which is what the *live* Adjust render shows.
  scale_bar: ScaleBar | null;
  // The same bar measured on the part of the canvas the *stored preview* shows,
  // for runs the auto-edit trimmed — so the drawn bar, the frame width and the
  // "N full Moons wide" sentence all describe the picture on screen rather than
  // the larger canvas behind it. null when the run isn't cropped (use
  // `scale_bar`) or has no usable WCS; absent on an older backend, same meaning.
  preview_scale_bar?: ScaleBar | null;
  // Where North/East point, or null when the run has no usable orientation.
  // Absent on an older backend, which reads as "no rose" and shows nothing.
  directions?: SkyDirections | null;
  // How far a `?north_up=true` render would actually turn this picture, or null
  // when it wouldn't turn it at all (no usable WCS, or a correction below the
  // renderer's threshold). A surface offers the "North up" *view* only when this
  // is a number — otherwise the toggle would do visibly nothing. Absent on an
  // older backend, which reads the same way: no toggle.
  north_up_deg?: number | null;
}

/** "Did I frame it well?" — the post-stack verdict on how a finished picture
 *  actually caught its target, from the run's own WCS and the object's catalog
 *  size. The endpoint returns null (never a guess) when the target isn't in the
 *  catalog, carries no vetted size, or the run has no usable celestial WCS. */
/** The crop that would bring an off-centre object back to the middle of its own
 *  picture — fractional (0..1) bounds in the editor's `geometry.crop` convention,
 *  plus the fraction of the frame's area it keeps. Only ever present on an
 *  `off_centre` verdict, and only when it's honestly worth offering (cropping
 *  can't un-clip an object, and a crop that gutted the picture isn't offered). */
export interface StackRecentreCrop {
  x0: number;
  y0: number;
  x1: number;
  y1: number;
  kept: number;
}

/** Why there is no re-centring crop on a picture the verdict *did* call
 *  off-centre. `reason` is the engine's stable token (`too_destructive` is the
 *  only one worth saying out loud — see `recentreRefusalLine`); `kept` is the
 *  fraction of the frame that refused crop would have left. */
export interface StackRecentreRefusal {
  reason: string;
  kept?: number | null;
}

export interface StackFraming {
  level: "centred" | "off_centre" | "clipped" | "partial";
  text: string;           // the sentence, prefixed by the caller with the name
  coverage: number;       // 0–1: how much of the object landed in the frame
  off_centre: number;     // 0 = dead centre, 1 = on the frame's edge
  object_name: string;    // the catalog's friendly name ("Orion Nebula")
  size_arcmin: number;
  // Additive (an older backend omits it entirely — read as "no offer").
  recentre?: StackRecentreCrop | null;
  // Additive: why the offer above is absent (older backend → omitted).
  recentre_refused?: StackRecentreRefusal | null;
  // Additive: which way (and how far) to move the mount so the object lands in
  // the middle next session — the missing half of "re-centre it next time".
  // Null/omitted when the correction is too small to act on, or the verdict
  // isn't one a better pointing fixes.
  nudge?: StackRecentreNudge | null;
}

/** "Next time, nudge your Seestar about 0.4° west…" — the actionable half of a
 *  re-centre verdict. `direction` is one of eight plain compass words and
 *  `degrees` the angular move; `text` is the ready-to-render sentence, and
 *  `short` the same move as a chip-sized phrase ("0.4° west") for a surface with
 *  no room for it. Absent on an older backend. */
export interface StackRecentreNudge {
  direction: string;
  degrees: number;
  text: string;
  short?: string;
}

export interface StackRunInfo {
  run_id: number;
  integration_s: number | null;
  n_frames: number | null;
  weighting: StackWeightingSummary | null;
  weighting_skipped?: StackWeightingSkipped | null;
  photometric?: StackPhotometricSummary | null;
  dark_scaling?: StackDarkScalingSummary | null;
  rejection?: StackRejectionSummary | null;
  // Honest per-run frame accounting — how many subs the stacker attempted to
  // combine and how many couldn't be aligned. Absent on older masters.
  frame_accounting?: StackFrameAccounting | null;
  // Present only when an *unattended* run's drizzle canvas didn't fit the memory
  // budget and the engine stepped the super-resolution scale down to the largest
  // one that did — instead of refusing to make a picture at all with advice
  // nobody was there to read. Absent on every run that fitted.
  drizzle_degraded?: StackDrizzleDegraded | null;
  // Plain-language "what the unattended auto-edit did (and why)" note, present
  // only on runs an autonomous job auto-edited (Process-target / reprocess /
  // watcher auto-stack). Absent on manual/un-edited runs.
  auto_edit?: string | null;
  // The finished picture's residual sky-background colour cast (r/g/b sky medians
  // + a neutral/colour verdict), measured on the auto-edited render an unattended
  // job produced. Present only on auto-edited runs; lets History show whether the
  // hands-off Auto path landed the background neutral. Absent on older runs.
  sky_cast?: SkyCast | null;
  // Which colour-calibration (white-balance) path the auto-edit's Auto recipe
  // actually ran and on how many stars — the star-based gray-star/Gaia solve, the
  // background-neutral fallback (too few stars), or a no-op. Present only on
  // auto-edited runs; lets History tell the user whether their hands-off image was
  // really white-balanced (and by which route). Absent on older/manual runs.
  color_cal?: AutoColorCal | null;
  // A specific, actionable hint for *why* a stack that carries provenance came out
  // uncalibrated (e.g. "you have a master dark at a different exposure — build a
  // master bias and it'll be reused automatically"). Present only when the library
  // holds a master that's usable but for one concrete, fixable thing; the generic
  // "build or pick a master" copy is used otherwise.
  calibration_advice?: string | null;
  // Plain-language reasons this run had to *skip* a calibration master the user
  // explicitly saved for the target — e.g. one deleted since it was saved, or one
  // built for another camera. Recorded by the run itself (not inferred), so it's
  // the only signal that can explain a dropped pick; empty/absent on runs that
  // skipped nothing and on runs from before this was recorded.
  calibration_skipped?: string[] | null;
  // The mirror image of `calibration_skipped`: plain-language mismatches between a
  // master this run *did* apply and the subs it calibrated — a dark shot at another
  // exposure (its pedestal is over/under-subtracted on every frame) or at a very
  // different sensor temperature. Measured by the engine at stack time and recorded
  // on the run; empty/absent when the masters matched and on runs from before this
  // was recorded.
  calibration_warnings?: string[] | null;
  processing?: StackProcessingStep[];
  cards: StackInfoCard[];
}

export interface StackEstimate {
  n_frames: number;
  canvas_w: number;
  canvas_h: number;
  output_w: number;
  output_h: number;
  is_mosaic: boolean;
  peak_bytes: number;
  peak_gb: number;
  budget_bytes: number;
  budget_gb: number;
  would_exceed: boolean;
  suggested_drizzle_scale: number | null;
  suggested_reference_canvas: boolean;
  // The single least-destructive one-click fix + the memory it lands at, matching
  // the run-time refusal message. null when the run fits or no one lever obviously
  // does. `kind` names the lever: "drizzle_scale" (set drizzle_scale to `value`),
  // "reduce_outlier_passes" (set min_max_reject_count to 1), or "reference_canvas"
  // (set mosaic_canvas to "reference"). `value` is the target drizzle scale for
  // "drizzle_scale", null otherwise.
  memory_fix: {
    kind: "drizzle_scale" | "reduce_outlier_passes" | "reference_canvas";
    value: number | null;
    peak_bytes: number;
    peak_gb: number;
  } | null;
  // What this stack would *print* at, in the unit a human wants, while the knob
  // that sets it is still on screen. `bigger_*` are null whenever there is
  // nothing honest to offer (the canvas already fills the largest paper, the gap
  // needs more super-resolution than pays off, or the bigger canvas would bust
  // the memory budget — that verdict is the one above's to give, not this one's).
  // Optional so an older backend simply says nothing.
  print_plan?: {
    name: string | null;
    dpi: number | null;
    text: string;
    bigger_name: string | null;
    bigger_drizzle_scale: number | null;
    bigger_text: string | null;
  } | null;
  // What "Auto outlier removal" resolves to for this many frames — the engine
  // overrides the sigma-clip / min-max toggles when it's on, so the form reads
  // the truth from here rather than re-deriving the rule. null means those
  // toggles really are live (auto off, or drizzle on — drizzle keeps its own
  // two-pass rejection and auto leaves the toggles alone).
  auto_reject_resolved: {
    method: "sigma_clip" | "min_max";
    // The frame count at which auto switches from min/max to sigma clipping.
    switch_at_frames: number;
    // The accepted+solved frames this answer was computed for.
    n_frames: number;
  } | null;
  // Whether the rejection this stack is configured for can actually drop a lone
  // satellite/plane/cosmic-ray hit at this frame count. Sigma clipping runs from
  // 4 frames but is mathematically blind to a single outlier until
  // `lone_outlier_min_frames` (11 at the default κ=3), so in between it runs and
  // clips nothing — which is the opposite of what a beginner assumes. Optional so
  // an older backend simply says nothing.
  rejection_reach?: {
    // The combine that will actually run, on the resolved options.
    method: "drizzle" | "min-max-reject" | "sigma-clip" | "mean";
    n_frames: number;
    // Smallest frame count at which `method` could drop a lone extreme; null
    // when no rejection pass runs at any count.
    lone_outlier_min_frames: number | null;
    reaches: boolean;
  } | null;
}

/** What the *unattended* chain's outlier rejection will be able to do.
 *
 * `StackEstimate.rejection_reach` answers this for the values on the Stack form;
 * this answers it for the settings the watcher's auto-stack and the one-click
 * **Process target** button will actually use — the target's saved defaults,
 * with the chain's own "the user chose nothing" injection applied. Sized by a
 * mosaic's per-pixel `panel_depth`, not by its frame count.
 */
export interface RejectionOutlook {
  method?: "drizzle" | "min-max-reject" | "sigma-clip" | "mean";
  n_frames?: number;
  /** Subs on one spot of a mosaic; null on a single field, where it is `n_frames`. */
  panel_depth?: number | null;
  lone_outlier_min_frames?: number | null;
  /** null = no verdict (nothing solved yet, or an older backend). */
  reaches: boolean | null;
  /** True when the method came from the user's own saved defaults. */
  user_chose: boolean;
}

export interface GalleryItem {
  safe: string;
  target_name: string;
  run_id: number;
  output_basename: string;
  timestamp_utc: string;
  n_frames_used: number;
  canvas_w: number;
  canvas_h: number;
  total_exposure_s: number | null;
  notes?: string | null;
  has_preview: boolean;
  has_fits: boolean;
  has_tiff: boolean;
  preview_url: string;
  options: Record<string, unknown>;
  reusable?: boolean;
  // When this picture's subs were **shot** (observing nights, ISO `YYYY-MM-DD`,
  // bucketed server-side) — as opposed to `timestamp_utc`, when the stack ran.
  // Null/absent for a run recorded before the app knew; a caller then drops the
  // date rather than passing off a processing stamp as a capture date.
  capture_night_start?: string | null;
  capture_night_end?: string | null;
  /** How many observing **nights** those subs came from. The window above
   *  cannot say — 15→18 Nov is equally consistent with two nights and with
   *  four — and the count is what makes a picture sound like the work it was.
   *  Absent for a run recorded before the app tracked it; say nothing then. */
  capture_nights?: number | null;
  transparency_ratio?: number | null;
  noise_sigma?: number | null;
  calstat?: string | null;
  // Panel-flatness verdict for a mosaic run ("flat" | "check"), or null/absent
  // when there's nothing honest to say. Resolved server-side from the same
  // thresholds the "How's my stack?" seam notes use — see `StackRun`.
  seam_verdict?: string | null;
  // True when an edit was saved for this run but never exported, so this card's
  // thumbnail isn't the user's version. Same server-side decision as `StackRun`;
  // absent on an older backend, which reads as "no unfinished edit".
  unexported_edit?: boolean;
  // True when this run recorded the "what stacking removed" map beside its FITS,
  // so the full-screen viewer can offer the tint. Same server-side stat as
  // `StackRun.has_rejection_map`; absent on an older backend, which reads as
  // "no overlay for this one" — the correct answer for every run that didn't
  // record one.
  has_rejection_map?: boolean;
}

// A finished Moon/Sun still, as the Gallery lists it alongside stack runs. It is
// not a stack run — no target, no run id, no stacking options — so it carries
// only what a plain card needs, plus the framing fields behind the one-click
// crop, and links back to the Moon & Sun page for anything else.
export interface VideoStill {
  capture_id: string;
  label: string;
  kind: "lunar" | "solar" | "other";
  created_utc: string;
  width: number;
  height: number;
  n_stacked: number;
  source_name: string;
  preview_url: string;
  // The 16-bit TIFF of the same picture, when the backend found one on disk —
  // the full-quality copy to open elsewhere. Optional/nullable: an older backend
  // omits it and the viewer simply doesn't offer the download.
  tiff_url?: string | null;
  // Framing — the same four fields `VideoResult` carries, so both surfaces read
  // one decision. Optional: an older backend omits them and the card simply
  // offers nothing.
  crop_applied?: boolean;
  crop_available?: boolean;
  crop_trim_fraction?: number;
  source_width?: number;
  source_height?: number;
  crop_restorable?: boolean;
  // Anything the stack wants said about this picture (frames that couldn't be
  // aligned, a truncated tail frame). The same engine strings the Moon & Sun
  // card shows, so one picture reads the same on both. Optional: an older
  // backend omits them and the card simply says nothing extra.
  warnings?: string[];
  // How hard this picture was sharpened (0 = not at all), so the card can say so
  // in the same words the Moon & Sun page does. Optional: an older backend omits
  // it and a still made before sharpening existed reads as unsharpened.
  sharpen_amount?: number;
  // Whether that strength can still be changed without re-stacking. Optional:
  // an older backend omits it and the card simply offers no sharpening control,
  // which is what it did before this field existed.
  sharpen_editable?: boolean;
}

// "My life list" — one bundled catalog object and whether it has been captured.
// Matched server-side against the library's plate-solved target centres, so a
// captured tile can link straight to the picture.
export interface LifeListItem {
  catalog_id: string;
  /** Popular name, or "" for the many catalog entries without one. */
  name: string;
  type: string;
  con: string;
  blurb: string;
  size_arcmin: number | null;
  captured: boolean;
  safe_name: string | null;
  target_name: string | null;
  sep_deg: number | null;
  /** null for an object never captured, and for one captured but not yet stacked. */
  thumbnail_url: string | null;
}

export interface LifeListCounts {
  messier_captured: number;
  messier_total: number;
  other_captured: number;
  other_total: number;
}

export interface LifeList {
  messier: LifeListItem[];
  other: LifeListItem[];
  counts: LifeListCounts;
}

/** One object still missing from a nearly-finished constellation. The
 *  observability fields are set only on the one that's best placed tonight
 *  (`tonight_catalog_id`); every other row leaves them null. */
export interface NearlyThereObject {
  catalog_id: string;
  name: string;
  type: string;
  blurb: string;
  max_altitude_deg: number | null;
  minutes_above_min_alt: number | null;
  usable_start_utc: string | null;
  usable_end_utc: string | null;
}

/** "You're one away from finishing Orion — and it's up tonight."
 *  (`GET /api/life-list/nearly-there`; `null` when no constellation is close,
 *  so the card self-hides.) */
export interface NearlyThere {
  con: string;
  /** Full constellation name ("Orion"), or the abbreviation when unknown. */
  constellation: string;
  captured: number;
  total: number;
  missing: NearlyThereObject[];
  tonight_catalog_id: string | null;
  /** "settings" | "fits" | "none" — lets the card explain a missing tonight pick. */
  location_source: string;
}

export interface BestPicture {
  safe: string;
  target_name: string;
  run_id: number;
  output_basename: string;
  timestamp_utc: string;
  n_frames_used: number;
  canvas_w: number;
  canvas_h: number;
  total_exposure_s: number | null;
  noise_sigma: number | null;
  has_preview: boolean;
  has_fits: boolean;
  has_tiff: boolean;
  preview_url: string;
  // Quality-blend score in [0, 1], relative to this Library's own collection.
  score: number;
  // When this picture's subs were **shot** (observing nights, ISO `YYYY-MM-DD`,
  // bucketed server-side) — as opposed to `timestamp_utc`, when the stack ran.
  // Null/absent for a run recorded before the app knew; a caller then drops the
  // date rather than passing off a processing stamp as a capture date.
  capture_night_start?: string | null;
  capture_night_end?: string | null;
  /** How many observing **nights** those subs came from. The window above
   *  cannot say — 15→18 Nov is equally consistent with two nights and with
   *  four — and the count is what makes a picture sound like the work it was.
   *  Absent for a run recorded before the app tracked it; say nothing then. */
  capture_nights?: number | null;

  // True when this is the picture the user pinned as its target's cover ("Set as
  // cover" in History): it represents that target here instead of the newest
  // stack, and is floated above the ranked tail so the automatic ranking can't
  // hide it. Absent from an older backend, which never pinned anything.
  pinned?: boolean;
  // "What am I looking at?" — the offline catalog's plain-language type
  // ("galaxy") and one-line blurb, so a surface that shows this picture away
  // from its target page (the slideshow) can caption it in the app's own words.
  // Optional: an older backend omits both, and the caption then just names the
  // target.
  object_type?: string;
  blurb?: string;
}

export interface UnexportedEditItem {
  safe: string;
  target_name: string;
  run_id: number;
  timestamp_utc: string;
}

export interface LogEntry {
  seq: number;
  ts: string;
  level: string;
  levelno: number;
  logger: string;
  message: string;
}

export interface Job {
  id: string;
  kind: string;
  target: string | null;
  state: string;
  phase: string;
  done: number;
  total: number;
  detail: string;
  created_utc: string | null;
  started_utc: string | null;
  finished_utc: string | null;
  error: string | null;
  /** Stable canonical failure category set server-side (webapp/jobs.py), preferred
   * over string-matching the raw `error`. Absent on an older backend. */
  error_kind?: string | null;
  result: Record<string, unknown> | null;
}

export interface StackOptionField {
  key: string;
  label: string;
  type: "bool" | "int" | "float" | "str" | "enum" | "curve";
  group: "simple" | "advanced";
  default: unknown;
  min: number | null;
  max: number | null;
  step: number | null;
  options: string[] | null;
  option_labels?: Record<string, string> | null;
  help: string | null;
  depends_on: string | null;
}

export interface SystemInfo {
  version: string;
  data_root: string;
  cpu_count: number | null;
  cpu_workers: number | null;
  gpu_available: boolean;
  astap: {
    found: boolean;
    path: string | null;
    star_db_found?: boolean;
    star_db_dir?: string | null;
    star_db_count?: number;
    runs?: boolean;
    version?: string | null;
    hint?: string;
    error?: string;
  };
  disk: {
    total_gb?: number; used_gb?: number; free_gb?: number;
    /** Raw counts (additive; absent on an older backend). Prefer these — the
     *  `*_gb` fields are decimal, the rest of the UI is binary. */
    free_bytes?: number; total_bytes?: number;
  };
  memory: { total_gb?: number; available_gb?: number };
  folders?: {
    incoming: { path: string; exists: boolean; writable: boolean };
    library: { path: string; exists: boolean; writable: boolean };
  };
  watcher_enabled: boolean;
}

export type Settings = Record<string, unknown> & {
  resolved_incoming_dir: string;
  resolved_library_root: string;
};

// --- editor ---------------------------------------------------------------

export interface EditOp {
  id: string;
  label: string;
  group: string;
  stage: string;
  proxy_safe: boolean;
  is_stretch: boolean;
  heavy?: boolean;
  help: string | null;
  params: StackOptionField[];
}

export interface OpInstance {
  uid: string;
  id: string;
  enabled: boolean;
  params: Record<string, unknown>;
}

export interface Recipe {
  version?: number;
  base_run_id?: number | null;
  updated_utc?: string | null;
  ops: OpInstance[];
}

/** The most recent *other* run's saved editor recipe, offered for one-click
 * carry-over onto a re-stacked run. `run_id` is null when none exists. */
export interface PreviousRecipe {
  run_id: number | null;
  ops: OpInstance[];
  count: number;
}

/** The user's library-wide default editor recipe ("my house style"), offered as
 * a one-click seed on any run with no saved edit. `count` is 0 when unset. */
export interface DefaultRecipe {
  ops: OpInstance[];
  count: number;
}

export interface Preset {
  id: string;
  label: string;
  group: string;
  ops: { id: string; params: Record<string, unknown>; enabled?: boolean; uid?: string }[];
}

/** The library's Adaptive-Auto "taste" profile: the active per-parameter `biases`
 * the owner built up by giving Auto plain-language feedback, a plain-language
 * `note` explaining how Auto shifted (`null` when neutral), and a `neutral` flag.
 * An unset profile reads as neutral — Auto then behaves exactly as its data-driven
 * default. Served by `…/editor/auto-preferences`. */
export interface AutoPreferences {
  biases: Record<string, number>;
  note: string | null;
  neutral: boolean;
}

/** The measured cues Auto-process read from a run's own data to build its recipe
 * (the *causal inputs* behind the ops), served by `…/editor/auto-analysis`. Every
 * field is nullable so it degrades gracefully: sky/noise are null when the proxy
 * can't be measured, `median_fwhm`/`sharpen_radius` are null with no solved stars,
 * and `trim_fraction` is null on a single-field (non-trimmed) stack. */
export interface AutoAnalysis {
  sky: number | null;            // measured normalized sky level (0..1)
  sky_sigma: number | null;      // robust background noise σ
  noisy: boolean | null;         // coarse noisy verdict
  noise_fraction: number | null; // 0..1 denoise/sharpen crossfade weight
  median_fwhm: number | null;    // target's median star FWHM (px)
  sharpen_radius: number | null; // unsharp radius Auto sized from the stars (px)
  is_mosaic: boolean;
  trim_fraction: number | null;  // fraction of frame trimmed as ragged mosaic edge
  // What the trim *would* remove, even when auto-crop is off — so the UI can offer
  // the crop without claiming it happened. Optional: an older backend omits both.
  trim_fraction_available?: number | null;
  auto_crop?: boolean;           // whether this recipe trimmed the border at all
}

/** A coarse content-classification hint served by `…/editor/preset-suggestion`:
 * "this looks like a star cluster / nebula / galaxy — try the matching preset?".
 * `preset_id` is null when nothing is clearly one archetype (no chip shown). */
export interface PresetSuggestion {
  preset_id: string | null;  // a BUILTIN_PRESETS id, or null when unsure
  label: string | null;      // that preset's display label
  reason: string | null;     // short plain-language "why" (e.g. "mostly point-like stars…")
  confidence: number;        // 0..1 (0 when declined)
}

/** Whether "check it at full size" can answer for a run + recipe, and what it
 *  would show. `available: false` always carries a plain-language `reason` — the
 *  preview is already 1:1, or the recipe's geometry makes "which part of the
 *  picture is this?" unanswerable. Absent on an older backend, which the caller
 *  reads as "don't offer it". */
/** Which source pixels a rendered full-size window actually covers, as the
 *  server clamped it — `x`/`y`/`width`/`height` in the **full canvas**'s own
 *  pixels, alongside that canvas's size. The browser can only ever report a
 *  fraction of the preview it clicked, and with a crop in the recipe that maps to
 *  somewhere it cannot compute, so this is the one authoritative answer to "which
 *  part of my picture am I looking at?". Comes back on the loupe response's
 *  `X-Loupe-Window` header; `null` on an older backend that doesn't send it. */
export interface LoupeWindow {
  x: number;
  y: number;
  width: number;
  height: number;
  canvas_width: number;
  canvas_height: number;
  proxy_scale: number;
  /** The same rectangle as 0..1 fractions of the **rendered preview**, which is a
   *  different frame whenever the recipe crops. Deliberately not clamped: a
   *  window clamped inside the canvas can hang over a crop's edge, and saying so
   *  lets the marker be drawn clipped rather than slid inward. Absent on a
   *  backend older than v0.329.6, and on a degenerate crop. */
  preview_x?: number;
  preview_y?: number;
  preview_width?: number;
  preview_height?: number;
}

export interface LoupeInfo {
  available: boolean;
  reason: string | null;
  proxy_scale: number;
  size_px: number;
  canvas_width: number | null;
  canvas_height: number | null;
}

export interface Histogram {
  bins: number;
  edges: number[];
  r: number[];
  g: number[];
  b: number[];
  empty?: boolean;
  errors?: string[];
  // Live preview runs on a downscaled proxy of the (possibly huge) master.
  // proxy_scale = full_width / proxy_width (>=1); proxy_width is the proxy's
  // pixel width. Surfaced so the editor can tell the user the preview is
  // downscaled and set expectations vs the full-res export.
  proxy_scale?: number;
  proxy_width?: number;
  proxy_height?: number;
  // Dims of the *rendered* preview after the recipe's geometry ops (crop/rotate/
  // resize) reshape the frame — what the preview PNG actually measures. The editor
  // sizes its image box from these so a cropped preview fills the box instead of
  // letterboxing inside the un-cropped aspect (which mis-aligns overlays). Equal to
  // proxy_width/height when the recipe has no reshaping geometry op; absent on an
  // older backend (fall back to the proxy dims).
  render_width?: number;
  render_height?: number;
  // True when this run is a mosaic (uneven panel overlap → coverage spans a
  // range). The "Coverage leveling" op only does something on a mosaic, so the
  // editor uses this to tell the user when the control is a no-op here.
  is_mosaic?: boolean;
  // True when an enabled Deconvolution op's PSF collapses on the decimated
  // preview proxy, so the live preview understates the effect the full-res
  // export applies. Surfaced as an honest advisory (the sub-pixel blur simply
  // isn't representable on the proxy grid — see deconvUnderstatesCaption).
  deconv_preview_understates?: boolean;
  // True when an enabled Star-reduction op runs on a decimated preview, where its
  // erosion footprint rounds to whole proxy pixels and the stars themselves are
  // partly decimated away — so the preview's star reduction is not the export's
  // (measured 0.63x–1.58x, no consistent direction). Surfaced as an honest
  // advisory (see starReduceDiffersCaption). Key name kept for compatibility.
  star_reduce_preview_overstates?: boolean;
  // True when an enabled Sharpen op's radius, shrunk by proxy_scale, goes
  // sub-pixel on the decimated preview, so the unsharp mask collapses towards the
  // identity and the live preview shows only a fraction of the local contrast the
  // full-res export adds (see sharpenUnderstatesCaption). Absent on an older backend.
  sharpen_preview_understates?: boolean;
  // True when an enabled Hot-pixel removal op is *skipped* on the decimated
  // preview: striding turns a real star into a lone isolated pixel, which is the
  // signature the op treats as a defect, so previewing it erased stars the export
  // never touches. The preview leaves the image alone and says so (see
  // hotPixelsSkippedCaption); the export still cleans the frame. Absent on an
  // older backend.
  hot_pixels_preview_skipped?: boolean;
  // Robust per-channel sky-background medians + colour-cast verdict over the
  // finished display image (sky population only, so stars/target don't pull it),
  // so the editor can show whether the background ended up neutral (see
  // skyCastCaption). Absent on an older backend.
  sky_cast?: SkyCast;
  // True when this run is already in display space (a re-opened editor export, so
  // no default stretch runs). The one-click "Neutralize background" fix only lands
  // in display space — where the cast is measured — when an explicit stretch is
  // enabled OR the run is already display-space, so the editor only offers it then.
  // Absent on an older backend (treated as false).
  already_display?: boolean;
  // Which white-balance path an enabled colour-calibration op ran on this live
  // preview (the one-click Auto recipe includes one), so the editor can show the
  // same read-out the History Info panel shows for the autonomous auto-edit (see
  // autoColorCalCaption). null/absent when no colour-cal op ran or on an older
  // backend. On the decimated proxy Gaia falls back to gray-star, so mode_used
  // here reflects what the preview actually applied.
  color_cal?: AutoColorCal | null;
}

export interface SkyCast {
  r: number | null;
  g: number | null;
  b: number | null;
  neutral: boolean;
  cast: string;
  deviation: number;
}

// Which white-balance path the unattended auto-edit ran. `mode_used` is one of
// "gray_star" | "gaia" (star-based), "background_neutral" (the too-few-stars
// fallback), or "none" (couldn't balance at all).
export interface AutoColorCal {
  mode_used: string;
  n_stars_used: number;
  notes?: string;
  // True only on a *live preview* whose decimated proxy held too few resolvable
  // stars for the star-based balance the full-res export will manage — i.e. the
  // colour on screen is genuinely not the colour that gets saved. Absent on a
  // full-res render and on an older backend.
  proxy_fallback?: boolean;
}

export interface PsfSuggestion {
  fwhm_px: number | null;
  psf_sigma: number | null;
}

export interface DenoiseSuggestion {
  noise_sigma: number | null;
  strength: number | null;
}

export interface SharpenSuggestion {
  fwhm_px: number | null;
  radius: number | null;
}

export interface StarSizeSuggestion {
  fwhm_px: number | null;
  size: number | null;
}

export interface LevelsSuggestion {
  /** Data-driven black/white points for the Levels op, or null when there's no
   * useful suggestion (too few finite pixels / a near-empty range). */
  black: number | null;
  white: number | null;
  /** Optional midtone (gamma) lift that lands the typical tone at a pleasant grey
   * after the black/white points; null when no meaningful lift exists. */
  gamma?: number | null;
  /** The display-space grey (0..1) the gamma lift aims for, so the UI can name the
   * goal the number solves for; null when there's no gamma suggestion. */
  gamma_target?: number | null;
}

export interface StretchSuggestion {
  /** Data-driven asinh Strength + Black point for the tone.stretch op, or null
   * when there's no useful suggestion (too few finite pixels / no dynamic range). */
  stretch: number | null;
  black: number | null;
  /** The display-space grey (0..1) the strength lands the sky median at, so the UI
   * can name the goal the number solves for; null when there's no suggestion. */
  target_bg?: number | null;
}

export interface HighlightSuggestion {
  /** The smallest "Hold back highlights" step that reopens the run's blown-out
   * bright core, or null when there's no suggestion — no bright core, one too
   * small to be anything but a star, one barely clipped, one already saturated
   * at capture (nothing to bring back), or one the knob can't meaningfully
   * reopen. The button hides on null rather than implying a problem. */
  strength: number | null;
  /** Share (0..1) of that core rendering flat white today while still carrying
   * structure in the linear data — the severity the button can name. */
  flat_fraction?: number | null;
  /** Size of the measured core in proxy pixels. */
  core_px?: number | null;
}

export interface CurveSuggestion {
  /** Ordered [x, y] control points for a gentle starting tone curve, or null when
   * there's no useful suggestion (too few finite pixels / degenerate range /
   * typical tone already at or above the target grey). */
  points: [number, number][] | null;
  /** The display-space grey (0..1) the midtone lift aims for, so the UI can name
   * the goal the curve solves for; null when there's no suggestion. */
  target_bg?: number | null;
}

export interface TrimSuggestion {
  is_mosaic: boolean;
  /** Fractional (0..1) crop rectangle for the largest well-covered area, or null
   * when there's nothing worth trimming (single-field / uniform / full-frame). */
  crop: { x0: number; y0: number; x1: number; y1: number } | null;
}

export interface CalibrationMaster {
  id: number;
  name: string;
  kind: "dark" | "flat" | "bias";
  filename: string;
  n_frames: number;
  method: string;
  exposure_s: number | null;
  gain: number | null;
  sensor_temp_c: number | null;
  bayer_pattern: string | null;
  width_px: number;
  height_px: number;
  created_utc: string;
  exists: boolean;
}

// A Seestar Moon/Sun video capture sitting in the incoming folder (a `*_video/`
// folder the deep-sky scanner skips), and its finished lucky-imaging still if
// one has been made.
export interface VideoFile {
  name: string;
  size_bytes: number;
}

// What one "how picky should we be?" setting would give you on this capture,
// measured from the grading pass's own per-frame scores.
export interface VideoKeepOption {
  percent: number;
  n_frames: number;
  // Median sharpness of the kept frames ÷ that of a typical frame in the capture.
  sharpness_vs_typical: number;
  // √N — roughly how much cleaner than a single frame the average is.
  noise_gain: number;
}

// "How steady was your capture?" — optional, because a still stacked by an older
// version didn't keep the scores. Absent → the panel simply doesn't render.
export interface VideoSharpnessProfile {
  // Frame scores sharpest-first, rescaled so the best frame is 1.0.
  curve: number[];
  // Where the setting used falls along that curve, 0..1.
  cut_fraction: number;
  options: VideoKeepOption[];
  suggested_percent: number;
  spread: "steady" | "mixed" | "variable";
  summary: string;
}

// The sharpest single frame a "Check this capture" pass found. It answers "is
// this capture worth stacking at all?" — a cloud, a drift out of frame, a soft
// focus — in a couple of seconds rather than a couple of minutes. `note` is the
// backend's own sentence, and it says plainly that this is one noisy frame and
// the stack is the picture.
export interface VideoQuickLook {
  url: string;
  frame_number: number;
  n_graded: number;
  note: string;
}

export interface VideoResult {
  created_utc: string;
  source_name: string;
  width: number;
  height: number;
  keep_percent: number;
  n_graded: number;
  n_kept: number;
  n_stacked: number;
  n_align_failed: number;
  stride: number;
  warnings: string[];
  preview_url: string;
  tiff_url: string;
  sharpness?: VideoSharpnessProfile | null;
  // Framing. `crop_applied` — the still was trimmed to the disk, so width/height
  // are the cropped size and `source_*` the stack's own. `crop_available` — it
  // wasn't, and there is enough empty sky around the disk to be worth offering.
  // All optional: an older backend sends none of them and nothing is claimed.
  crop_applied?: boolean;
  crop_available?: boolean;
  // Fraction of the frame the crop trims, or would trim (0..1).
  crop_trim_fraction?: number;
  source_width?: number;
  source_height?: number;
  // How hard this picture was sharpened (0 = not at all). Optional: a still
  // stacked before sharpening existed sends nothing and reads as unsharpened.
  sharpen_amount?: number;
  // True when that strength can still be changed from the saved picture, with no
  // second decode. Optional/false from an older backend, which then simply
  // doesn't offer the control.
  sharpen_editable?: boolean;
  // True when the still was cropped in place and its full frame is still saved
  // beside it, so the crop can be undone in one click.
  crop_restorable?: boolean;
}

export interface VideoCapture {
  id: string;
  label: string;
  kind: "lunar" | "solar" | "other";
  folder_name: string;
  files: VideoFile[];
  total_bytes: number;
  result: VideoResult | null;
  // The grade-only pass ("Check this capture"), when one has been run. Optional:
  // an older backend never sends it and the panel simply doesn't appear.
  sharpness?: VideoSharpnessProfile | null;
  // The sharpest frame that same pass found. Optional and independent of
  // `sharpness`: a grade recorded before the quick look existed has the scores
  // but no picture, and nothing renders.
  quicklook?: VideoQuickLook | null;
}

export interface VideoList {
  // False when the container has no ffmpeg — the page shows `hint` instead of
  // offering a button that could only fail.
  available: boolean;
  hint: string | null;
  incoming_dir: string;
  captures: VideoCapture[];
}

// "Do my masters actually cover my targets?" — for each master, how many of the
// library's targets the *unattended* binder would apply it to (so the roll-up
// promises exactly what the app does on its own), plus the targets no master
// covers at all.
export interface CalibrationCoverage {
  n_targets: number;
  masters: {
    id: number;
    name: string;
    kind: string;
    n_covered: number;
    covered: string[];
    missed: string[];
    // Why each missed target misses, in one plain-language clause ("your subs are
    // 10s, this dark is 30s"). Optional: an older backend sends only `missed`, so
    // the tooltip falls back to the bare name list.
    missed_detail?: { name: string; reason: string }[];
  }[];
  uncovered: string[];
  // The acquisition numbers each uncovered target would need a dark shot at —
  // what turns "build a matching dark" into something a beginner can act on.
  // Optional: an older backend omits it and the nudge stays generic.
  uncovered_detail?: { name: string; exposure_s: number | null; gain: number | null }[];
  // Whether auto-calibration is actually switched on. With it off (the default) a
  // "covered" master is one the app *can* apply — the user still picks it on the
  // Stack form — so the page must not promise it will be used automatically.
  // Optional: an older backend omits it (treated as off).
  auto_apply?: boolean;
}

export interface CalibrationSuggestions {
  params: {
    exposure_s: number | null; gain: number | null; sensor_temp_c: number | null;
    // The target's modal raw frame size, so the form can flag a master built
    // for a different camera/binning (which would fail the stack outright).
    // Optional: an older backend omits them.
    width_px?: number | null; height_px?: number | null;
  };
  dark_master_id: number | null;
  flat_master_id: number | null;
  flat_dark_master_id: number | null;
  bias_master_id: number | null;
  scores: Record<string, number>;
  n_frames: number;
  // The engine's own exposure/temperature mismatch thresholds, so the Stack
  // form's pick-time warnings fire on exactly the pairs the finished run will
  // complain about. Optional: an older backend omits it and the form falls back
  // to its mirrored constants (see `calibrationFit.ts`).
  tolerances?: { exposure_frac?: number | null; temp_c?: number | null } | null;
  // What the *unattended* stack would bind for these same subs — the stricter
  // "best master we're confident about", as opposed to the fields above, which
  // are the best master of each kind you own. The two can disagree, so the form
  // prefers these where they exist and its "Use recommended" then lands on the
  // masters a walk-away stack would have used. Absent on an older backend, and
  // an empty object means "nothing confident" — in both cases the form keeps its
  // best-available recommendation and its existing cautions.
  confident?: {
    dark_master_id?: number | null;
    flat_master_id?: number | null;
    flat_dark_master_id?: number | null;
    bias_master_id?: number | null;
    scale_dark_to_light?: boolean | null;
  } | null;
}

export interface UploadResult {
  target: string;   // folder the files landed in ("" = Unsorted)
  saved: { name: string; bytes: number }[];
  skipped: { name: string; bytes: number }[];   // already present
  rejected: { name: string; reason: string }[]; // not FITS / unsafe / no room
  bytes_written: number;
  job_id: string | null;
  folders?: string[];  // top-level folders kept from a folder drop (may be absent)
}

function encodeRecipe(recipe: Recipe): string {
  const bytes = new TextEncoder().encode(JSON.stringify(recipe));
  let bin = "";
  bytes.forEach((b) => (bin += String.fromCharCode(b)));
  return btoa(bin).replace(/\+/g, "-").replace(/\//g, "_");
}

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      detail = (await res.json()).detail ?? detail;
    } catch {
      /* ignore */
    }
    throw new Error(`${res.status}: ${detail}`);
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

/** Body for the two Auto endpoints' optional per-run "trim the ragged border?"
 * override. `undefined` sends no body at all, which the backend reads as "use the
 * saved `auto_crop_border` setting" — so the default call is byte-identical to
 * what every earlier build sent. */
function autoCropBody(autoCrop?: boolean): { body?: string } {
  return autoCrop === undefined ? {} : { body: JSON.stringify({ auto_crop: autoCrop }) };
}

export const api = {
  // targets
  listTargets: () => req<Target[]>("/api/targets"),
  getTarget: (safe: string) => req<Target>(`/api/targets/${safe}`),
  createTarget: (name: string) =>
    req<Target>("/api/targets", { method: "POST", body: JSON.stringify({ name }) }),
  patchTarget: (safe: string, body: { notes?: string | null; tags?: string[] }) =>
    req<Target>(`/api/targets/${safe}`, { method: "PATCH", body: JSON.stringify(body) }),
  deleteTarget: (safe: string, removeFiles: boolean) =>
    req(`/api/targets/${safe}?remove_files=${removeFiles}`, { method: "DELETE" }),
  mergeTargets: (into: string, sources: string[]) =>
    req("/api/targets/merge", { method: "POST", body: JSON.stringify({ into, sources }) }),
  mergeSuggestions: () =>
    req<MergeSuggestion[]>("/api/targets/merge-suggestions"),
  cleanupSuggestions: () =>
    req<CleanupSuggestion[]>("/api/targets/cleanup-suggestions"),
  targetThumbnailUrl: (safe: string) => `/api/targets/${safe}/thumbnail`,
  identifyTarget: (safe: string) =>
    req<ObjectInfo | null>(`/api/targets/${safe}/identify`),
  sessionRecap: (safe: string) =>
    req<SessionRecap | null>(`/api/targets/${safe}/session-recap`),
  // "Tonight, live" — the session happening right now (or the trailing one, with
  // `active` false). Polled while the page is open, so it stays cheap: a
  // read-only aggregation of the frames table, no pixels touched.
  liveSession: (safe: string) =>
    req<LiveSession | null>(`/api/targets/${safe}/live-session`),
  autoStackHold: (safe: string) =>
    req<AutoStackHold | null>(`/api/targets/${safe}/autostack-hold`),
  cleanestShot: (safe: string) =>
    req<CleanestShot | null>(`/api/targets/${safe}/cleanest-shot`),
  grainierNewest: (safe: string) =>
    req<GrainierNewest | null>(`/api/targets/${safe}/grainier-newest`),
  // "This picture was made by an older AstroStack" — what a re-stack would give
  // back, named as a gain. `null` (the common case) means say nothing.
  restackGain: (safe: string) =>
    req<RestackGain | null>(`/api/targets/${safe}/restack-gain`),
  stackHealth: (safe: string, runId?: number) =>
    req<StackHealth | null>(
      `/api/targets/${safe}/stack-health` +
        (runId != null ? `?run_id=${runId}` : ""),
    ),
  bestFrame: (safe: string) =>
    req<BestFrame>(`/api/targets/${safe}/best-frame`),
  targetNights: (safe: string) =>
    req<NightSummary[]>(`/api/targets/${safe}/nights`),
  focusTrend: (safe: string) =>
    req<FocusTrend | null>(`/api/targets/${safe}/focus-trend`),
  transparencyTrend: (safe: string) =>
    req<TransparencyTrend | null>(`/api/targets/${safe}/transparency-trend`),
  // `want` asks for more than the default three windows — the finish forecast
  // counts to the n-th window for an n-night goal, so a 5-night goal needs 5.
  // The 14-night scan behind it is unchanged, so this is a bigger slice of the
  // same search; omit it and the response is byte-for-byte what it always was.
  nextSession: (safe: string, want?: number) =>
    req<NextSession>(`/api/plan/next-session/${safe}`
      + (want ? `?want=${encodeURIComponent(String(want))}` : "")),
  // Download URL for the next-session windows as a .ics calendar file (one-tap
  // "Add to calendar"). A plain href/download, not a fetch — the browser hands
  // the file to the OS calendar.
  nextSessionIcsUrl: (safe: string) =>
    `/api/plan/next-session/${safe}/calendar.ics`,
  // "Best time of year to shoot this" — twelve months of observability for a
  // known target (empty months ⇒ the strip self-hides).
  bestMonths: (safe: string) =>
    req<BestMonths>(`/api/plan/best-months/${safe}`),
  // "Is the Moon going to wash this out tonight?" — a Moon-interference readout
  // for a known target (null moon ⇒ the card self-hides).
  moonInterference: (safe: string) =>
    req<MoonInterferenceResponse>(`/api/plan/moon/${safe}`),
  // "Try something new tonight" — famous showpieces the user hasn't captured
  // that are well-placed tonight (empty list ⇒ the card self-hides).
  suggestTargets: () => req<SuggestResponse>(`/api/plan/suggest`),
  // Download URL for a *suggested* (not-yet-captured) showpiece's next windows as
  // a .ics calendar file. Catalog ids can contain spaces ("NGC 7000"), so encode.
  suggestIcsUrl: (catalogId: string) =>
    `/api/plan/suggest/${encodeURIComponent(catalogId)}/calendar.ics`,
  // Download URL for "Your imaging log" — a plain CSV record of every finished
  // stack (date, target, subs, integration, sharpness, calibration, noise). A
  // href/download, not a fetch: the browser saves the file.
  imagingLogUrl: () => `/api/imaging-log.csv`,
  getIntegrationGoal: (safe: string) =>
    req<{ goal_s: number | null }>(`/api/targets/${safe}/integration-goal`),
  setIntegrationGoal: (safe: string, goalS: number | null) =>
    req<{ goal_s: number | null }>(`/api/targets/${safe}/integration-goal`, {
      method: "PUT",
      body: JSON.stringify({ goal_s: goalS }),
    }),

  // frames
  // Page through the whole target rather than capping at one request: one good
  // S30 night is ~2,100 × 10 s subs, so a fixed limit silently hid the newest
  // frames from the table, keyboard grading, "Reject worst" ordering and the
  // Stack pre-flight guards. We fetch fixed-size pages until a short page proves
  // we've reached the end, so callers always receive the complete, consistently
  // sorted list.
  listFrames: async (safe: string, sort = "id", order = "asc"): Promise<Frame[]> => {
    const pageSize = 2000;
    const all: Frame[] = [];
    for (let offset = 0; ; offset += pageSize) {
      const page = await req<Frame[]>(
        `/api/targets/${safe}/frames?sort=${sort}&order=${order}&limit=${pageSize}&offset=${offset}`,
      );
      all.push(...page);
      if (page.length < pageSize) break;
    }
    return all;
  },
  patchFrame: (safe: string, id: number, body: Record<string, unknown>) =>
    req<Frame>(`/api/targets/${safe}/frames/${id}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),
  bulkFrames: (safe: string, body: Record<string, unknown>) =>
    req<{ changed: number; changed_ids: number[]; note?: string | null }>(
      `/api/targets/${safe}/frames/bulk`,
      { method: "POST", body: JSON.stringify(body) },
    ),
  // Opt-in "set this night aside": reject the accepted subs of one capture night
  // (bounded by a NightSummary's start/end). Returns the touched ids for undo.
  setAsideNight: (safe: string, start_utc: string, end_utc: string) =>
    req<{ changed: number; changed_ids: number[] }>(
      `/api/targets/${safe}/frames/set-aside-night`,
      { method: "POST", body: JSON.stringify({ start_utc, end_utc }) },
    ),
  // "Those subs are gone — carry on without them." Database-only and undone
  // automatically by the next scan if the files come back.
  setMissingAside: (safe: string) =>
    req<{ changed: number; changed_ids: number[] }>(
      `/api/targets/${safe}/frames/set-missing-aside`, { method: "POST" },
    ),
  rejectSummary: (safe: string) =>
    req<{
      counts: Record<string, number>;
      total: number;
      // Server-side plate-solve *setup* classification (v0.84.1+). Reliable for
      // the star-database case too; older backends omit it and the frontend
      // falls back to detecting it from `counts`.
      solve_setup_problem?: { kind: "astap" | "database"; frames: number } | null;
      // Plain-language grouped "why were some frames left out?" breakdown
      // (v0.159.2+). Older backends omit it, so it's optional.
      summary?: RejectionSummary;
      // Storage preflight (v0.232.0+): accepted subs whose files aren't on disk
      // right now, and the accepted total they were counted over. Older backends
      // omit both, so the callout self-hides.
      n_missing_files?: number;
      n_accepted?: number;
    }>(
      `/api/targets/${safe}/frames/reject-summary`,
    ),
  // Was the sky on this target's latest night brighter than usual? Derived from
  // the sky level QC already measures on every sub. `read` is null whenever the
  // data can't support an honest answer, so the card self-hides.
  skyBrightness: (safe: string) =>
    req<{ read: SkyBrightnessRead | null }>(
      `/api/targets/${safe}/frames/sky-brightness`,
    ),
  autoGradePreview: (safe: string, sensitivity?: string) =>
    req<GradeReport>(
      `/api/targets/${safe}/frames/auto-grade${sensitivity ? `?sensitivity=${sensitivity}` : ""}`,
    ),
  autoGradeApply: (safe: string, sensitivity?: string) =>
    req<GradeReport>(
      `/api/targets/${safe}/frames/auto-grade/apply${sensitivity ? `?sensitivity=${sensitivity}` : ""}`,
      { method: "POST" },
    ),
  framePreviewUrl: (safe: string, id: number, size = 640, bayer?: string) =>
    `/api/targets/${safe}/frames/${id}/preview?size=${size}${bayer ? `&bayer=${bayer}` : ""}`,

  // stack
  optionsSchema: () => req<StackOptionField[]>("/api/stack/options/schema"),
  getStackDefaults: (safe: string) =>
    req<Record<string, unknown>>(`/api/targets/${safe}/stack-defaults`),
  putStackDefaults: (safe: string, body: Record<string, unknown>) =>
    req<Record<string, unknown>>(`/api/targets/${safe}/stack-defaults`, {
      method: "PUT",
      body: JSON.stringify(body),
    }),
  triggerStack: (safe: string, options: Record<string, unknown>) =>
    req<{ job_id: string }>(`/api/targets/${safe}/stack`, {
      method: "POST",
      body: JSON.stringify(options),
    }),
  listStackRuns: (safe: string) => req<StackRun[]>(`/api/targets/${safe}/stack-runs`),
  deleteStackRun: (safe: string, id: number) =>
    req(`/api/targets/${safe}/stack-runs/${id}`, { method: "DELETE" }),
  // Pin a run as the target's showcase "cover" (or clear with run_id null).
  setTargetCover: (safe: string, run_id: number | null) =>
    req<Target>(`/api/targets/${safe}/cover`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ run_id }),
    }),
  updateStackRunNotes: (safe: string, id: number, notes: string) =>
    req<{ id: number; notes: string | null }>(
      `/api/targets/${safe}/stack-runs/${id}`,
      { method: "PATCH", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ notes }) }),
  stackRunInfo: (safe: string, id: number) =>
    req<StackRunInfo>(`/api/targets/${safe}/stack-runs/${id}/info`),
  stackRunOptions: (safe: string, id: number) =>
    req<{ run_id: number; options: Record<string, unknown> }>(
      `/api/targets/${safe}/stack-runs/${id}/options`),
  stackEstimate: (
    safe: string,
    opts: {
      drizzle?: boolean; drizzle_scale?: number; drizzle_reject?: boolean;
      mosaic_canvas?: string; min_max_reject?: boolean; min_max_reject_count?: number;
      auto_reject?: boolean; sigma_kappa?: number; sigma_clip?: boolean;
    },
  ) => {
    const p = new URLSearchParams();
    if (opts.drizzle) p.set("drizzle", "true");
    if (opts.drizzle_scale != null) p.set("drizzle_scale", String(opts.drizzle_scale));
    if (opts.drizzle_reject) p.set("drizzle_reject", "true");
    if (opts.mosaic_canvas) p.set("mosaic_canvas", opts.mosaic_canvas);
    // Rejection knobs affect memory (extra min/max passes hold 2k canvas planes),
    // so pass them through to keep the pre-submit peak honest for a k>1 reject.
    if (opts.min_max_reject) p.set("min_max_reject", "true");
    if (opts.min_max_reject_count != null) p.set("min_max_reject_count", String(opts.min_max_reject_count));
    if (opts.auto_reject) p.set("auto_reject", "true");
    if (opts.sigma_kappa != null) p.set("sigma_kappa", String(opts.sigma_kappa));
    // Not a sizing knob — the backend defaults it to true (StackOptions' own
    // default) and reads it only for `rejection_reach`, so an unticked sigma
    // clip has to be said explicitly or the reach answer describes a stack the
    // user isn't running.
    if (opts.sigma_clip != null) p.set("sigma_clip", opts.sigma_clip ? "true" : "false");
    return req<StackEstimate>(`/api/targets/${safe}/stack-estimate?${p.toString()}`);
  },
  rejectionOutlook: (safe: string) =>
    req<RejectionOutlook>(`/api/targets/${safe}/rejection-outlook`),
  stackArtifactUrl: (
    safe: string, id: number, kind: "preview" | "jpeg" | "fits" | "tiff",
    northUp = false, nameplate = false, keepsake = false, scale = false,
    labelObjects = false,
  ) => {
    const base = `/api/targets/${safe}/stack-runs/${id}/${kind}`;
    if (kind !== "jpeg") return base;
    // Only the share-friendly JPEG honours north_up (rotate so North is up),
    // nameplate (bake the acquisition-data caption over the picture), keepsake
    // (mat the picture on a dark card with its name and acquisition data set
    // beneath it, for printing or posting), scale (draw the angular scale bar
    // and the North/East compass onto the picture, from the run's own solve) and
    // label_objects (draw the named catalog objects in the field — the same pins
    // the "What's in it?" overlay shows, baked in so they travel with the file).
    const params: string[] = [];
    if (northUp) params.push("north_up=true");
    if (nameplate) params.push("nameplate=true");
    if (keepsake) params.push("keepsake=true");
    if (scale) params.push("scale=true");
    if (labelObjects) params.push("label_objects=true");
    return params.length ? `${base}?${params.join("&")}` : base;
  },
  // The run's *stored* preview PNG, turned so celestial North is up — the saved
  // bytes rotated on the way out, not a re-render. Deliberately its own helper
  // rather than a flag on `stackArtifactUrl`: the bare artifact URLs stay
  // WCS-aligned for every surface that embeds them, and only a caller that wants
  // to *look at* a turn on a picture it must not replace asks for this.
  stackPreviewNorthUpUrl: (safe: string, id: number) =>
    `/api/targets/${safe}/stack-runs/${id}/preview?north_up=true`,
  // "See what stacking removed" — a transparent PNG tinting where outlier
  // rejection dropped samples, sized to the run's stored preview so it lays
  // straight over it. Only runs whose `rejection.has_map` is true have one.
  // `northUp` composes the same on-the-fly turn `stackPreviewNorthUpUrl` applies
  // to the picture underneath, so the tint stays in register with a North-up
  // *view* instead of having to step aside; off by default, so the bare URL is
  // unchanged for every surface that already embeds it.
  stackRejectionOverlayUrl: (safe: string, id: number, northUp = false) =>
    `/api/targets/${safe}/stack-runs/${id}/rejection-overlay` +
    (northUp ? "?north_up=true" : ""),
  // "Make it your wallpaper" — the finished preview cropped to a device aspect
  // (phone/desktop/square), auto-centred on the target, downloaded as a JPEG.
  stackWallpaperUrl: (
    safe: string, id: number, aspect: "phone" | "desktop" | "square",
    northUp = false,
  ) => `/api/targets/${safe}/stack-runs/${id}/wallpaper?aspect=${aspect}` +
    (northUp ? "&north_up=true" : ""),
  // "Zoom clip" — a short looping push-in on the finished picture and back out,
  // for posting somewhere that rewards motion. Built and cached server-side from
  // the run's own preview; a run with no preview simply has none.
  stackZoomClipUrl: (safe: string, id: number) =>
    `/api/targets/${safe}/stack-runs/${id}/zoom-clip`,
  // "What's in this picture?" — catalog objects that fall inside a run's field.
  stackAnnotations: (safe: string, id: number) =>
    req<StackAnnotations>(`/api/targets/${safe}/stack-runs/${id}/annotations`),
  stackFraming: (safe: string, id: number) =>
    req<StackFraming | null>(`/api/targets/${safe}/stack-runs/${id}/framing`),
  // The finished picture as a native-resolution PNG (same look as the preview
  // thumbnail, just full-size instead of the 1024px preview cap) — the direct
  // answer to "why is my downloaded picture low-res?".
  stackFullResPngUrl: (safe: string, id: number, northUp = false) =>
    `/api/targets/${safe}/stack-runs/${id}/full-res-png` +
    (northUp ? "?north_up=true" : ""),
  stackRenderUrl: (
    safe: string, id: number, stretch: number, black: number, northUp = false,
  ) =>
    `/api/targets/${safe}/stack-runs/${id}/render?stretch=${stretch}&black=${black}` +
    (northUp ? "&north_up=true" : ""),
  stackRenderSuggestion: (safe: string, id: number) =>
    req<{
      stretch: number | null; black: number | null; target_bg?: number;
      // The rotation (deg) that puts celestial North up, or null when the run has
      // no usable WCS / the correction is trivial (so no "North up" toggle).
      north_up_deg?: number | null;
      // True when the picture on screen is a *processed* one (the one-click
      // "Process target" Auto edit), so a plain slider save would replace it
      // with a flat stretch of the raw stack — the panel warns before the fact.
      processed_preview?: boolean;
      // …and true when that run's recipe is still on disk, so the save can
      // re-bake the processed picture instead (rotation and all).
      can_keep_processed?: boolean;
    }>(`/api/targets/${safe}/stack-runs/${id}/render-suggestion`),
  // "One frame vs your stack" reveal — a single raw sub next to the finished
  // stack, so a beginner sees what stacking bought them.
  oneSubVsStack: (safe: string, id: number) =>
    req<{
      available: boolean;
      n_frames: number | null;
      sub_exposure_s: number | null;
      integration_s: number | null;
      // How the two halves were made comparable: "stretch" (a plain linear run,
      // both rendered through the same tone curve) or "recipe" (a "Process
      // target" Auto edit, both put through that run's own edit). Optional so an
      // older backend that doesn't send it still reads as the plain case.
      matched_by?: string | null;
    }>(`/api/targets/${safe}/stack-runs/${id}/one-sub-vs-stack`),
  // The concrete "stacking cut your noise ~N×" number (lazy, best-effort — null
  // for an edited/older run or an unmeasurable image).
  // `expected_verdict` is the engine's reading of the ratio against √N
  // ("expected" | "low" | null, from `seestack.stackhealth.noise_vs_expected`) —
  // the same judgement the "How's my stack?" note uses, so the threshold lives
  // in one place rather than being re-typed here.
  // `expected_frames` is the N that verdict was made against and
  // `expected_basis` says which count it is: "stack" (the run's own frames) or
  // "mosaic_centre" (the depth at the crop the ratio was measured over, the only
  // honest yardstick on a mosaic canvas). Both optional, so an older backend
  // still reads as the plain single-field case.
  oneSubVsStackNoise: (safe: string, id: number) =>
    req<{
      ratio: number | null;
      expected_verdict?: string | null;
      expected_frames?: number | null;
      expected_basis?: string | null;
      // The run's own canvas flag, served beside the basis so the celebratory
      // badge can drop its sub count on a mosaic even when no verdict resolved.
      is_mosaic?: boolean | null;
    }>(
      `/api/targets/${safe}/stack-runs/${id}/one-sub-vs-stack/noise`),
  stackReferenceSubUrl: (safe: string, id: number) =>
    `/api/targets/${safe}/stack-runs/${id}/reference-sub`,
  // "Share your glow-up" — the reveal composed into one labelled, captioned
  // JPEG you can post. 404s on exactly the runs the reveal itself hides on, so
  // the button only ever appears where the card does.
  stackBeforeAfterUrl: (safe: string, id: number) =>
    `/api/targets/${safe}/stack-runs/${id}/before-after.jpg`,
  // "Watch your picture come together" progress reel (opt-in save_progress).
  stackProgressInfo: (safe: string, id: number) =>
    req<{ available: boolean; frames: number; format?: string }>(
      `/api/targets/${safe}/stack-runs/${id}/progress-info`),
  stackProgressUrl: (safe: string, id: number) =>
    `/api/targets/${safe}/stack-runs/${id}/progress`,
  // "Night after night" cross-run deepening reel (per target, ≥2 stacks).
  deepeningReelInfo: (safe: string) =>
    req<{
      available: boolean;
      n_stacks: number;
      first_subs?: number;
      last_subs?: number;
      first_utc?: string | null;
      last_utc?: string | null;
      format?: string;
    }>(`/api/targets/${safe}/deepening-reel/info`),
  deepeningReelUrl: (safe: string) => `/api/targets/${safe}/deepening-reel`,
  saveStackPreview: (
    safe: string, id: number, stretch: number, black: number, northUp = false,
    keepProcessed = false,
  ) =>
    req<{ ok: boolean }>(`/api/targets/${safe}/stack-runs/${id}/preview`, {
      // north_up saves the image rotated so North is up, matching what the user
      // sees on screen when they save with the History "North up" toggle on.
      // keep_processed re-bakes a processed run's own saved edit instead of the
      // sliders, so rotating a finished picture doesn't flatten it (default
      // false — the plain stretch save, unchanged).
      method: "POST",
      body: JSON.stringify({ stretch, black, north_up: northUp,
                             ...(keepProcessed ? { keep_processed: true } : {}) }),
    }),

  // pipeline
  scan: () => req<{ job_id: string }>("/api/scan", { method: "POST", body: "{}" }),
  uploadFits: (
    fileList: File[],
    target: string,
    onProgress?: (loaded: number, total: number) => void,
    preserveFolders = false,
  ) => {
    // Multipart upload via XHR (not fetch) so we can report *upload* progress —
    // fetch exposes no upload-progress event, and a beginner sending several GB
    // over the browser needs to see it moving. The browser still sets the
    // multipart boundary Content-Type from the FormData body.
    const form = new FormData();
    if (target.trim()) form.append("target", target.trim());
    // Ask the server to keep the dropped folder's *directories* rather than
    // flattening them into filenames, so the scanner's Seestar folder convention
    // makes the real targets (M 31_sub → "M 31") instead of one Unsorted pile.
    // Only sent when we actually have folder paths, so a plain multi-file pick
    // posts exactly the body it always did.
    if (preserveFolders) form.append("preserve_folders", "true");
    // Send the file's folder-relative path when we have one (a folder drop bakes
    // it into ``name``; a ``webkitdirectory`` input exposes ``webkitRelativePath``)
    // so the server can keep two same-named subs from different session folders
    // distinct instead of dropping one as a duplicate.
    for (const f of fileList) form.append("files", f, f.webkitRelativePath || f.name);
    return new Promise<UploadResult>((resolve, reject) => {
      const xhr = new XMLHttpRequest();
      xhr.open("POST", "/api/upload");
      if (onProgress) {
        xhr.upload.onprogress = (e) => {
          if (e.lengthComputable) onProgress(e.loaded, e.total);
        };
      }
      xhr.onload = () => {
        if (xhr.status >= 200 && xhr.status < 300) {
          try {
            resolve(JSON.parse(xhr.responseText) as UploadResult);
          } catch {
            reject(new Error("The server sent back a response we couldn't read."));
          }
          return;
        }
        let detail = xhr.statusText;
        try {
          detail = JSON.parse(xhr.responseText).detail ?? detail;
        } catch {
          /* ignore — keep the status text */
        }
        reject(new Error(`${xhr.status}: ${detail}`));
      };
      xhr.onerror = () =>
        reject(new Error("Upload failed — check your connection and try again."));
      xhr.send(form);
    });
  },
  qcSolve: (safe: string) =>
    req<{ job_id: string }>(`/api/targets/${safe}/qc-solve`, { method: "POST" }),
  processTarget: (safe: string) =>
    req<{ job_id: string }>(`/api/targets/${safe}/process`, { method: "POST" }),

  // jobs
  // Ask for the whole retained history (up to the backend's hard 2000 cap), not
  // the endpoint's silent default of 100 — otherwise the "Job history to keep"
  // setting (default 200) has no visible effect and "Clear finished" looks like
  // it deletes fewer jobs than it actually does (it clears DB-wide). Callers must
  // invoke it with no args (or an explicit number); never pass it straight as a
  // TanStack `queryFn`, which would hand the query context in as `limit`.
  listJobs: (limit = 2000) => req<Job[]>(`/api/jobs?limit=${limit}`),
  clearJobs: () => req<{ removed: number }>("/api/jobs/clear", { method: "POST" }),
  getJob: (id: string) => req<Job>(`/api/jobs/${id}`),
  cancelJob: (id: string) => req(`/api/jobs/${id}/cancel`, { method: "POST" }),

  // settings / system
  getSettings: () => req<Settings>("/api/settings"),
  putSettings: (patch: Record<string, unknown>) =>
    req<Settings>("/api/settings", { method: "PUT", body: JSON.stringify(patch) }),
  settingsExportUrl: () => "/api/settings/export",
  importSettings: (config: Record<string, unknown>) =>
    req<Settings>("/api/settings/import", {
      method: "POST",
      body: JSON.stringify(config),
    }),
  getSystem: () => req<SystemInfo>("/api/system"),
  astapTest: () => req<{
    ok: boolean; detail?: string | null; solved?: boolean; target?: string;
    frame?: string; ra_deg?: number | null; dec_deg?: number | null; elapsed_s?: number;
  }>("/api/system/astap-test", { method: "POST" }),
  reprocessAll: (staleOnly = false, deepRescan = false, autoEdit = false) =>
    req<{ job_id: string; already_running: boolean }>("/api/reprocess-all", {
      method: "POST",
      body: JSON.stringify({
        stale_only: staleOnly, deep_rescan: deepRescan, auto_edit: autoEdit,
      }),
    }),
  reprocessStatus: () => req<ReprocessStatus>("/api/reprocess-status"),
  autoCastSummary: () => req<AutoCastSummary>("/api/auto-cast-summary"),

  // sky viewer
  getSky: () => req<SkyData>("/api/sky"),
  /** The all-sky "My map" PNG, built server-side from the owner's own pictures. */
  myMapUrl: () => "/api/sky/my-map.png",
  /**
   * How much sky those pictures actually cover, measured from each run's own
   * WCS — never by counting pixels on the map, which is a non-equal-area
   * projection that also draws every picture larger than life. Pictures that
   * overlap on the sky are counted once; `summed_deg2` is what plain addition
   * would have said (absent on an older backend).
   */
  skyCoverage: () =>
    req<{
      deg2: number; sky_fraction: number; n_pictures: number;
      whole_sky_deg2: number; summed_deg2?: number;
    }>("/api/sky/coverage"),
  /** "Your universe" — the captured objects placed in depth by catalog distance. */
  getUniverse: () => req<UniverseData>("/api/sky/universe"),

  /** Targets whose most recent stack attempt failed, with nothing since. */
  getStackFailures: () => req<StackFailuresData>("/api/stack-failures"),

  // tonight — night planner. `date` (YYYY-MM-DD) plans an upcoming night instead
  // of tonight; omit it for tonight.
  getTonight: (opts?: { minAlt?: number; date?: string }) => {
    const qs = new URLSearchParams();
    if (opts?.minAlt != null) qs.set("min_alt", String(opts.minAlt));
    if (opts?.date) qs.set("date", opts.date);
    const suffix = qs.toString() ? `?${qs.toString()}` : "";
    return req<NightPlan>(`/api/plan/tonight${suffix}`);
  },
  // "Best use of your scope right now": the user's *own* targets ranked by how
  // well-placed they are at this moment × how much another hour would help.
  // Read-only; returns an empty `picks` when there's nothing worth suggesting.
  getBestTonight: (limit?: number) =>
    req<BestTonight>(
      `/api/plan/best-tonight${limit != null ? `?limit=${limit}` : ""}`,
    ),

  // "Plan my week": which of your own targets to point at, on which of the next
  // few nights — the cross-target, multi-night view `getTonight` (one night, all
  // targets) and `nextSession` (one target, many nights) don't give. Read-only;
  // an empty `nights` means the card self-hides.
  getPlanWeek: (opts?: { nights?: number; minAlt?: number }) => {
    const qs = new URLSearchParams();
    if (opts?.nights != null) qs.set("nights", String(opts.nights));
    if (opts?.minAlt != null) qs.set("min_alt", String(opts.minAlt));
    const suffix = qs.toString() ? `?${qs.toString()}` : "";
    return req<PlanWeek>(`/api/plan/week${suffix}`);
  },
  // Download URL for the planned week as a .ics calendar file — one event per
  // night that has a pick, so "Saturday is your M 31 night" survives closing the
  // tab. Takes the same options as `getPlanWeek` so the file matches the card
  // that offers it. A plain href/download, not a fetch.
  planWeekIcsUrl: (opts?: { nights?: number; minAlt?: number }) => {
    const qs = new URLSearchParams();
    if (opts?.nights != null) qs.set("nights", String(opts.nights));
    if (opts?.minAlt != null) qs.set("min_alt", String(opts.minAlt));
    const suffix = qs.toString() ? `?${qs.toString()}` : "";
    return `/api/plan/week/calendar.ics${suffix}`;
  },

  // life list
  // The famous objects you've captured and the ones still to get. Read-only and
  // offline: the catalog ships with the app and the match reads only the target
  // registry, so it is cheap enough to ask on every visit.
  getLifeList: () => req<LifeList>("/api/life-list"),
  nearlyThere: () => req<NearlyThere | null>("/api/life-list/nearly-there"),

  // gallery
  // `videos` is additive — an older backend doesn't send it, so read it as `?? []`.
  getGallery: () =>
    req<{ items: GalleryItem[]; videos?: VideoStill[] }>("/api/gallery"),
  // "My best pictures": the newest finished stack of every target, auto-ranked
  // best-first. Self-hides (empty items) until there are ≥2 finished pictures.
  getGalleryBest: (limit?: number) =>
    req<{ items: BestPicture[] }>(
      `/api/gallery/best${limit != null ? `?limit=${limit}` : ""}`,
    ),
  // How many pictures library-wide carry an edit that was saved and never
  // exported. Its own endpoint on purpose: it is deliberately cheap (one indexed
  // meta scan per target, no run listing), because the Dashboard asks it and
  // `/api/gallery` lists every run of every target.
  getUnexportedEdits: () =>
    req<{ count: number; items: UnexportedEditItem[] }>("/api/gallery/unexported-edits"),
  // Finish all of them in one cancellable job. The server re-scans and exports
  // exactly what the count above describes, so the browser never sends a list
  // that could have gone stale between the note rendering and the click.
  exportUnexportedEdits: () =>
    req<{ job_id: string; count: number }>("/api/gallery/unexported-edits/export",
      { method: "POST" }),

  // logs
  getLogs: (level?: string, limit = 1000) =>
    req<{ logs: LogEntry[]; last_seq: number }>(
      `/api/logs?limit=${limit}${level ? `&level=${level}` : ""}`,
    ),

  // dashboard
  getStats: () => req<DashboardStats>("/api/stats"),
  getLastNight: () => req<LibrarySessionRecap | null>("/api/last-night"),
  getActivityCalendar: (months = 12) =>
    req<ActivityCalendar>(`/api/activity-calendar?months=${months}`),
  getLibraryProgress: () => req<TargetProgress[]>("/api/library-progress"),
  getLibrarySummary: () => req<LibrarySummary>("/api/library/summary"),
  getLibraryMissingFiles: () => req<LibraryMissingFiles>("/api/library/missing-files"),
  getLibraryRecap: () => req<LibraryRecap>("/api/recap"),
  // Download URL for the recap poster — a square, social-ready JPEG rendered
  // from the same figures over the user's own best picture. A href/download,
  // not a fetch: the browser saves the image.
  recapPosterUrl: () => `/api/recap.jpg`,
  // "Your year under the stars" — the same nights the heatmap folds, clipped to
  // one calendar year. A year with nothing in it is a normal 200 whose
  // `years_with_data` says where the nights actually are.
  getYearRecap: (year: number) => req<YearRecap>(`/api/recap/year/${year}`),
  galleryMontageUrl: (limit?: number) =>
    `/api/gallery/montage.jpg${limit ? `?limit=${limit}` : ""}`,
  // Download URL for "all my pictures" — every target's current picture (its
  // pinned cover, else its newest stack) as one streamed .zip. Like the montage
  // and the recap poster this is a href/download, not a fetch: the browser saves
  // the archive, and nothing is written on the server.
  galleryPicturesZipUrl: () => `/api/gallery/pictures.zip`,

  // "Try it with a sample image" onboarding demo
  getSampleStatus: () => req<SampleStatus>("/api/sample"),
  loadSample: () => req<SampleStatus>("/api/sample", { method: "POST" }),
  removeSample: () => req<SampleStatus>("/api/sample", { method: "DELETE" }),

  // storage / housekeeping
  getStorage: () => req<StorageInfo>("/api/storage"),
  clearCache: (safe: string, stage: "stage1" | "stage2" | "thumbs" | "proxies" | "all") =>
    req<{ cleared: string[] }>(`/api/targets/${safe}/cache/clear?stage=${stage}`, {
      method: "POST",
    }),
  pruneStackRuns: (safe: string, body: { keep?: number; ids?: number[] }) =>
    req<{ deleted: number[] }>(`/api/targets/${safe}/stack-runs/prune`, {
      method: "POST",
      body: JSON.stringify(body),
    }),

  // seestar telescope
  getSeestarDevices: () => req<SeestarDevices>("/api/seestar/devices"),
  seestarScan: () => req<{ scanning: boolean }>("/api/seestar/scan", { method: "POST" }),
  seestarConnect: (ip: string) =>
    req<{ connected: string }>(`/api/seestar/${ip}/connect`, { method: "POST" }),
  seestarDisconnect: (ip: string) =>
    req<{ disconnected: string }>(`/api/seestar/${ip}/disconnect`, { method: "POST" }),
  seestarGoto: (ip: string, body: { ra_hours: number; dec_deg: number; target_name?: string }) =>
    req(`/api/seestar/${ip}/goto`, { method: "POST", body: JSON.stringify(body) }),
  seestarStop: (ip: string) => req(`/api/seestar/${ip}/stop`, { method: "POST" }),
  seestarPark: (ip: string) => req(`/api/seestar/${ip}/park`, { method: "POST" }),

  // editor
  editorOps: () => req<EditOp[]>("/api/editor/ops/schema"),
  psfSuggestion: (safe: string) =>
    req<PsfSuggestion>(`/api/targets/${safe}/editor/psf-suggestion`),
  sharpenSuggestion: (safe: string) =>
    req<SharpenSuggestion>(`/api/targets/${safe}/editor/sharpen-suggestion`),
  starSizeSuggestion: (safe: string) =>
    req<StarSizeSuggestion>(`/api/targets/${safe}/editor/star-size-suggestion`),
  // With no recipe/uid the bare proxy is measured (the stack's inherent noise —
  // used by the "Your data" chip + bulk apply). Passing the selected denoise op's
  // recipe+uid measures the *linear image entering that op* (any prior linear ops
  // applied), so the per-op "From your image" button reflects an upstream
  // gradient/colour op instead of ignoring it — mirroring levels/stretch/curve.
  denoiseSuggestion: (safe: string, runId: number, recipe?: Recipe, uid?: string) =>
    req<DenoiseSuggestion>(
      `/api/targets/${safe}/stack-runs/${runId}/editor/denoise-suggestion` +
      (recipe && uid
        ? `?recipe=${encodeRecipe(recipe)}&uid=${encodeURIComponent(uid)}`
        : ""),
    ),
  trimSuggestion: (safe: string, runId: number) =>
    req<TrimSuggestion>(`/api/targets/${safe}/stack-runs/${runId}/editor/trim-suggestion`),
  levelsSuggestion: (safe: string, runId: number, recipe: Recipe, uid: string) =>
    req<LevelsSuggestion>(
      `/api/targets/${safe}/stack-runs/${runId}/editor/levels-suggestion` +
      `?recipe=${encodeRecipe(recipe)}&uid=${encodeURIComponent(uid)}`,
    ),
  stretchSuggestion: (safe: string, runId: number, recipe: Recipe, uid: string) =>
    req<StretchSuggestion>(
      `/api/targets/${safe}/stack-runs/${runId}/editor/stretch-suggestion` +
      `?recipe=${encodeRecipe(recipe)}&uid=${encodeURIComponent(uid)}`,
    ),
  highlightSuggestion: (safe: string, runId: number, recipe: Recipe, uid: string) =>
    req<HighlightSuggestion>(
      `/api/targets/${safe}/stack-runs/${runId}/editor/highlight-suggestion` +
      `?recipe=${encodeRecipe(recipe)}&uid=${encodeURIComponent(uid)}`,
    ),
  curveSuggestion: (safe: string, runId: number, recipe: Recipe, uid: string) =>
    req<CurveSuggestion>(
      `/api/targets/${safe}/stack-runs/${runId}/editor/curve-suggestion` +
      `?recipe=${encodeRecipe(recipe)}&uid=${encodeURIComponent(uid)}`,
    ),
  getRecipe: (safe: string, runId: number) =>
    req<Recipe>(`/api/targets/${safe}/stack-runs/${runId}/editor/recipe`),
  previousRecipe: (safe: string, runId: number) =>
    req<PreviousRecipe>(
      `/api/targets/${safe}/stack-runs/${runId}/editor/previous-recipe`),
  autoNote: (safe: string, runId: number) =>
    req<{ note: string | null }>(
      `/api/targets/${safe}/stack-runs/${runId}/editor/auto-note`),
  putRecipe: (safe: string, runId: number, recipe: Recipe) =>
    req<Recipe>(`/api/targets/${safe}/stack-runs/${runId}/editor/recipe`, {
      method: "PUT", body: JSON.stringify(recipe),
    }),
  editPreviewUrl: (safe: string, runId: number, recipe: Recipe, bust = 0) =>
    `/api/targets/${safe}/stack-runs/${runId}/editor/preview?recipe=${encodeRecipe(recipe)}`
    + (bust ? `&v=${bust}` : ""),
  // "Check it at full size": whether one window of this picture can be rendered
  // at 1:1 for the current recipe, and the window itself. See LoupeInfo.
  loupeInfo: (safe: string, runId: number, recipe: Recipe) =>
    req<LoupeInfo>(
      `/api/targets/${safe}/stack-runs/${runId}/editor/loupe-info`
      + `?recipe=${encodeRecipe(recipe)}`),
  editLoupeUrl: (safe: string, runId: number, recipe: Recipe,
                 fx: number, fy: number, size: number) =>
    `/api/targets/${safe}/stack-runs/${runId}/editor/loupe?recipe=${encodeRecipe(recipe)}`
    + `&fx=${fx.toFixed(4)}&fy=${fy.toFixed(4)}&size=${Math.round(size)}`,
  /** The full-size window as a blob URL **and** the source rectangle it covers.
   *  Fetched rather than hung off an `<img src>` because the rectangle only
   *  exists as a response header — the same blob-URL shape the live preview
   *  already uses, so the caller must revoke the URL when it changes. */
  fetchLoupe: async (safe: string, runId: number, recipe: Recipe,
                     fx: number, fy: number, size: number,
                     signal?: AbortSignal): Promise<{
                       url: string; window: LoupeWindow | null }> => {
    const res = await fetch(
      api.editLoupeUrl(safe, runId, recipe, fx, fy, size), { signal });
    if (!res.ok) {
      let detail = `HTTP ${res.status}`;
      try { detail = (await res.json()).detail ?? detail; } catch { /* ignore */ }
      throw new Error(detail);
    }
    let win: LoupeWindow | null = null;
    try {
      const raw = res.headers.get("X-Loupe-Window");
      if (raw) win = JSON.parse(raw) as LoupeWindow;
    } catch { /* an unreadable header just means "don't say where" */ }
    return { url: URL.createObjectURL(await res.blob()), window: win };
  },
  editStarMaskUrl: (safe: string, runId: number, sizePx?: number,
                    recipe?: Recipe, uid?: string) => {
    const q = new URLSearchParams();
    if (sizePx) q.set("size_px", String(sizePx));
    // The star ops gate on the display-space image at their pipeline position, so
    // pass the recipe + selected star op uid to mask that (not the linear proxy).
    if (recipe) q.set("recipe", encodeRecipe(recipe));
    if (uid) q.set("uid", uid);
    const s = q.toString();
    return `/api/targets/${safe}/stack-runs/${runId}/editor/star-mask${s ? `?${s}` : ""}`;
  },
  editCoverageMapUrl: (safe: string, runId: number, recipe?: Recipe) => {
    // Pass the recipe so the backend applies its enabled geometry ops
    // (crop/rotate/resize) to the coverage map — then the overlay tracks the
    // reshaped preview instead of the raw full frame.
    const s = recipe ? `?recipe=${encodeRecipe(recipe)}` : "";
    return `/api/targets/${safe}/stack-runs/${runId}/editor/coverage-map${s}`;
  },
  getHistogram: (safe: string, runId: number, recipe: Recipe, signal?: AbortSignal) =>
    req<Histogram>(
      `/api/targets/${safe}/stack-runs/${runId}/editor/histogram?recipe=${encodeRecipe(recipe)}`,
      { signal }),
  // `autoCrop` overrides the library's "Auto-crop ragged border" setting for this
  // call only (the editor's per-run switch); omit it to use the saved setting.
  autoProcess: (safe: string, runId: number, autoCrop?: boolean) =>
    req<Recipe>(`/api/targets/${safe}/stack-runs/${runId}/editor/auto`,
      { method: "POST", ...autoCropBody(autoCrop) }),
  autoAnalysis: (safe: string, runId: number, autoCrop?: boolean) =>
    req<AutoAnalysis>(`/api/targets/${safe}/stack-runs/${runId}/editor/auto-analysis`,
      { method: "POST", ...autoCropBody(autoCrop) }),
  presetSuggestion: (safe: string, runId: number) =>
    req<PresetSuggestion>(
      `/api/targets/${safe}/stack-runs/${runId}/editor/preset-suggestion`,
      { method: "POST" }),
  exportPng: (safe: string, runId: number, recipe: Recipe) =>
    req<{ job_id: string }>(`/api/targets/${safe}/stack-runs/${runId}/editor/export-png`, {
      method: "POST", body: JSON.stringify({ recipe }),
    }),
  editPngUrl: (safe: string, runId: number, jobId: string) =>
    `/api/targets/${safe}/stack-runs/${runId}/editor/png/${jobId}`,
  exportShare: (safe: string, runId: number, recipe: Recipe, nameplate = false) =>
    req<{ job_id: string }>(`/api/targets/${safe}/stack-runs/${runId}/editor/share`, {
      method: "POST", body: JSON.stringify({ recipe, nameplate }),
    }),
  editShareUrl: (safe: string, runId: number, jobId: string) =>
    `/api/targets/${safe}/stack-runs/${runId}/editor/share/${jobId}`,
  /** Which standard paper sizes this picture can print *sharply*, largest first,
   *  plus one plain-language recommendation. Cheap (sized from the run's canvas,
   *  no render), so the menu can offer only sizes that will look good. */
  printSizes: (safe: string, runId: number) =>
    req<PrintSizes>(`/api/targets/${safe}/stack-runs/${runId}/editor/print-sizes`),
  /** Render a print-ready, DPI-tagged JPEG fitted to `sizeName` (omit it for the
   *  largest size this picture can fill sharply). */
  exportPrint: (safe: string, runId: number, recipe: Recipe,
                sizeName?: string, nameplate = false) =>
    req<{ job_id: string }>(`/api/targets/${safe}/stack-runs/${runId}/editor/print`, {
      method: "POST",
      body: JSON.stringify({ recipe, size_name: sizeName ?? null, nameplate }),
    }),
  editPrintUrl: (safe: string, runId: number, jobId: string) =>
    `/api/targets/${safe}/stack-runs/${runId}/editor/print/${jobId}`,
  /** Export the edited picture as a new image.
   *
   *  `tiffMode` is still sent — the endpoint has always taken it and a run's
   *  `options_json` may record it — but an editor export writes its TIFF with
   *  `already_display=True`, which returns before `mode` is read, so the value
   *  cannot change the file. It defaults to the same `"linear"` the sibling
   *  `exportSavedEdit` has always hardcoded, and the editor no longer asks. */
  exportRun: (safe: string, runId: number, recipe: Recipe, outputName: string,
              tiffMode = "linear") =>
    req<{ job_id: string }>(`/api/targets/${safe}/stack-runs/${runId}/editor/export`, {
      method: "POST",
      body: JSON.stringify({ recipe, output_name: outputName, tiff_mode: tiffMode }),
    }),
  /** Export the run's own *saved* recipe — "finish the edit I already saved",
   *  for someone who pressed Save in the editor and closed it. Omitting `recipe`
   *  makes the server use the stored one, so the browser never has to fetch and
   *  round-trip a recipe it isn't editing. */
  exportSavedEdit: (safe: string, runId: number, outputName: string) =>
    req<{ job_id: string }>(`/api/targets/${safe}/stack-runs/${runId}/editor/export`, {
      method: "POST",
      body: JSON.stringify({ output_name: outputName, tiff_mode: "linear" }),
    }),
  getAutoPreferences: () => req<AutoPreferences>("/api/editor/auto-preferences"),
  /** The profile scoped to a run's archetype (galaxy/nebula/cluster), so the
   * editor's "why Auto shifted" note reflects the target being edited. */
  getRunAutoPreferences: (safe: string, runId: number) =>
    req<AutoPreferences>(
      `/api/targets/${safe}/stack-runs/${runId}/editor/auto-preferences`),
  sendAutoFeedback: (cue: string, ctx?: { safe: string; runId: number }) =>
    req<AutoPreferences>("/api/editor/auto-preferences/feedback", {
      method: "POST",
      body: JSON.stringify(
        ctx ? { cue, safe: ctx.safe, run_id: ctx.runId } : { cue }),
    }),
  resetAutoPreferences: () =>
    req<AutoPreferences>("/api/editor/auto-preferences", { method: "DELETE" }),
  getDefaultRecipe: () => req<DefaultRecipe>("/api/editor/default-recipe"),
  putDefaultRecipe: (ops: OpInstance[]) =>
    req<DefaultRecipe>("/api/editor/default-recipe", {
      method: "PUT", body: JSON.stringify({ ops }),
    }),
  deleteDefaultRecipe: () =>
    req<DefaultRecipe>("/api/editor/default-recipe", { method: "DELETE" }),
  listPresets: () => req<{ builtin: Preset[]; user: Preset[] }>("/api/editor/presets"),
  createPreset: (label: string, ops: OpInstance[]) =>
    req<Preset>("/api/editor/presets", { method: "POST", body: JSON.stringify({ label, ops }) }),
  deletePreset: (id: string) => req(`/api/editor/presets/${id}`, { method: "DELETE" }),
  batchApply: (body: {
    items: { safe: string; run_id: number }[];
    recipe?: Recipe; preset_id?: string; output_name?: string;
  }) => req<{ job_id: string }>("/api/editor/batch", { method: "POST", body: JSON.stringify(body) }),

  // channel combine (LRGB / RGB from mono stacks)
  channelCombine: (safe: string, body: {
    items: { safe: string; run_id: number; channel: string }[];
    output_name?: string; weights?: Record<string, number>;
  }) => req<{ job_id: string }>(`/api/targets/${safe}/channel-combine`, {
    method: "POST", body: JSON.stringify(body),
  }),

  // access control (optional HTTP Basic auth)
  authStatus: () => req<{ enabled: boolean; username: string }>("/api/auth/status"),
  setAuthPassword: (body: { password: string; username?: string }) =>
    req<{ enabled: boolean; username: string }>("/api/auth/password", {
      method: "POST", body: JSON.stringify(body),
    }),

  // calibration masters (library-level dark/flat frames)
  listCalibrationMasters: () => req<CalibrationMaster[]>("/api/calibration/masters"),
  calibrationCoverage: () => req<CalibrationCoverage>("/api/calibration/coverage"),
  calibrationSuggestions: (safe: string) =>
    req<CalibrationSuggestions>(`/api/targets/${safe}/calibration-suggestions`),
  buildCalibrationMaster: (body: {
    kind: string; source_dir: string; name?: string; method?: string; sigma?: number;
  }) => req<{ job_id: string }>("/api/calibration/masters", {
    method: "POST", body: JSON.stringify(body),
  }),
  deleteCalibrationMaster: (id: number) =>
    req<{ deleted: number }>(`/api/calibration/masters/${id}`, { method: "DELETE" }),

  // Moon & Sun — lucky-imaging stacks of the Seestar's *_video captures
  listVideoCaptures: () => req<VideoList>("/api/videos"),
  gradeVideoCapture: (
    id: string,
    body: { file_name?: string } = {},
  ) => req<{ job_id: string }>(`/api/videos/${encodeURIComponent(id)}/grade`, {
    method: "POST", body: JSON.stringify(body),
  }),
  stackVideoCapture: (
    id: string,
    body: {
      keep_percent: number; file_name?: string; align?: boolean; crop?: boolean;
      // How hard to sharpen the finished picture (0 = not at all, the default).
      // Omitted by an older client, which then gets exactly the picture it
      // always got.
      sharpen?: number;
    },
  ) => req<{ job_id: string }>(`/api/videos/${encodeURIComponent(id)}/stack`, {
    method: "POST", body: JSON.stringify(body),
  }),
  // Trim the empty sky off a still that already exists. Not a job: it slices
  // the saved picture, so it returns the updated result straight away instead
  // of decoding the capture a second time.
  cropVideoStill: (id: string) =>
    req<VideoResult>(`/api/videos/${encodeURIComponent(id)}/crop`, { method: "POST" }),
  restoreVideoStill: (id: string) =>
    req<VideoResult>(`/api/videos/${encodeURIComponent(id)}/uncrop`, { method: "POST" }),
  // Change how sharp a finished still is, for the same reason and in the same
  // way as the crop: it re-renders from the copy kept beside the picture, so it
  // is instant, never compounds, and `amount: 0` puts the soft picture back.
  sharpenVideoStill: (id: string, amount: number) =>
    req<VideoResult>(`/api/videos/${encodeURIComponent(id)}/sharpen`, {
      method: "POST", body: JSON.stringify({ amount }),
    }),
};
