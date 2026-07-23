import type { FieldObject } from "../api/client";

// "What else is in this picture?" — turn the catalog objects the annotations
// endpoint already projects into the field into a short, plain-language list a
// beginner can actually read, instead of only labels drawn on the image plus a
// bare "Found N catalog objects" count. A Seestar's ~1.3°×0.7° field almost
// always catches more than the one target the user aimed at (shoot M42 and the
// Running Man rides along above it), and "what are those other smudges?" is
// exactly the question that makes astrophotography exciting to a newcomer.
//
// Pure and presentation-only: it reuses the exact `objects` array + FITS grid
// the Identify/Scale overlay already fetches, so there's no new engine math and
// no backend change. Positions are named relative to the *frame*, not to the
// primary target, so it needs no fragile primary-object identification and can
// never mislabel an object it can't disambiguate.

/** One catalog object described in plain language for the list. */
export interface FramedObjectDescription {
  catalogId: string;
  /** "Orion Nebula (M42)", or a bare "NGC 891" when there's no common name. */
  label: string;
  /** Friendly type clause, e.g. "a nebula" / "an open cluster"; "" if unknown. */
  typePhrase: string;
  /** Where it sits in the frame, e.g. "near the centre" / "toward the top-left". */
  positionPhrase: string;
}

// Within this fraction of the way out to a corner an object reads as "near the
// centre" rather than being given a direction (the main target usually sits
// here). Beyond it, an axis earns a directional word only once the object is
// this far off that axis, so a near-axis object isn't called "top-left".
const CENTRE_RADIUS = 0.25;
const AXIS_THRESHOLD = 0.33;

function objectLabel(o: FieldObject): string {
  const name = o.name.trim();
  const id = o.catalog_id.trim();
  if (name && id && name.toLowerCase() !== id.toLowerCase()) return `${name} (${id})`;
  return name || id;
}

function typePhrase(type: string): string {
  const t = type.trim().toLowerCase();
  if (!t) return "";
  const article = /^[aeiou]/.test(t) ? "an" : "a";
  return `${article} ${t}`;
}

function positionPhrase(nx: number, ny: number, r: number): string {
  // nx: -1 (left) … +1 (right); ny: -1 (top) … +1 (bottom), since image y runs
  // downward.
  if (r < CENTRE_RADIUS) return "near the centre";
  const vert = ny < -AXIS_THRESHOLD ? "top" : ny > AXIS_THRESHOLD ? "bottom" : "";
  const horiz = nx < -AXIS_THRESHOLD ? "left" : nx > AXIS_THRESHOLD ? "right" : "";
  if (vert && horiz) return `toward the ${vert}-${horiz}`;
  if (vert) return `toward the ${vert}`;
  if (horiz) return `toward the ${horiz}`;
  // Off-centre but diagonally, with neither axis past its threshold — name the
  // stronger axis so a description never falls through to empty.
  return Math.abs(ny) >= Math.abs(nx)
    ? `toward the ${ny < 0 ? "top" : "bottom"}`
    : `toward the ${nx < 0 ? "left" : "right"}`;
}

/**
 * Describe the catalog objects inside a run's field in plain language, nearest
 * the centre first, capped at `limit`. Returns `[]` for no objects or a
 * degenerate (zero-size) grid — the caller then simply shows nothing.
 */
export function describeFieldObjects(
  objects: FieldObject[],
  width: number,
  height: number,
  limit = 5,
): FramedObjectDescription[] {
  if (!objects.length || width <= 0 || height <= 0) return [];
  const cx = width / 2;
  const cy = height / 2;
  return objects
    .map((o) => {
      const nx = (o.x_px - cx) / (width / 2);
      const ny = (o.y_px - cy) / (height / 2);
      return { o, nx, ny, r: Math.hypot(nx, ny) };
    })
    .sort((a, b) => a.r - b.r)
    .slice(0, limit)
    .map(({ o, nx, ny, r }) => ({
      catalogId: o.catalog_id,
      label: objectLabel(o),
      typePhrase: typePhrase(o.type),
      positionPhrase: positionPhrase(nx, ny, r),
    }));
}
