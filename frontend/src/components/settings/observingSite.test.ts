import { describe, expect, it } from "vitest";
import type { ObservingSite } from "../../api/client";
import {
  HORIZON, READ_FROM_PHOTOS_PATCH, altitudeBandPath, altitudeHint, currentLocationLine,
  formatLatLon, hasTypedLocation, memoryBar, memoryHeadline, showTypedBoxes, siteMode,
} from "./observingSite";

const PHOTOS: ObservingSite = {
  location_source: "fits", location_reason: null,
  observer: { lat_deg: 48, lon_deg: 11, elevation_m: 0 },
  from_photos: { lat_deg: 48, lon_deg: 11 }, photos_reason: "found",
};
const NONE = (reason: string): ObservingSite => ({
  location_source: "none", location_reason: null, observer: null,
  from_photos: null, photos_reason: reason,
});

describe("where you observe from — which button is lit", () => {
  it("needs BOTH boxes for a typed location, because the planner does", () => {
    // `_resolve_observer_detail` only obeys Settings when lat AND lon are set.
    expect(hasTypedLocation({ site_lat: 51.5, site_lon: -0.1 })).toBe(true);
    expect(hasTypedLocation({ site_lat: 51.5, site_lon: null })).toBe(false);
    expect(hasTypedLocation({})).toBe(false);
  });

  it("is 'photos' on an untouched install and 'typed' once a location is in", () => {
    expect(siteMode({ site_lat: null, site_lon: null }, false)).toBe("photos");
    expect(siteMode({ site_lat: 51.5, site_lon: -0.1 }, false)).toBe("typed");
  });

  it("stays 'typed' part-way through typing, so the boxes don't vanish", () => {
    expect(siteMode({ site_lat: 51.5, site_lon: null }, false)).toBe("typed");
    expect(siteMode({}, true)).toBe("typed");
  });

  it("'Read it from my photos' clears both boxes and nothing else", () => {
    expect(READ_FROM_PHOTOS_PATCH).toEqual({ site_lat: null, site_lon: null });
  });
});

describe("where you observe from — the boxes", () => {
  it("hides them when the photos already say where you are", () => {
    expect(showTypedBoxes("photos", PHOTOS)).toBe(false);
  });

  it("shows them whenever the photos can't — the case Tonight links here for", () => {
    expect(showTypedBoxes("photos", NONE("no-site-header"))).toBe(true);
    expect(showTypedBoxes("photos", undefined)).toBe(true);
    expect(showTypedBoxes("typed", PHOTOS)).toBe(true);
  });
});

describe("where you observe from — the 'Currently' line", () => {
  it("formats a location to one decimal with compass letters", () => {
    expect(formatLatLon(51.4934, -0.0098)).toBe("51.5° N, 0.0° W");
    expect(formatLatLon(-33.86, 151.21)).toBe("33.9° S, 151.2° E");
  });

  it("previews the form, not what was saved — a typed location wins", () => {
    const line = currentLocationLine({ site_lat: 10, site_lon: 20 }, "typed", PHOTOS);
    expect(line).toEqual({ text: "Typed in: 10.0° N, 20.0° E", known: true });
  });

  it("names the photos' location when it reads from them", () => {
    const line = currentLocationLine({}, "photos", PHOTOS);
    expect(line.text).toBe("Read from your Seestar's photos: 48.0° N, 11.0° E");
    expect(line.known).toBe(true);
  });

  it("says a half-typed location is not in force yet", () => {
    const line = currentLocationLine({ site_lat: 10 }, "typed", PHOTOS);
    expect(line.known).toBe(false);
    expect(line.text).toMatch(/Type both latitude and longitude/);
  });

  it("uses the planner's own wording for why the photos say nothing", () => {
    expect(currentLocationLine({}, "photos", NONE("no-site-header")).text)
      .toMatch(/^Your subs don't say where you were — type it in below/);
  });

  it("doesn't send somebody to type a location when the frames are unreadable", () => {
    // `siteUnknownCopy` withholds the Settings fix for this case on purpose.
    const t = currentLocationLine({}, "photos", NONE("unreadable")).text;
    expect(t).toMatch(/Couldn't read your frames/);
    expect(t).not.toMatch(/type it in/);
  });
});

describe("the horizon drawing", () => {
  const point = (path: string) => {
    const m = /L([\d.]+) ([\d.]+)/.exec(path)!;
    return [Number(m[1]), Number(m[2])];
  };

  it("lights the whole dome at 0° and a narrow cap near 80°", () => {
    const [x0, y0] = point(altitudeBandPath(0));
    expect(x0).toBeCloseTo(HORIZON.cx + HORIZON.r, 1);
    expect(y0).toBeCloseTo(HORIZON.cy, 1);
    const [x80, y80] = point(altitudeBandPath(80));
    expect(x80).toBeLessThan(HORIZON.cx + 30);
    expect(y80).toBeLessThan(HORIZON.cy - 130);
  });

  it("redraws as the slider moves — a higher floor is a higher edge", () => {
    expect(point(altitudeBandPath(45))[1]).toBeLessThan(point(altitudeBandPath(30))[1]);
  });

  it("still draws a stored value outside the field's range", () => {
    expect(altitudeBandPath(95)).toBe(altitudeBandPath(80));
    expect(altitudeBandPath(-5)).toBe(altitudeBandPath(0));
  });

  it("explains the number in plain words", () => {
    expect(altitudeHint(10)).toMatch(/hazy/);
    expect(altitudeHint(30)).toMatch(/trees/);
    expect(altitudeHint(60)).toMatch(/fewer/);
  });
});

describe("the NAS memory bar", () => {
  it("splits total RAM into other apps / room for one stack / kept free", () => {
    const bar = memoryBar({ total_gb: 16, available_gb: 6, stack_budget_gb: 4.2,
      stack_budget_source: "available" })!;
    expect(bar.otherGb).toBe(10);
    expect(bar.roomGb).toBe(4.2);
    expect(bar.freeGb).toBe(1.8);
    expect(bar.otherPct + bar.roomPct + bar.freePct).toBeCloseTo(100, 5);
    expect(bar.clipped).toBe(false);
  });

  it("never draws more room than is free, and says it clipped", () => {
    const bar = memoryBar({ total_gb: 16, available_gb: 6, stack_budget_gb: 64,
      stack_budget_source: "setting" })!;
    expect(bar.roomGb).toBe(6);
    expect(bar.freeGb).toBe(0);
    expect(bar.clipped).toBe(true);
  });

  it("draws nothing on an older backend rather than a guess", () => {
    expect(memoryBar({ total_gb: 16, available_gb: 6 })).toBeNull();
    expect(memoryBar(undefined)).toBeNull();
  });

  it("heads the bar with Automatic, or the number in the form", () => {
    expect(memoryHeadline({ max_stack_memory_gb: null })).toMatch(/^Automatic/);
    expect(memoryHeadline({ max_stack_memory_gb: 12 })).toBe("at most 12 GB per stack.");
  });
});
