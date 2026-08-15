import { MantineProvider } from "@mantine/core";
import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { LatestPictureCard, latestPictureCaption } from "./LatestPictureCard";
import type { StackRun } from "../../api/client";

function mkRun(over: Partial<StackRun> = {}): StackRun {
  return {
    id: 7, timestamp_utc: "2026-08-14T22:10:00Z", output_basename: "master",
    n_frames_used: 128, canvas_w: 1920, canvas_h: 1080,
    coverage_min: 128, coverage_max: 128, has_fits: true, has_tiff: false,
    has_preview: true, notes: null, total_exposure_s: 7560, ...over,
  };
}

function renderCard(run: StackRun | null) {
  return render(
    <MantineProvider>
      <MemoryRouter>
        <LatestPictureCard safe="M_42" name="M42" run={run} />
      </MemoryRouter>
    </MantineProvider>,
  );
}

describe("latestPictureCaption", () => {
  it("says when it was stacked, out of how many subs, and how much light", () => {
    const cap = latestPictureCaption(mkRun());
    expect(cap).toMatch(/^Stacked /);
    expect(cap).toContain("128 frames");
    expect(cap).toContain("of light");
  });

  it("says 'frame' for a single-frame stack", () => {
    expect(latestPictureCaption(mkRun({ n_frames_used: 1 }))).toContain("1 frame ");
  });

  it("omits the integration when the run never recorded one", () => {
    expect(latestPictureCaption(mkRun({ total_exposure_s: null })))
      .not.toContain("of light");
  });

  it("omits an unparseable timestamp rather than printing 'Invalid Date'", () => {
    const cap = latestPictureCaption(mkRun({ timestamp_utc: "not-a-date" }));
    expect(cap).not.toMatch(/Stacked/);
    expect(cap).toContain("128 frames");
  });
});

describe("LatestPictureCard", () => {
  it("shows the finished picture with a route into the editor", async () => {
    renderCard(mkRun());
    const img = await screen.findByAltText("Latest stacked picture of M42");
    expect(img.getAttribute("src")).toContain("/stack-runs/7/preview");
    expect(screen.getByRole("link", { name: "Edit this picture" }))
      .toHaveAttribute("href", "/targets/M_42/edit/7");
    expect(screen.getByRole("link", { name: "All versions" }))
      .toHaveAttribute("href", "/targets/M_42/history");
  });

  it("renders nothing at all before there is a finished picture", () => {
    renderCard(null);
    expect(screen.queryByTestId("latest-picture")).not.toBeInTheDocument();
  });

  it("renders nothing for a run that produced no preview", () => {
    renderCard(mkRun({ has_preview: false }));
    expect(screen.queryByTestId("latest-picture")).not.toBeInTheDocument();
  });

  it("opens the same zoomable viewer the rest of the app uses when clicked", async () => {
    renderCard(mkRun());
    const img = await screen.findByAltText("Latest stacked picture of M42");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    fireEvent.click(img.parentElement!);
    expect(await screen.findByRole("dialog")).toBeInTheDocument();
  });
});
