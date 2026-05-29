import { describe, expect, it } from "vitest";
import * as THREE from "three";
import {
  angularToWorld,
  northTangent,
  orientationFor,
  raDecToVector,
  sortOldestFirst,
  starSize,
  type SkyImage,
} from "./projection";

const close = (a: number, b: number, eps = 1e-6) => Math.abs(a - b) < eps;

describe("raDecToVector", () => {
  it("maps RA=0,Dec=0 to +X", () => {
    const v = raDecToVector(0, 0, 5);
    expect(close(v.x, 5)).toBe(true);
    expect(close(v.y, 0)).toBe(true);
    expect(close(v.z, 0)).toBe(true);
  });

  it("maps the north celestial pole to +Y", () => {
    const v = raDecToVector(123, 90, 1);
    expect(close(v.y, 1)).toBe(true);
    expect(close(Math.hypot(v.x, v.z), 0, 1e-6)).toBe(true);
  });

  it("stays on the sphere of the given radius", () => {
    const v = raDecToVector(57, -33, 7);
    expect(close(v.length(), 7, 1e-5)).toBe(true);
  });
});

describe("orientationFor", () => {
  it("aligns local +Y with celestial north", () => {
    const q = orientationFor(40, 20, 0);
    const up = new THREE.Vector3(0, 1, 0).applyQuaternion(q);
    const n = northTangent(40, 20);
    expect(close(up.dot(n), 1, 1e-6)).toBe(true);
  });

  it("position angle rotates the plane about its normal", () => {
    const q0 = orientationFor(40, 20, 0);
    const q90 = orientationFor(40, 20, 90);
    // After a 90° PA, the old up direction should be ~orthogonal to the new up.
    const up0 = new THREE.Vector3(0, 1, 0).applyQuaternion(q0);
    const up90 = new THREE.Vector3(0, 1, 0).applyQuaternion(q90);
    expect(Math.abs(up0.dot(up90)) < 1e-6).toBe(true);
  });
});

describe("angularToWorld + starSize", () => {
  it("scales angular degrees by radius", () => {
    expect(close(angularToWorld(180, 1), Math.PI)).toBe(true);
    expect(close(angularToWorld(90, 2), Math.PI)).toBe(true);
  });

  it("makes brighter stars bigger", () => {
    expect(starSize(-1)).toBeGreaterThan(starSize(3));
  });
});

describe("sortOldestFirst", () => {
  const mk = (id: number, ts: string | null): SkyImage => ({
    safe: `t${id}`, name: `T${id}`, ra_deg: 0, dec_deg: 0,
    width_deg: 1, height_deg: 1, rotation_deg: 0,
    preview_url: "", timestamp_utc: ts, run_id: id,
  });

  it("orders oldest→newest so newest paints last (on top)", () => {
    const out = sortOldestFirst([
      mk(1, "2026-05-03T00:00:00Z"),
      mk(2, "2026-05-01T00:00:00Z"),
      mk(3, "2026-05-02T00:00:00Z"),
    ]);
    expect(out.map((i) => i.run_id)).toEqual([2, 3, 1]);
  });

  it("is stable for equal/missing timestamps", () => {
    const out = sortOldestFirst([mk(1, null), mk(2, null)]);
    expect(out.map((i) => i.run_id)).toEqual([1, 2]);
  });
});
