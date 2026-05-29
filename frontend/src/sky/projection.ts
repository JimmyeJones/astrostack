/**
 * Celestial-sphere math for the 3D sky viewer.
 *
 * Pure functions (no WebGL) so they can be unit-tested. The viewer places the
 * camera at the origin looking outward at a sphere of radius `R`; stars and
 * stacked-image planes live on that sphere at their RA/Dec.
 *
 * Convention (right-handed, Y-up):
 *   x = cos(dec)·cos(ra),  y = sin(dec),  z = cos(dec)·sin(ra)
 * so RA=0,Dec=0 → +X, the north celestial pole (Dec=+90) → +Y.
 */
import * as THREE from "three";

const DEG = Math.PI / 180;

export interface SkyImage {
  safe: string;
  name: string;
  ra_deg: number;
  dec_deg: number;
  width_deg: number;
  height_deg: number;
  rotation_deg: number;
  preview_url: string;
  timestamp_utc: string | null;
  run_id: number;
}

export interface SkyStar {
  name: string;
  ra_deg: number;
  dec_deg: number;
  mag: number;
}

/** Unit (×radius) direction vector for a celestial coordinate. */
export function raDecToVector(raDeg: number, decDeg: number, radius = 1): THREE.Vector3 {
  const ra = raDeg * DEG;
  const dec = decDeg * DEG;
  const cd = Math.cos(dec);
  return new THREE.Vector3(
    radius * cd * Math.cos(ra),
    radius * Math.sin(dec),
    radius * cd * Math.sin(ra),
  );
}

/** Tangent unit vector pointing toward celestial north at (ra, dec). */
export function northTangent(raDeg: number, decDeg: number): THREE.Vector3 {
  const ra = raDeg * DEG;
  const dec = decDeg * DEG;
  const sd = Math.sin(dec);
  return new THREE.Vector3(
    -sd * Math.cos(ra),
    Math.cos(dec),
    -sd * Math.sin(ra),
  ).normalize();
}

/** Tangent unit vector pointing toward increasing RA (east) at (ra, dec). */
export function eastTangent(raDeg: number): THREE.Vector3 {
  const ra = raDeg * DEG;
  return new THREE.Vector3(-Math.sin(ra), 0, Math.cos(ra)).normalize();
}

/**
 * Orientation for an image plane (local XY, normal +Z) centred at (ra, dec):
 * tangent to the sphere with +Y along celestial north and +X along east, then
 * rotated by the field's position angle about the surface normal.
 */
export function orientationFor(raDeg: number, decDeg: number, rotationDeg = 0): THREE.Quaternion {
  const east = eastTangent(raDeg);
  const north = northTangent(raDeg, decDeg);
  // Surface normal pointing inward (toward the camera at the centre). Using the
  // inward normal makes (east, north, inward) a right-handed basis — a proper
  // rotation — and orients the image to face the viewer.
  const inward = raDecToVector(raDeg, decDeg, 1).normalize().negate();
  const basis = new THREE.Matrix4().makeBasis(east, north, inward);
  const q = new THREE.Quaternion().setFromRotationMatrix(basis);
  if (rotationDeg) {
    q.multiply(new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(0, 0, 1), rotationDeg * DEG));
  }
  return q;
}

/** Angular size in degrees → world units at the given sphere radius. */
export function angularToWorld(deg: number, radius: number): number {
  return radius * deg * DEG;
}

/** Point size (world-ish units) for a star of the given visual magnitude. */
export function starSize(mag: number, base = 1): number {
  // Brighter (smaller mag) → larger. Clamp so very bright stars don't explode.
  return base * Math.max(0.35, Math.min(2.4, 1.9 - 0.32 * mag));
}

/**
 * Order images oldest-first so the caller can assign increasing renderOrder
 * (newest drawn last → on top of overlapping older images). Stable.
 */
export function sortOldestFirst(images: SkyImage[]): SkyImage[] {
  return images
    .map((im, i) => [im, i] as const)
    .sort(([a, ai], [b, bi]) => {
      const ta = a.timestamp_utc ?? "";
      const tb = b.timestamp_utc ?? "";
      if (ta < tb) return -1;
      if (ta > tb) return 1;
      return ai - bi;
    })
    .map(([im]) => im);
}
