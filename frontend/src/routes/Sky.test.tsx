import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { describe, expect, it, vi } from "vitest";
import {
  BRIGHT_STAR_POINT_SIZE, MyMap, OFFLINE_FOV_MAX, OFFLINE_FOV_MIN,
  STAR_LABEL_FONT_PX, STAR_LABEL_OFFSET_PX, SkyView, initialSkyMode, initialSkyView,
  myMapFilename, myMapSaveOffered, offlineCameraPosition, skyFootprintLine,
  starPointDiameterPx,
} from "./Sky";
import { raDecToVector, type SkyImage, type SkyStar } from "../sky/projection";
import { MantineProvider } from "@mantine/core";
import { api } from "../api/client";
import * as client from "../api/client";
import { MemoryRouter } from "react-router-dom";
import { formatStampDate } from "../format";

/** MyMap asks the server how much sky its pictures cover, so it needs a query
 *  client. Kept in one helper so every case renders it the same way. */
function renderMyMap() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <MantineProvider>
      <QueryClientProvider client={qc}><MyMap /></QueryClientProvider>
    </MantineProvider>,
  );
}

function image(
  timestamp_utc: string | null,
  capture: { start?: string | null; end?: string | null } = {},
) {
  return {
    ra_deg: 83.8221, dec_deg: -5.3911, timestamp_utc,
    capture_night_start: capture.start ?? null,
    capture_night_end: capture.end ?? null,
  };
}

describe("skyFootprintLine", () => {
  it("dates a footprint the way every other picture surface does", () => {
    // Found by dogfooding the Sky Map: the card printed a raw `2026-08-17`
    // while the Gallery, History and the Target hero print "17 Aug 2026" for
    // the same run — and the raw slice is the *UTC* day, so for an evening
    // stack west of UTC it named a different calendar day from every other
    // surface. 03:30 UTC is that case.
    const line = skyFootprintLine(image("2026-08-17T03:30:00Z"));
    expect(line).toBe(
      `RA 83.822° · Dec -5.391° · Stacked ${formatStampDate("2026-08-17T03:30:00Z")}`);
    expect(line).not.toContain("2026-08-17");
  });

  it("says when the subs were SHOT when the run knows, not when it stacked", () => {
    // The whole point of the label: an unlabelled date beside a picture reads
    // as the night it was taken, and on a re-stack of a back catalogue the
    // stack stamp is years out.
    const line = skyFootprintLine(
      image("2026-08-17T03:30:00Z", { start: "2024-11-15", end: "2024-11-18" }));
    expect(line).toBe("RA 83.822° · Dec -5.391° · Shot 15–18 Nov 2024");
    expect(line).not.toContain("2026");
  });

  it("labels the stack date rather than passing it off as a capture one", () => {
    // Every run recorded before the app knew when its subs were shot — which is
    // most of an existing library — and the honest answer is to say which date
    // this is, not to go silent and not to imply the other.
    const line = skyFootprintLine(image("2026-08-17T03:30:00Z"));
    expect(line).toContain("Stacked");
    expect(line).not.toContain("Shot");
  });

  it("keeps the coordinates and drops the separator when there is no date", () => {
    expect(skyFootprintLine(image(null))).toBe("RA 83.822° · Dec -5.391°");
    expect(skyFootprintLine(image(""))).toBe("RA 83.822° · Dec -5.391°");
  });

  it("says nothing rather than 'Invalid Date' for an unreadable stamp", () => {
    const line = skyFootprintLine(image("not-a-date"));
    expect(line).toBe("RA 83.822° · Dec -5.391°");
    expect(line).not.toMatch(/Invalid/);
  });
});

describe("MyMap", () => {
  it("shows the all-sky picture built from the owner's own data", () => {
    renderMyMap();
    const img = screen.getByRole("img");
    expect(img.getAttribute("src")).toBe(api.myMapUrl());
    expect(img.getAttribute("src")).toBe("/api/sky/my-map.png");
    // Named for what it is, so a screen reader doesn't just say "image".
    expect(img.getAttribute("alt")).toMatch(/your own pictures/i);
  });

  it("invites the owner to keep it, from the bytes already on screen", () => {
    renderMyMap();
    const save = screen.getByRole("link", { name: /save this map/i });
    // The same endpoint the <img> is showing — never a second render.
    expect(save).toHaveAttribute("href", api.myMapUrl());
    expect(save.getAttribute("download")).toMatch(
      /^astrostack-my-map-\d{4}-\d{2}-\d{2}\.png$/);
  });
  it("says how much of the sky those pictures actually cover", async () => {
    vi.spyOn(client.api, "skyCoverage").mockResolvedValue({
      deg2: 18.4, sky_fraction: 18.4 / 41252.96, n_pictures: 12,
      whole_sky_deg2: 41252.96,
    });
    renderMyMap();
    // The map itself can't answer this — it's a non-equal-area projection that
    // draws every picture larger than life — so the number comes off the runs'
    // own WCS, and the line anchors it in full Moons.
    expect(await screen.findByText(/18\.4 square degrees/)).toBeInTheDocument();
    expect(screen.getByText(/full Moons/)).toBeInTheDocument();
    expect(screen.getByText(/0\.045% of the whole sky/)).toBeInTheDocument();
  });

  it("stays quiet on a fresh install rather than claiming 0% of the sky", async () => {
    vi.spyOn(client.api, "skyCoverage").mockResolvedValue({
      deg2: 0, sky_fraction: 0, n_pictures: 0, whole_sky_deg2: 41252.96,
    });
    renderMyMap();
    await waitFor(() => expect(client.api.skyCoverage).toHaveBeenCalled());
    expect(screen.queryByText(/square degrees/)).toBeNull();
  });
});

describe("myMapFilename", () => {
  it("dates the file by the viewer's own day, zero-padded", () => {
    // Local, not the UTC slice: 23:30 on the 29th west of UTC is still the 29th
    // to the person saving it, the same rule every other picture surface uses.
    expect(myMapFilename(new Date(2026, 7, 9, 23, 30)))
      .toBe("astrostack-my-map-2026-08-09.png");
  });
});

describe("initialSkyMode", () => {
  it("opens on the map a link asked for, so 'My map' is one click away", () => {
    // The Dashboard's sky-coverage line links here; without this it landed on
    // the real-sky atlas and the stat's own map was another switch away.
    expect(initialSkyMode("mine", null)).toBe("mine");
    expect(initialSkyMode("offline", "mine")).toBe("offline");
  });

  it("leaves the remembered default alone when no link asked for one", () => {
    expect(initialSkyMode(null, "mine")).toBe("mine");
    expect(initialSkyMode(null, null)).toBe("offline");
  });

  it("opens on the offline star map, not the one that fetches sky imagery", () => {
    // The owner said the mode that pulls imagery is not one he wants to land
    // on, and defaulting to the only view that reaches the internet is the
    // wrong way round for the local rule. "Real sky (online)" is still on the
    // switch, and picking it is remembered — it just isn't where a first open,
    // on a new browser or a new device, starts.
    expect(initialSkyMode(null, null)).toBe("offline");
    expect(initialSkyMode(null, "online")).toBe("online");
    expect(initialSkyMode("online", null)).toBe("online");
  });

  it("ignores a value that isn't a map, rather than showing nothing", () => {
    // A hand-typed URL, an old bookmark, or a stored value from a build that
    // named its modes differently — all fall through to something that renders.
    expect(initialSkyMode("universe", "mine")).toBe("mine");
    expect(initialSkyMode("", null)).toBe("offline");
    expect(initialSkyMode(null, "nonsense")).toBe("offline");
  });
});

describe("initialSkyView", () => {
  // Found by dogfooding the app after "Stars (offline)" became the mode Sky Map
  // opens in: the offline viewer opened on a fixed patch of sky (RA 18h) that
  // held four of the sixty bundled bright stars and none of the user's own
  // pictures — a black rectangle that reads as a map which failed to load.
  // "Real sky (online)" has always centred on the newest picture.
  function pic(over: Partial<SkyImage> = {}): SkyImage {
    return {
      safe: "M42", name: "Orion Nebula",
      ra_deg: 83.82, dec_deg: -5.39,
      width_deg: 2.1, height_deg: 1.4, rotation_deg: 0,
      preview_url: "/p.png", timestamp_utc: "2026-09-01T00:00:00Z", run_id: 1,
      ...over,
    };
  }
  const CATALOG: SkyStar[] = [
    { name: "Arcturus", ra_deg: 213.9, dec_deg: 19.2, mag: -0.05 },
    { name: "Sirius", ra_deg: 101.3, dec_deg: -16.7, mag: -1.46 },
    { name: "Vega", ra_deg: 279.2, dec_deg: 38.8, mag: 0.03 },
  ];

  it("opens on the newest picture, framed the way the online viewer frames it", () => {
    const older = pic({ run_id: 1, timestamp_utc: "2026-08-01T00:00:00Z" });
    const newest = pic({
      run_id: 2, timestamp_utc: "2026-09-05T00:00:00Z",
      ra_deg: 10.68, dec_deg: 41.27, width_deg: 3,
    });
    // Deliberately out of order: "newest" is the stack time, not the position.
    const v = initialSkyView([newest, older], CATALOG);
    expect(v.raDeg).toBeCloseTo(10.68);
    expect(v.decDeg).toBeCloseTo(41.27);
    expect(v.fovDeg).toBeCloseTo(18);  // 3° × the 6 picture-widths Aladin uses
  });

  it("keeps the opening FOV inside the range the viewer's own zoom allows", () => {
    // A Seestar field is ~2°, so six of them is already below the floor; an
    // all-sky mosaic would be above the ceiling. Either way the first scroll
    // must not jump to an edge.
    expect(initialSkyView([pic({ width_deg: 0.5 })], CATALOG).fovDeg).toBe(OFFLINE_FOV_MIN);
    expect(initialSkyView([pic({ width_deg: 90 })], CATALOG).fovDeg).toBe(OFFLINE_FOV_MAX);
  });

  it("opens on the brightest star in the backdrop when there are no pictures yet", () => {
    // A first-run install. The star comes from the catalogue the viewer is
    // already drawing, so it can never aim where the backdrop has nothing.
    const v = initialSkyView([], CATALOG);
    expect(v.raDeg).toBeCloseTo(101.3);   // Sirius, mag -1.46
    expect(v.decDeg).toBeCloseTo(-16.7);
    expect(v.fovDeg).toBe(OFFLINE_FOV_MAX);
  });

  it("still opens somewhere real with no pictures and no catalogue at all", () => {
    // The old fixed direction, kept exactly: RA 270°, Dec 0°, 70° across.
    expect(initialSkyView([], [])).toEqual({ raDeg: 270, decDeg: 0, fovDeg: 70 });
    expect(initialSkyView(null, null)).toEqual({ raDeg: 270, decDeg: 0, fovDeg: 70 });
  });

  it("skips a picture or a star it cannot place, rather than aiming at NaN", () => {
    const broken = pic({ run_id: 9, timestamp_utc: "2026-09-09T00:00:00Z", ra_deg: NaN });
    // The newest picture has no usable position, so the older placed one wins.
    const v = initialSkyView([pic({ ra_deg: 120, dec_deg: 5 }), broken], CATALOG);
    expect(v.raDeg).toBeCloseTo(120);
    expect(v.decDeg).toBeCloseTo(5);
    const starless = initialSkyView([], [{ name: "?", ra_deg: NaN, dec_deg: 0, mag: -9 }]);
    expect(starless).toEqual({ raDeg: 270, decDeg: 0, fovDeg: 70 });
  });

  it("stays off the poles, where the viewer's orbit controls have no azimuth", () => {
    expect(initialSkyView([pic({ dec_deg: 90 })], CATALOG).decDeg).toBeCloseTo(89.9);
    expect(initialSkyView([pic({ dec_deg: -90 })], CATALOG).decDeg).toBeCloseTo(-89.9);
  });
});

describe("the star labels clear their own stars", () => {
  // Also found by dogfooding: the label was centred on the star, so the star's
  // dot was painted through the middle of its own name — magnified from the
  // screenshot, "Rigel" read as "R∎el".
  it("steps the name below the dot at every height this viewer runs at", () => {
    // A phone in portrait through a 1440p desktop. The dot's size does not
    // depend on the zoom (see `starPointDiameterPx`), so one offset covers the
    // whole range — but it does grow with the viewport, so the tallest screen
    // is the one that decides.
    for (const viewportHeightPx of [600, 800, 1000, 1400]) {
      const dotRadius = starPointDiameterPx(BRIGHT_STAR_POINT_SIZE, viewportHeightPx) / 2;
      const textTopEdge = STAR_LABEL_OFFSET_PX - STAR_LABEL_FONT_PX / 2;
      expect(textTopEdge).toBeGreaterThanOrEqual(dotRadius);
    }
  });

  it("scales the dot with the viewport and not with the zoom", () => {
    // The property the single fixed offset rests on. three.js sizes an
    // attenuated point from the renderer height alone; the field of view moves
    // it around the screen without resizing it.
    expect(starPointDiameterPx(BRIGHT_STAR_POINT_SIZE, 800)).toBeCloseTo(6.4);
    expect(starPointDiameterPx(BRIGHT_STAR_POINT_SIZE, 1600))
      .toBeCloseTo(2 * starPointDiameterPx(BRIGHT_STAR_POINT_SIZE, 800));
  });
});

describe("offlineCameraPosition", () => {
  it("puts the camera where looking at the centre looks at the asked-for sky", () => {
    // The camera sits a hair off the centre of the sphere and is aimed at the
    // origin, so it looks along the negative of its own position.
    const view = { raDeg: 83.82, decDeg: -5.39, fovDeg: 30 };
    const [x, y, z] = offlineCameraPosition(view, 0.1);
    const want = raDecToVector(view.raDeg, view.decDeg, 1);
    const len = Math.hypot(x, y, z);
    expect(len).toBeCloseTo(0.1);
    expect(-x / len).toBeCloseTo(want.x);
    expect(-y / len).toBeCloseTo(want.y);
    expect(-z / len).toBeCloseTo(want.z);
  });

  it("reproduces the old fixed camera for the no-data fallback", () => {
    // RA 270°, Dec 0° is exactly [0, 0, 0.1] looking at the origin — what the
    // viewer did unconditionally before it learned to aim.
    const [x, y, z] = offlineCameraPosition({ raDeg: 270, decDeg: 0, fovDeg: 70 });
    expect(x).toBeCloseTo(0);
    expect(y).toBeCloseTo(0);
    expect(z).toBeCloseTo(0.1);
  });
});

describe("myMapSaveOffered", () => {
  it("offers the save when the owner has pictures on the map", () => {
    expect(myMapSaveOffered([{}], false)).toBe(true);
    expect(myMapSaveOffered([{}, {}, {}], false)).toBe(true);
  });

  it("withholds it on a fresh install, where the map is a bare grid", () => {
    expect(myMapSaveOffered([], false)).toBe(false);
  });

  it("treats a failed query as unknown, not as empty", () => {
    // A dead click costs one click; hiding a working feature costs the feature.
    expect(myMapSaveOffered(undefined, true)).toBe(true);
    expect(myMapSaveOffered([], true)).toBe(true);
  });

  it("waits rather than guessing while the answer is still in flight", () => {
    expect(myMapSaveOffered(undefined, false)).toBe(false);
    expect(myMapSaveOffered(null, false)).toBe(false);
  });
});

describe("MyMap — nothing to save yet", () => {
  it("drops the save button when the map has no pictures on it", () => {
    render(
      <MantineProvider>
        <QueryClientProvider client={new QueryClient({
          defaultOptions: { queries: { retry: false } },
        })}>
          <MyMap savable={false} />
        </QueryClientProvider>
      </MantineProvider>,
    );
    // The map itself still renders — it is the page's whole stage.
    expect(screen.getByRole("img")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /save this map/i })).toBeNull();
  });
});

describe("SkyView — the save button is gated on the map's own pictures", () => {
  function renderSky() {
    localStorage.setItem("astrostack.skyMode", "mine");
    return render(
      <MantineProvider>
        <QueryClientProvider client={new QueryClient({
          defaultOptions: { queries: { retry: false } },
        })}>
          <MemoryRouter initialEntries={["/sky"]}>
            <SkyView />
          </MemoryRouter>
        </QueryClientProvider>
      </MantineProvider>,
    );
  }

  it("offers no save on a fresh install, beside its own empty state", async () => {
    vi.spyOn(client.api, "getSky").mockResolvedValue({ stars: [], images: [] });
    renderSky();
    expect(await screen.findByText(/No stacked images yet/)).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /save this map/i })).toBeNull();
  });

  it("offers it as soon as one picture is on the map", async () => {
    vi.spyOn(client.api, "getSky").mockResolvedValue({
      stars: [],
      images: [{
        safe_name: "M_42", name: "M42", ra_deg: 83.8, dec_deg: -5.4,
        width_deg: 1.3, height_deg: 0.7, rotation_deg: 0,
        preview_url: "/api/targets/M_42/stack-runs/1/preview",
        timestamp_utc: "2026-01-01T00:00:00", run_id: 1,
      }] as never,
    });
    renderSky();
    expect(await screen.findByRole("link", { name: /save this map/i }))
      .toBeInTheDocument();
  });
});
