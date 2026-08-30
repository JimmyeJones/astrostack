import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { describe, expect, it, vi } from "vitest";
import { MyMap, initialSkyMode, myMapFilename, skyFootprintLine } from "./Sky";
import { MantineProvider } from "@mantine/core";
import { api } from "../api/client";
import * as client from "../api/client";
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

function image(timestamp_utc: string | null) {
  return { ra_deg: 83.8221, dec_deg: -5.3911, timestamp_utc };
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
      `RA 83.822° · Dec -5.391° · ${formatStampDate("2026-08-17T03:30:00Z")}`);
    expect(line).not.toContain("2026-08-17");
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
    // own WCS, and the line anchors it in full moons.
    expect(await screen.findByText(/18\.4 square degrees/)).toBeInTheDocument();
    expect(screen.getByText(/full moons/)).toBeInTheDocument();
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
    expect(initialSkyMode(null, null)).toBe("online");
  });

  it("ignores a value that isn't a map, rather than showing nothing", () => {
    // A hand-typed URL, an old bookmark, or a stored value from a build that
    // named its modes differently — all fall through to something that renders.
    expect(initialSkyMode("universe", "mine")).toBe("mine");
    expect(initialSkyMode("", null)).toBe("online");
    expect(initialSkyMode(null, "nonsense")).toBe("online");
  });
});
