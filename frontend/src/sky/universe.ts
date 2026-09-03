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
  /** The catalog's plain-language "what am I looking at?" one-liner. Optional so
   *  an older backend that doesn't send it simply shows no sentence. */
  blurb?: string;
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

/** One *object* on the map, and every target of yours that is that object. */
export interface PlacedGroup {
  /** Stable key for the group — the catalog id when there is one. */
  key: string;
  /** The one drawn: the picture the reader should see for this object. */
  primary: PlacedPicture;
  /** Your other targets of the same object, in the order they arrived. */
  others: PlacedPicture[];
}

/** The catalog identity two targets have to share to be one thing on the map.
 *  Empty when the target has no catalog id — see {@link groupByObject}. */
function objectKey(p: PlacedPicture): string {
  return (p.object.object_id ?? "").trim().toLowerCase();
}

/**
 * Collapse targets that are the *same catalogue object* into one node.
 *
 * Every target is placed at its object's real position, which is right — all of
 * your pictures of M 31 belong where M 31 actually is. But two targets of one
 * object (`M 31` and `M 31 (mosaic)`, which is what the Seestar's own folder
 * convention produces for anyone who shoots a mosaic; or the same object
 * re-imaged under a second folder name) then land on **exactly** the same point,
 * drawing two coincident pictures and two overlapping labels with nothing to
 * tell the reader there are two.
 *
 * Grouping is the honest fix. Nudging one aside would be the wrong one on a map
 * whose whole promise is "placed where they really are".
 *
 * The **primary** — the one actually drawn — is the first entry that has a
 * picture, because a bare marker drawn over a finished picture would hide the
 * better thing. Failing that it is simply the first, so a group is never empty.
 * Input order is preserved throughout, so the near→far ordering the rest of this
 * module relies on survives.
 *
 * A target with **no** catalog id never groups: it gets its own node keyed by
 * its target name. Folding those together on an empty id would pile every
 * unidentified target onto one point, which is this bug with the sign flipped.
 */
export function groupByObject(placed: PlacedPicture[]): PlacedGroup[] {
  const order: string[] = [];
  const byKey = new Map<string, PlacedPicture[]>();
  for (const p of placed) {
    const id = objectKey(p);
    const key = id ? `id:${id}` : `safe:${p.object.safe}`;
    const bucket = byKey.get(key);
    if (bucket) bucket.push(p);
    else { byKey.set(key, [p]); order.push(key); }
  }
  return order.map((key) => {
    const members = byKey.get(key) as PlacedPicture[];
    const lead = members.findIndex((m) => m.image !== null);
    const at = lead >= 0 ? lead : 0;
    return {
      key,
      primary: members[at],
      others: members.filter((_, i) => i !== at),
    };
  });
}

/**
 * Your other targets of the same object as `object` — what the read-out lists
 * so a reader can tell there is more than one picture behind that node.
 *
 * Matches on the catalog id, and returns `[]` when the object has none (see
 * {@link groupByObject}: no id means no claim of sameness).
 */
export function sameObjectTargets(
  objects: UniverseObject[], object: UniverseObject,
): UniverseObject[] {
  const id = (object.object_id ?? "").trim().toLowerCase();
  if (!id) return [];
  return objects.filter(
    (o) => o.safe !== object.safe && (o.object_id ?? "").trim().toLowerCase() === id,
  );
}

/** How many distinct objects the map actually draws — which is what the "N
 *  placed" badge means to someone looking at it, and stops disagreeing with the
 *  node count the moment two of your targets are one object. */
export function distinctObjectCount(objects: UniverseObject[]): number {
  const keys = new Set<string>();
  for (const o of objects) {
    const id = (o.object_id ?? "").trim().toLowerCase();
    keys.add(id ? `id:${id}` : `safe:${o.safe}`);
  }
  return keys.size;
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

/** How far *outside* an object the camera stops when it flies to it. The
 *  pictures are {@link PICTURE_SIZE}-sized in world units, so this is roughly
 *  "close enough to fill the view, far enough to still see the ring behind it".
 */
export const FLY_MARGIN = 14;
/** The camera's own orbit limits (mirrored from OrbitControls' min/maxDistance),
 *  so a fly-to can never park the camera somewhere the controls would then snap
 *  it out of on the next frame. */
export const FLY_MIN_DISTANCE = 20;
export const FLY_MAX_DISTANCE = 360;

/**
 * Where the camera should end up to *look at* an object — "fly to it".
 *
 * Clicking a picture selects it, but on a five-decade scale the nearest objects
 * are a long way in from the outer ring, so without this the reader has to orbit
 * and dolly to actually look at the thing they clicked.
 *
 * The camera stays on the object's **own radial line**, just outside it. That is
 * what lets OrbitControls keep its target at the origin (moving the target makes
 * the orbit confusing, and the origin is "you are here" — the point every
 * distance on this map is measured from): with the object *between* the camera
 * and the origin, looking at the origin puts it dead centre anyway.
 *
 * Returns `null` for a degenerate position (an object on top of the origin,
 * which the inner radius makes impossible, or a non-finite coordinate) — the
 * caller then simply doesn't move, rather than flying the camera into NaN.
 */
export function flyToCameraPosition(
  target: { x: number; y: number; z: number },
  opts: { margin?: number; min?: number; max?: number } = {},
): { x: number; y: number; z: number } | null {
  const { x, y, z } = target;
  if (![x, y, z].every((v) => Number.isFinite(v))) return null;
  const len = Math.hypot(x, y, z);
  if (!(len > 1e-6)) return null;
  const margin = opts.margin ?? FLY_MARGIN;
  const min = opts.min ?? FLY_MIN_DISTANCE;
  const max = opts.max ?? FLY_MAX_DISTANCE;
  const dist = Math.min(max, Math.max(min, len + margin));
  return { x: (x / len) * dist, y: (y / len) * dist, z: (z / len) * dist };
}
