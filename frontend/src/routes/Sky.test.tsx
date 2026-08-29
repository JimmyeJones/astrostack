import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { MyMap, skyFootprintLine } from "./Sky";
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
    render(<MyMap />);
    const img = screen.getByRole("img");
    expect(img.getAttribute("src")).toBe(api.myMapUrl());
    expect(img.getAttribute("src")).toBe("/api/sky/my-map.png");
    // Named for what it is, so a screen reader doesn't just say "image".
    expect(img.getAttribute("alt")).toMatch(/your own pictures/i);
  });
});
