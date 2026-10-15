/**
 * "Leaving out bad frames" — slice 3 of the owner-approved Settings redesign
 * (`docs/design/settings-redesign.md`, section 3).
 *
 * One "How picky?" control over two `Settings` fields — *Keep all* is
 * `auto_grade_frames` off; *Gentle / Balanced / Strict* switch it on at
 * `auto_grade_sensitivity` conservative / balanced / aggressive — plus an
 * illustration of which kinds of frame each choice leaves out, and the trails
 * switch (`keep_streaked_frames`). This module is the data and the arithmetic,
 * free of React so each answer is pinned as a value; `FramePicky.tsx` draws it.
 *
 * **Every sentence here was checked against the grader it describes**
 * (`seestack/qc/grading.py`), and the mockup's did not survive it. The mockup
 * says *Gentle* leaves out "only clouded-out frames" and *Strict* "also frames
 * that are only slightly soft". Neither is how grading works: every level
 * judges **every** measure (sharpness, star shape, sky brightness, star count,
 * star brightness) — the levels only move how far from the rest of the night
 * a frame must be (`SENSITIVITY_THRESHOLDS`, a robust z of 5.0 / 3.5 / 2.5) —
 * and no level ever leaves a frame out for a small difference, because each
 * measure also has a fixed "meaningfully worse" floor (≥25 % softer, ≥30 %
 * fewer stars, …) that the level does not move. So the notes speak of *how
 * bad*, not of *which kind*, and the illustration's "a bit soft" tile is kept
 * at every level, Strict included.
 *
 * Two more facts the section states because they are true of the code:
 * grading never leaves out more than a quarter of a target's frames
 * (`MAX_REJECT_FRACTION`), and a frame you accepted or rejected yourself is
 * never touched (`user_override`). And one it states because a beginner would
 * otherwise be misled: frames arriving on their own are graded only while the
 * **Check** step (`auto_qc`) runs (`_pipeline_body` gates the hook on it),
 * though checking a target yourself or **Process target** still grades it.
 */

export type SettingsForm = Record<string, unknown>;
export type SettingsPatch = Record<string, unknown>;

export type GradeSensitivity = "conservative" | "balanced" | "aggressive";
export type PickyLevelId = "off" | "gentle" | "balanced" | "strict";

export interface PickyLevel {
  id: PickyLevelId;
  label: string;
  /** What `auto_grade_sensitivity` this level stores; null for Keep all. */
  sensitivity: GradeSensitivity | null;
  /** One plain sentence on what this choice does. */
  note: string;
}

export const PICKY_LEVELS: PickyLevel[] = [
  {
    id: "off",
    label: "Keep all",
    sensitivity: null,
    note: "No frame is left out for cloud, shake or soft focus.",
  },
  {
    id: "gentle",
    label: "Gentle",
    sensitivity: "conservative",
    note: "Only frames far worse than the rest of the night — thick cloud, a bad shake — are left out.",
  },
  {
    id: "balanced",
    label: "Balanced",
    sensitivity: "balanced",
    note: "Frames clearly worse than the rest of the night are left out (recommended).",
  },
  {
    id: "strict",
    label: "Strict",
    sensitivity: "aggressive",
    note: "Borderline frames are left out too — best when you have plenty of frames.",
  },
];

/** The labels these controls had before the redesign, for the `Was:` line. */
export const PICKY_WAS =
  "“Auto-grade frames after QC”, “Sensitivity”, “Keep frames with satellite/plane streaks”";

/**
 * Which level the two fields add up to. Grading off is *Keep all* whatever
 * sensitivity is stored (it is kept, unused, for when grading is switched
 * back on); null only for a stored sensitivity this page doesn't know, so no
 * button is drawn as picked rather than a wrong one.
 */
export function pickyLevel(form: SettingsForm): PickyLevelId | null {
  if (!form.auto_grade_frames) return "off";
  const sens = (form.auto_grade_sensitivity as string | undefined) ?? "balanced";
  return PICKY_LEVELS.find((l) => l.sensitivity === sens)?.id ?? null;
}

/**
 * What picking a level writes. *Keep all* only switches grading off and
 * leaves the stored sensitivity alone, so going back to the level he had
 * is one click and nothing he set is quietly reset.
 */
export function pickyPatch(id: PickyLevelId): SettingsPatch {
  const lvl = PICKY_LEVELS.find((l) => l.id === id);
  if (!lvl) return {};
  if (lvl.sensitivity === null) return { auto_grade_frames: false };
  return { auto_grade_frames: true, auto_grade_sensitivity: lvl.sensitivity };
}

/** Where a level sits, gentlest first — Keep all is 0. */
function rank(id: PickyLevelId): number {
  return PICKY_LEVELS.findIndex((l) => l.id === id);
}

export type FrameKind =
  | "sharp" | "cloud" | "shaken" | "haze" | "soft" | "borderline" | "bitsoft" | "trail";

export interface FrameTile {
  kind: FrameKind;
  /** The caption under the tile. */
  what: string;
  /**
   * The gentlest level that leaves this kind out, or null if no level does.
   * Trails are decided by the trails switch instead, and carry null here.
   */
  leftOutFrom: PickyLevelId | null;
}

/**
 * The illustration's twelve frames. Typical, not exact — the real cut-off is
 * measured against the rest of each target's own night, which is why the
 * section labels it *Illustration*. The ordering of the kinds is the grader's:
 * a frame further from the night's typical one is left out at a gentler level.
 */
export const FRAME_TILES: FrameTile[] = [
  { kind: "sharp", what: "Sharp", leftOutFrom: null },
  { kind: "sharp", what: "Sharp", leftOutFrom: null },
  { kind: "cloud", what: "Thick cloud", leftOutFrom: "gentle" },
  { kind: "sharp", what: "Sharp", leftOutFrom: null },
  { kind: "soft", what: "Soft focus", leftOutFrom: "balanced" },
  { kind: "bitsoft", what: "A bit soft", leftOutFrom: null },
  { kind: "trail", what: "Satellite", leftOutFrom: null },
  { kind: "shaken", what: "Bad shake", leftOutFrom: "gentle" },
  { kind: "haze", what: "Thin haze", leftOutFrom: "balanced" },
  { kind: "sharp", what: "Sharp", leftOutFrom: null },
  { kind: "borderline", what: "Borderline", leftOutFrom: "strict" },
  { kind: "sharp", what: "Sharp", leftOutFrom: null },
];

/** Is this tile left out under the current choice? */
export function tileLeftOut(
  tile: FrameTile, level: PickyLevelId | null, keepTrails: boolean,
): boolean {
  if (tile.kind === "trail") return !keepTrails;
  if (tile.leftOutFrom === null || level === null) return false;
  return rank(level) >= rank(tile.leftOutFrom);
}

export function trailNote(keepTrails: boolean): string {
  return keepTrails
    ? "On: a frame with a trail is kept, and the stack's outlier removal usually wipes the trail out — most reliably once a dozen or so frames cover that patch of sky."
    : "Off (recommended): a frame with a satellite or plane trail is left out of the stack.";
}

/**
 * The one condition under which the picky choice does not act on frames that
 * arrive by themselves: grading runs on the Check step's measurements, and the
 * unattended pipeline only grades while Check is on. Null when nothing needs
 * saying.
 */
export function pickyWaitingNote(form: SettingsForm): string | null {
  if (!form.auto_grade_frames || form.auto_qc) return null;
  return "Check (step 3) is off, so frames that arrive on their own aren't sorted out — "
    + "only when you check a target yourself or press Process target.";
}
