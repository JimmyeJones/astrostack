import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { MyMap, myMapFilename, skyFootprintLine } from "./Sky";
import { MantineProvider } from "@mantine/core";
import { api } from "../api/client";
import { formatStampDate } from "../format";

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
    render(<MantineProvider><MyMap /></MantineProvider>);
    const img = screen.getByRole("img");
    expect(img.getAttribute("src")).toBe(api.myMapUrl());
    expect(img.getAttribute("src")).toBe("/api/sky/my-map.png");
    // Named for what it is, so a screen reader doesn't just say "image".
    expect(img.getAttribute("alt")).toMatch(/your own pictures/i);
  });

  it("invites the owner to keep it, from the bytes already on screen", () => {
    render(<MantineProvider><MyMap /></MantineProvider>);
    const save = screen.getByRole("link", { name: /save this map/i });
    // The same endpoint the <img> is showing — never a second render.
    expect(save).toHaveAttribute("href", api.myMapUrl());
    expect(save.getAttribute("download")).toMatch(
      /^astrostack-my-map-\d{4}-\d{2}-\d{2}\.png$/);
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
