import { describe, expect, it } from "vitest";
import {
  SKYLINE_AZ_STEP, SKYLINE_BUCKETS, SKYLINE_MAX_ALT, SKYLINE_PRESETS,
  STRIP, altAtY, altitudeAtAz, arcContains, azAtX, bucketAzimuths, clampAltitude,
  compassLabel, describeSkyline, emptyHeights, groundPolygonPoints,
  heightsToProfile, nearestBucket, paintSpan, profileToHeights, xAtAz, yAtAlt,
  type HorizonPoint,
} from "./skyline";

describe("altitudeAtAz — the same answer the planner will get", () => {
  it("reports an open horizon for an empty profile", () => {
    expect(altitudeAtAz([], 0)).toBe(0);
    expect(altitudeAtAz([], 217)).toBe(0);
  });

  it("interpolates linearly between points", () => {
    const p: HorizonPoint[] = [[0, 0], [90, 30]];
    expect(altitudeAtAz(p, 0)).toBeCloseTo(0);
    expect(altitudeAtAz(p, 45)).toBeCloseTo(15);
    expect(altitudeAtAz(p, 90)).toBeCloseTo(30);
  });

  it("wraps through the northern seam like numpy's period=360", () => {
    // Values checked against the engine itself:
    //   np.interp(az, [0, 270], [10, 40], period=360)
    // — the same call HorizonProfile.altitude_at makes. If the strip and the
    // planner ever disagree about what a drawn skyline blocks, this is where
    // it shows up.
    const p: HorizonPoint[] = [[0, 10], [270, 40]];
    const expected: [number, number][] = [
      [0, 10], [10, 11.1111], [45, 15], [90, 20], [180, 30], [270, 40],
      [315, 25], [359, 10.3333],
    ];
    expected.forEach(([az, alt]) => expect(altitudeAtAz(p, az)).toBeCloseTo(alt, 3));
  });

  it("is constant for a single point, at every bearing", () => {
    expect(altitudeAtAz([[123, 17]], 0)).toBe(17);
    expect(altitudeAtAz([[123, 17]], 300)).toBe(17);
  });

  it("survives junk without throwing", () => {
    const junk = [[NaN, 3], ["x", 4], [10], [20, 30]] as unknown as HorizonPoint[];
    expect(altitudeAtAz(junk, 20)).toBe(30);
  });
});

describe("heightsToProfile — what actually gets saved", () => {
  it("a flattened skyline saves an EMPTY profile, not 24 zeros", () => {
    // An empty profile is exactly what an install that never touched this has,
    // so 'flatten it' must restore today's planner behaviour, not persist a
    // mask that happens to block nothing.
    expect(heightsToProfile(emptyHeights())).toEqual([]);
  });

  it("emits every bucket, zeros included, so gaps stay gaps", () => {
    const h = emptyHeights();
    h[nearestBucket(90)] = 20;
    const profile = heightsToProfile(h);
    expect(profile).toHaveLength(SKYLINE_BUCKETS);
    // The open sky either side of the one tree is stated, not left to be
    // bridged: dropping the zeros would make the backend interpolate a wall
    // from north all the way round to south.
    expect(altitudeAtAz(profile, 90)).toBeCloseTo(20);
    expect(altitudeAtAz(profile, 0)).toBeCloseTo(0);
    expect(altitudeAtAz(profile, 180)).toBeCloseTo(0);
  });

  it("emits whole degrees on the same azimuth grid, in order", () => {
    const profile = heightsToProfile(bucketAzimuths().map(() => 12.4));
    expect(profile.map((p) => p[0])).toEqual(bucketAzimuths());
    expect(profile.every((p) => Number.isInteger(p[1]))).toBe(true);
    expect(profile.every((p) => p[1] === 12)).toBe(true);
  });

  it("clamps anything a stray drag could produce into the valid range", () => {
    const profile = heightsToProfile([999, -999, ...emptyHeights().slice(2)]);
    expect(profile.every(([az, alt]) => az >= 0 && az < 360 && alt >= 0 && alt <= 90))
      .toBe(true);
    expect(profile[0][1]).toBe(SKYLINE_MAX_ALT);
    expect(profile[1][1]).toBe(0);
  });
});

describe("profileToHeights — showing a saved profile back", () => {
  it("round-trips a skyline drawn on the bucket grid", () => {
    const drawn = bucketAzimuths().map((az) => (az < 180 ? 20 : 5));
    const back = profileToHeights(heightsToProfile(drawn));
    back.forEach((h, i) => expect(h).toBeCloseTo(drawn[i]));
  });

  it("samples a hand-typed profile onto the grid without inventing height", () => {
    const typed: HorizonPoint[] = [[0, 0], [180, 36]];
    const h = profileToHeights(typed);
    expect(h).toHaveLength(SKYLINE_BUCKETS);
    expect(h[nearestBucket(180)]).toBeCloseTo(36);
    expect(Math.max(...h)).toBeLessThanOrEqual(36);
  });

  it("an empty profile draws a flat skyline", () => {
    expect(profileToHeights([])).toEqual(emptyHeights());
  });
});

describe("paintSpan — one gesture draws a continuous skyline", () => {
  it("fills the buckets a fast sweep skipped over", () => {
    const painted = paintSpan(emptyHeights(), 0, 30, 90, 30);
    for (let az = 0; az <= 90; az += SKYLINE_AZ_STEP) {
      expect(painted[nearestBucket(az)]).toBeCloseTo(30);
    }
    // …and nothing beyond the gesture.
    expect(painted[nearestBucket(180)]).toBe(0);
  });

  it("ramps between the two ends of the segment", () => {
    const painted = paintSpan(emptyHeights(), 0, 0, 60, 30);
    expect(painted[nearestBucket(0)]).toBeCloseTo(0);
    expect(painted[nearestBucket(30)]).toBeCloseTo(15);
    expect(painted[nearestBucket(60)]).toBeCloseTo(30);
  });

  it("takes the short way round the compass, not the long way", () => {
    // 345° → 15° is 30° of sky through north, not 330° the other way.
    const painted = paintSpan(emptyHeights(), 345, 20, 15, 20);
    expect(painted[nearestBucket(0)]).toBeCloseTo(20);
    expect(painted[nearestBucket(180)]).toBe(0);
    expect(painted.filter((h) => h > 0)).toHaveLength(3);
  });

  it("a tap paints exactly one bucket", () => {
    const painted = paintSpan(emptyHeights(), 92, 25, 92, 25);
    expect(painted.filter((h) => h > 0)).toHaveLength(1);
    expect(painted[nearestBucket(90)]).toBeCloseTo(25);
  });

  it("never mutates the array it was given", () => {
    const before = emptyHeights();
    paintSpan(before, 0, 40, 180, 40);
    expect(before).toEqual(emptyHeights());
  });

  it("a drag, then dragging it all back down, round-trips to an empty profile", () => {
    const drawn = paintSpan(emptyHeights(), 0, 30, 120, 30);
    expect(heightsToProfile(drawn)).not.toEqual([]);
    // Two sweeps, because one span always takes the short way round — the same
    // two gestures a user would make to flatten the whole compass by hand.
    const half = paintSpan(drawn, 0, 0, 180, 0);
    expect(heightsToProfile(paintSpan(half, 180, 0, 360, 0))).toEqual([]);
  });
});

describe("strip geometry", () => {
  it("x and azimuth are inverses across the strip", () => {
    [0, 45, 180, 359].forEach((az) => expect(azAtX(xAtAz(az))).toBeCloseTo(az, 3));
  });

  it("y and altitude are inverses, and clamp outside the plot", () => {
    [0, 15, 60].forEach((alt) => expect(altAtY(yAtAlt(alt))).toBeCloseTo(alt, 3));
    expect(altAtY(STRIP.yBase + 40)).toBe(0);
    expect(altAtY(STRIP.yTop - 40)).toBe(SKYLINE_MAX_ALT);
  });

  it("draws a flat skyline flat, and a raised one higher up the strip", () => {
    const flat = groundPolygonPoints(emptyHeights());
    expect(flat).toContain(`${STRIP.yBase.toFixed(1)}`);
    const raised = groundPolygonPoints(bucketAzimuths().map(() => SKYLINE_MAX_ALT));
    expect(raised).toContain(`${STRIP.yTop.toFixed(1)}`);
    expect(raised).not.toBe(flat);
  });

  it("closes the polygon across the northern seam at the same height", () => {
    const h = bucketAzimuths().map((az) => (az === 0 ? 40 : 0));
    const pts = groundPolygonPoints(h).split(" ");
    // Both ends of the strip are bucket 0, so the drawn shape doesn't jump.
    expect(pts[1].split(",")[1]).toBe(pts[pts.length - 2].split(",")[1]);
  });
});

describe("presets and copy", () => {
  it("every preset produces a full, in-range set of buckets", () => {
    SKYLINE_PRESETS.forEach((p) => {
      const h = p.heights();
      expect(h).toHaveLength(SKYLINE_BUCKETS);
      expect(h.every((v) => v === clampAltitude(v))).toBe(true);
    });
  });

  it("'open sky' is the same as no profile at all", () => {
    const open = SKYLINE_PRESETS.find((p) => p.id === "open")!;
    expect(heightsToProfile(open.heights())).toEqual([]);
  });

  it("the directional presets actually block that direction most", () => {
    const south = SKYLINE_PRESETS.find((p) => p.id === "house-south")!.heights();
    expect(south[nearestBucket(180)]).toBeGreaterThan(south[nearestBucket(0)]);
    const north = SKYLINE_PRESETS.find((p) => p.id === "trees-north")!.heights();
    expect(north[nearestBucket(0)]).toBeGreaterThan(north[nearestBucket(180)]);
  });

  it("describes an open horizon and a blocked one in plain language", () => {
    expect(describeSkyline(emptyHeights())).toMatch(/open horizon/i);
    const h = emptyHeights();
    h[nearestBucket(180)] = 30;
    const said = describeSkyline(h);
    expect(said).toContain("30°");
    expect(said).toContain("S");
  });

  it("names bearings the way a person would", () => {
    expect(compassLabel(0)).toBe("N");
    expect(compassLabel(90)).toBe("E");
    expect(compassLabel(181)).toBe("S");
    expect(compassLabel(315)).toBe("NW");
  });

  it("arcContains handles an arc that crosses north", () => {
    expect(arcContains(0, 315, 45)).toBe(true);
    expect(arcContains(340, 315, 45)).toBe(true);
    expect(arcContains(180, 315, 45)).toBe(false);
  });
});
