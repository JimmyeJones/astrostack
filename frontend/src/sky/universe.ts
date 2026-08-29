/**
 * "Your universe" — placing the owner's captured objects in true 3D.
 *
 * The depth decision itself lives in the engine (`seestack/universemap.py`),
 * which returns each object's `depth` as a 0..1 log-scaled radial coordinate.
 * Everything here is the *rendering* half: turning that coordinate into a world
 * radius, joining each object to the picture the owner actually took of it, and
 * writing the two sentences the scene needs so it can't be mistaken for a
 * measurement. All pure, so it can be unit-tested without WebGL.
 */
import type { SkyImage } from "./projection";

export interface UniverseObject {
  safe: string;
  name: string;
  object_id: string;
  object_name: string;
  type: string;
  ra_deg: number;
  dec_deg: number;
  distance_ly: number;
  distance_text: string;
  years_text: string;
  depth: number;
}

export interface UniverseShell {
  distance_ly: number;
  depth: number;
  label: string;
}

export interface UniverseUnplaced {
  safe: string;
  name: string;
  reason: string;
}

export interface UniverseData {
  objects: UniverseObject[];
  shells: UniverseShell[];
  unplaced: UniverseUnplaced[];
  near_ly: number;
  far_ly: number;
  provenance: string;
}

/**
 * World radius for a 0..1 depth. The inner radius is not zero: the camera
 * orbits the origin (where you are), and an object sitting on top of it would
 * be unreachable and unreadable.
 */
export const INNER_RADIUS = 12;
export const OUTER_RADIUS = 100;

export function radiusForDepth(depth: number): number {
  const d = Math.min(1, Math.max(0, Number.isFinite(depth) ? depth : 0));
  return INNER_RADIUS + d * (OUTER_RADIUS - INNER_RADIUS);
}

/** One object with the picture the owner took of it, when there is one. */
export interface PlacedPicture {
  object: UniverseObject;
  image: SkyImage | null;
}

/**
 * Join each placed object to its newest picture (from `/api/sky`) by target.
 *
 * A target can be placed with no picture — it has a solved position and a
 * catalog distance but no finished stack yet — and that is worth drawing as a
 * bare marker rather than dropping, so "I have been here" still shows.
 */
export function withPictures(
  objects: UniverseObject[], images: SkyImage[],
): PlacedPicture[] {
  const bySafe = new Map<string, SkyImage>();
  for (const im of images) bySafe.set(im.safe, im);
  return objects.map((object) => ({ object, image: bySafe.get(object.safe) ?? null }));
}

/**
 * The scale caption: what the map's radial axis means, in one sentence.
 *
 * Says "log" in plain language — *equal steps are equal multiples* — because a
 * reader who assumes the axis is linear will badly misread the spacing, and the
 * whole feature turns on that spacing being understood.
 */
export function scaleCaption(shells: UniverseShell[]): string {
  if (shells.length < 2) return "";
  const first = shells[0].label;
  const last = shells[shells.length - 1].label;
  return `Rings mark ${first} out to ${last}. Each ring is a big step further `
    + "than the one inside it, so near and far both stay readable.";
}

/**
 * The one-line summary above the object list.
 *
 * Names the near/far extremes because the *ratio* between them is the fact
 * worth carrying away ("the furthest thing I've photographed is a thousand
 * times further than the nearest").
 */
export function spanSummary(objects: UniverseObject[]): string {
  if (objects.length === 0) return "";
  const near = objects[0];
  const far = objects[objects.length - 1];
  if (objects.length === 1 || near.distance_ly === far.distance_ly) {
    return `${near.name} sits ${near.distance_text} away.`;
  }
  return `From ${near.name} at ${near.distance_text} out to ${far.name} `
    + `at ${far.distance_text}.`;
}
