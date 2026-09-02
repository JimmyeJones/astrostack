import { MantineProvider } from "@mantine/core";
import { Notifications } from "@mantine/notifications";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { HistoryView, sortRuns, noiseDeltas, previousRunId, historyCompareHref, noiseTrendSeries, combineMethodLabel, formatEngineVersion, photometricSummaryText, darkScalingSummaryText, rejectionSummaryText, weightingSummaryText, weightingSkippedText, frameAccountingNote, readErrorNote, roughlyAlignedNote, calibrationSummaryText, drizzleDegradedNote, removedOverlayCaption, derivedFromNote } from "./History";
import { formatIntegration } from "../format";
import * as client from "../api/client";
import { FULL_RES_PNG_MAX_LONG_EDGE } from "../fullres";
import { SAMPLE_TOUR_COPY } from "../components/SampleTourNote";
import type { StackRun } from "../api/client";

function mkRun(overrides: Partial<StackRun> = {}): StackRun {
  return {
    id: 1, timestamp_utc: "2026-01-01T00:00:00", output_basename: "M42_stack_01",
    n_frames_used: 42, canvas_w: 100, canvas_h: 100, coverage_min: 0, coverage_max: 1,
    has_fits: true, has_tiff: false, has_preview: false, notes: null,
    ...overrides,
  };
}

function renderHistory() {
  const qc = new QueryClient();
  return render(
    <MantineProvider>
      <Notifications />
      <QueryClientProvider client={qc}>
        <MemoryRouter initialEntries={["/targets/M_42/history"]}>
          <Routes>
            <Route path="/targets/:safe/history" element={<HistoryView />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>
    </MantineProvider>,
  );
}

// Default the page-level catalog-identity fetch (drives "Copy caption") to
// "unidentified" so tests that don't care about it never hit the network; any
// test that needs a named object overrides this spy.
beforeEach(() => {
  vi.spyOn(client.api, "identifyTarget").mockResolvedValue(null);
});

afterEach(() => vi.restoreAllMocks());

function mkIdentity(overrides: Partial<client.ObjectInfo> = {}): client.ObjectInfo {
  return {
    id: "M42", name: "Orion Nebula", type: "nebula",
    constellation: "Orion", constellation_abbr: "Ori",
    ra_deg: 83.82, dec_deg: -5.39, matched_by: "name",
    ...overrides,
  };
}

// The run card groups its file actions behind a "Save / share" menu and its
// "what is this?" actions behind an "About this stack" one, so a test that wants
// one of them has to open its menu first. `menuItem` then matches on the item's
// *name* — a menu item's accessible name also carries its one-line hint, so the
// match is anchored at the start rather than exact.
function openSaveShare(i = 0) {
  fireEvent.click(screen.getAllByRole("button", { name: "Save / share" })[i]);
}
function openAbout(i = 0) {
  fireEvent.click(screen.getAllByRole("button", { name: "About this stack" })[i]);
}
function menuItem(name: string) {
  return screen.findByRole("menuitem", { name: new RegExp(`^${name}`) });
}

describe("HistoryView", () => {
  it("does not delete a stack when the confirmation is declined", async () => {
    vi.spyOn(client.api, "listStackRuns").mockResolvedValue([mkRun()]);
    const del = vi.spyOn(client.api, "deleteStackRun").mockResolvedValue(undefined as never);
    vi.spyOn(window, "confirm").mockReturnValue(false);

    renderHistory();
    await waitFor(() => expect(screen.getByText("M42_stack_01")).toBeInTheDocument());

    fireEvent.click(screen.getByRole("button", { name: "Delete stack" }));

    expect(window.confirm).toHaveBeenCalled();
    expect(del).not.toHaveBeenCalled();
    expect(screen.getByText("M42_stack_01")).toBeInTheDocument();
  });

  it("deletes a stack and refreshes the list once confirmed", async () => {
    vi.spyOn(client.api, "listStackRuns")
      .mockResolvedValueOnce([mkRun()])
      .mockResolvedValueOnce([]);
    const del = vi.spyOn(client.api, "deleteStackRun").mockResolvedValue(undefined as never);
    vi.spyOn(window, "confirm").mockReturnValue(true);

    renderHistory();
    await waitFor(() => expect(screen.getByText("M42_stack_01")).toBeInTheDocument());

    fireEvent.click(screen.getByRole("button", { name: "Delete stack" }));

    await waitFor(() => expect(del).toHaveBeenCalledWith("M_42", 1));
    await waitFor(() => expect(screen.queryByText("M42_stack_01")).not.toBeInTheDocument());
  });

  it("shows FITS provenance when Info is toggled", async () => {
    vi.spyOn(client.api, "listStackRuns").mockResolvedValue([mkRun()]);
    const info = vi.spyOn(client.api, "stackRunInfo").mockResolvedValue({
      run_id: 1, integration_s: 2520, n_frames: 840, weighting: null,
      cards: [
        { key: "OBJECT", value: "M42", comment: "target name" },
        { key: "STACKER", value: "sigma-clip", comment: "stacking method" },
      ],
    });

    renderHistory();
    await waitFor(() => expect(screen.getByText("M42_stack_01")).toBeInTheDocument());

    openAbout();
    fireEvent.click(await menuItem("Info"));

    await waitFor(() => expect(info).toHaveBeenCalledWith("M_42", 1));
    await waitFor(() => expect(screen.getByText(/Integration: 42 min/)).toBeInTheDocument());
    expect(screen.getByText("sigma-clip")).toBeInTheDocument();
    // Plain-language combine line derived from the raw STACKER card.
    expect(screen.getByText(/Combined: κ-σ \(sigma-clip\) outlier rejection/)).toBeInTheDocument();
  });

  it("says how this run framed its target when Info is open", async () => {
    // The verdict is per-run, and History is where two stacks of one target get
    // compared — so it has to say "this one caught all of it" here too, in the
    // same words the Target page uses.
    vi.spyOn(client.api, "listStackRuns").mockResolvedValue([mkRun()]);
    vi.spyOn(client.api, "stackRunInfo").mockResolvedValue({
      run_id: 1, integration_s: 2520, n_frames: 840, weighting: null, cards: [],
    });
    const framing = vi.spyOn(client.api, "stackFraming").mockResolvedValue({
      level: "clipped", coverage: 0.68, off_centre: 0.5,
      object_name: "Orion Nebula", size_arcmin: 85,
      text: "runs off the edge of the frame — about 70% of it made it in. It "
        + "would fit whole, so just re-centre it next session.",
    });

    renderHistory();
    await waitFor(() => expect(screen.getByText("M42_stack_01")).toBeInTheDocument());
    // Not fetched (and nothing shown) until the Info panel is actually opened.
    expect(framing).not.toHaveBeenCalled();

    openAbout();
    fireEvent.click(await menuItem("Info"));

    await waitFor(() => expect(framing).toHaveBeenCalledWith("M_42", 1));
    expect(await screen.findByText("Part of it is outside the frame")).toBeInTheDocument();
    expect(screen.getByText(/^Orion Nebula runs off the edge/)).toBeInTheDocument();
  });

  it("says nothing about framing for a run the endpoint can't judge", async () => {
    vi.spyOn(client.api, "listStackRuns").mockResolvedValue([mkRun()]);
    vi.spyOn(client.api, "stackRunInfo").mockResolvedValue({
      run_id: 1, integration_s: 2520, n_frames: 840, weighting: null, cards: [],
    });
    const framing = vi.spyOn(client.api, "stackFraming").mockResolvedValue(null);

    renderHistory();
    await waitFor(() => expect(screen.getByText("M42_stack_01")).toBeInTheDocument());
    openAbout();
    fireEvent.click(await menuItem("Info"));

    await waitFor(() => expect(framing).toHaveBeenCalled());
    expect(screen.queryByTestId("framing-verdict")).not.toBeInTheDocument();
  });

  it("shows the auto-edit note for a silently auto-edited run", async () => {
    vi.spyOn(client.api, "listStackRuns").mockResolvedValue([mkRun()]);
    vi.spyOn(client.api, "stackRunInfo").mockResolvedValue({
      run_id: 1, integration_s: 2520, n_frames: 840, weighting: null,
      auto_edit:
        "Auto-edited: flattened the background, then applied a natural stretch · measured a ~0.1 sky, 4.7 px stars.",
      cards: [{ key: "STACKER", value: "sigma-clip", comment: "stacking method" }],
    });

    renderHistory();
    await waitFor(() => expect(screen.getByText("M42_stack_01")).toBeInTheDocument());
    openAbout();
    fireEvent.click(await menuItem("Info"));
    await waitFor(() =>
      expect(screen.getByText(/Auto-edited: flattened the background/)).toBeInTheDocument());
  });

  it("shows the auto-edit sky-cast read-out for a walk-away run", async () => {
    vi.spyOn(client.api, "listStackRuns").mockResolvedValue([mkRun()]);
    vi.spyOn(client.api, "stackRunInfo").mockResolvedValue({
      run_id: 1, integration_s: 2520, n_frames: 840, weighting: null,
      auto_edit: "Auto-edited: flattened the background, then applied a natural stretch.",
      sky_cast: { r: 0.2, g: 0.24, b: 0.2, neutral: false, cast: "green", deviation: 0.013 },
      cards: [{ key: "STACKER", value: "sigma-clip", comment: "stacking method" }],
    });

    renderHistory();
    await waitFor(() => expect(screen.getByText("M42_stack_01")).toBeInTheDocument());
    openAbout();
    fireEvent.click(await menuItem("Info"));
    await waitFor(() =>
      expect(
        screen.getByText("Auto's background came out with a slight green cast"),
      ).toBeInTheDocument());
  });

  it("shows which white-balance path Auto ran for a walk-away run", async () => {
    vi.spyOn(client.api, "listStackRuns").mockResolvedValue([mkRun()]);
    vi.spyOn(client.api, "stackRunInfo").mockResolvedValue({
      run_id: 1, integration_s: 2520, n_frames: 840, weighting: null,
      auto_edit: "Auto-edited: flattened the background, then applied a natural stretch.",
      color_cal: { mode_used: "gray_star", n_stars_used: 240, notes: "gray-world over detected stars" },
      cards: [{ key: "STACKER", value: "sigma-clip", comment: "stacking method" }],
    });

    renderHistory();
    await waitFor(() => expect(screen.getByText("M42_stack_01")).toBeInTheDocument());
    openAbout();
    fireEvent.click(await menuItem("Info"));
    await waitFor(() =>
      expect(
        screen.getByText("Auto white-balanced from 240 stars ✓"),
      ).toBeInTheDocument());
  });

  it("explains why a walk-away run's quality weighting did not count", async () => {
    vi.spyOn(client.api, "listStackRuns").mockResolvedValue([mkRun()]);
    vi.spyOn(client.api, "stackRunInfo").mockResolvedValue({
      run_id: 1, integration_s: 60, n_frames: 6, weighting: null,
      weighting_skipped: { reason: "minmax", auto: true, min_frames: 11 },
      cards: [{ key: "STACKER", value: "min-max-reject", comment: "stacking method" }],
    });

    renderHistory();
    await waitFor(() => expect(screen.getByText("M42_stack_01")).toBeInTheDocument());
    openAbout();
    fireEvent.click(await menuItem("Info"));
    await waitFor(() =>
      expect(screen.getByText(/Quality weighting was on, but this stack with 6 subs/))
        .toBeInTheDocument());
    expect(screen.getByText(/from 11 subs it switches to sigma clipping/)).toBeInTheDocument();
  });

  it("tells the user when a saved calibration pick was skipped by the run", async () => {
    vi.spyOn(client.api, "listStackRuns").mockResolvedValue([mkRun()]);
    vi.spyOn(client.api, "stackRunInfo").mockResolvedValue({
      run_id: 1, integration_s: 2520, n_frames: 840, weighting: null,
      calibration_skipped: [
        "Your saved master dark wasn't used: it's no longer in your calibration library.",
      ],
      cards: [{ key: "STACKER", value: "sigma-clip", comment: "stacking method" }],
    });

    renderHistory();
    await waitFor(() => expect(screen.getByText("M42_stack_01")).toBeInTheDocument());
    openAbout();
    fireEvent.click(await menuItem("Info"));

    await waitFor(() =>
      expect(
        screen.getByText(/Your saved master dark wasn't used: it's no longer in your/),
      ).toBeInTheDocument());
  });

  it("tells the user when the master the run DID apply doesn't match the subs", async () => {
    // The run is calibrated, so the Info panel's calibration line reads as good
    // news. Without this the only record of a 30s dark being subtracted from 10s
    // subs is a server log line the owner never opens.
    vi.spyOn(client.api, "listStackRuns").mockResolvedValue([mkRun()]);
    vi.spyOn(client.api, "stackRunInfo").mockResolvedValue({
      run_id: 1, integration_s: 2520, n_frames: 840, weighting: null,
      calibration_warnings: [
        "Master dark is 30s but your subs are 10s — its pedestal will be "
        + "over-subtracted on every frame.",
      ],
      cards: [
        { key: "STACKER", value: "sigma-clip", comment: "stacking method" },
        { key: "CALSTAT", value: "dark", comment: "calibration masters applied" },
      ],
    });

    renderHistory();
    await waitFor(() => expect(screen.getByText("M42_stack_01")).toBeInTheDocument());
    openAbout();
    fireEvent.click(await menuItem("Info"));

    await waitFor(() =>
      expect(screen.getByText(/Master dark is 30s but your subs are 10s/))
        .toBeInTheDocument());
    // Both lines show: what the picture got, and what's wrong with it.
    expect(screen.getByText("Calibrated with your master dark.")).toBeInTheDocument();
  });

  it("shows the quality-weighting summary when present", async () => {
    vi.spyOn(client.api, "listStackRuns").mockResolvedValue([mkRun()]);
    vi.spyOn(client.api, "stackRunInfo").mockResolvedValue({
      run_id: 1, integration_s: 2520, n_frames: 840,
      weighting: { mode: "quality", n_downweighted: 7, min: 0.31, max: 1.0, median: 0.72 },
      cards: [{ key: "STACKER", value: "sigma-clip", comment: "stacking method" }],
    });

    renderHistory();
    await waitFor(() => expect(screen.getByText("M42_stack_01")).toBeInTheDocument());
    openAbout();
    fireEvent.click(await menuItem("Info"));

    await waitFor(() =>
      expect(
        screen.getByText(/of your 840 subs, 7 were softer or hazier/),
      ).toBeInTheDocument());
    // Reassures rather than alarms: down-weighted, not dropped.
    expect(screen.getByText(/not dropped — just weighted down/)).toBeInTheDocument();
  });

  it("shows integration time inline on a card without opening Info", async () => {
    vi.spyOn(client.api, "listStackRuns").mockResolvedValue([
      mkRun({ total_exposure_s: 2520 }),
    ]);

    renderHistory();
    // 2520 s → "42 min" on the card metadata line, no Info toggle needed.
    await waitFor(() => expect(screen.getByText(/42 min/)).toBeInTheDocument());
  });

  it("labels the catalog objects in the field when Identify is toggled", async () => {
    vi.spyOn(client.api, "listStackRuns").mockResolvedValue([mkRun({ has_preview: true })]);
    const annot = vi.spyOn(client.api, "stackAnnotations").mockResolvedValue({
      width: 1000, height: 600,
      objects: [
        { catalog_id: "M31", name: "Andromeda Galaxy", type: "galaxy",
          ra_deg: 10.68, dec_deg: 41.27, x_px: 500, y_px: 300 },
      ],
      scale_bar: null,
    });

    renderHistory();
    await waitFor(() => expect(screen.getByText("M42_stack_01")).toBeInTheDocument());

    // Not fetched until the user asks.
    expect(annot).not.toHaveBeenCalled();
    openAbout();
    fireEvent.click(await menuItem("Identify"));

    await waitFor(() => expect(annot).toHaveBeenCalledWith("M_42", 1));
    // The plain-language "what else is in this picture?" list names the object,
    // its friendly type, and roughly where it sits in the frame.
    await waitFor(() =>
      expect(screen.getByText(/In this picture — 1 catalog object:/)).toBeInTheDocument());
    expect(
      screen.getByText(/Andromeda Galaxy \(M31\) — a galaxy, near the centre\./),
    ).toBeInTheDocument();
  });

  it("won't plot object pins on a picture a past save rotated North-up", async () => {
    // The North-up toggle starts off on every page load, so a run whose *stored*
    // preview was saved rotated used to get its pins and scale bar drawn on the
    // un-rotated FITS grid — over a picture that had since turned.
    vi.spyOn(client.api, "listStackRuns").mockResolvedValue([
      mkRun({ has_preview: true, preview_north_up_deg: 90 }),
    ]);
    vi.spyOn(client.api, "stackAnnotations").mockResolvedValue({
      width: 1000, height: 600,
      objects: [
        { catalog_id: "M31", name: "Andromeda Galaxy", type: "galaxy",
          ra_deg: 10.68, dec_deg: 41.27, x_px: 500, y_px: 300 },
      ],
      scale_bar: null,
    });

    renderHistory();
    await waitFor(() => expect(screen.getByText("M42_stack_01")).toBeInTheDocument());
    openAbout();
    fireEvent.click(await menuItem("Identify"));

    // The list is withheld, and the card says why in plain language.
    await waitFor(() =>
      expect(screen.getByText(/saved rotated so North is up/)).toBeInTheDocument());
    expect(screen.queryByText(/In this picture —/)).not.toBeInTheDocument();
  });

  it("still plots object pins on a picture saved un-rotated", async () => {
    // The no-regression half: an ordinary run (0 / absent) is unaffected.
    vi.spyOn(client.api, "listStackRuns").mockResolvedValue([
      mkRun({ has_preview: true, preview_north_up_deg: 0 }),
    ]);
    vi.spyOn(client.api, "stackAnnotations").mockResolvedValue({
      width: 1000, height: 600,
      objects: [
        { catalog_id: "M31", name: "Andromeda Galaxy", type: "galaxy",
          ra_deg: 10.68, dec_deg: 41.27, x_px: 500, y_px: 300 },
      ],
      scale_bar: null,
    });

    renderHistory();
    await waitFor(() => expect(screen.getByText("M42_stack_01")).toBeInTheDocument());
    openAbout();
    fireEvent.click(await menuItem("Identify"));

    await waitFor(() =>
      expect(screen.getByText(/In this picture — 1 catalog object:/)).toBeInTheDocument());
    expect(screen.queryByText(/saved rotated so North is up/)).not.toBeInTheDocument();
  });

  it("says so plainly when no catalog objects fall in the field", async () => {
    vi.spyOn(client.api, "listStackRuns").mockResolvedValue([mkRun({ has_preview: true })]);
    vi.spyOn(client.api, "stackAnnotations").mockResolvedValue({
      width: 1000, height: 600, objects: [], scale_bar: null,
    });

    renderHistory();
    await waitFor(() => expect(screen.getByText("M42_stack_01")).toBeInTheDocument());
    openAbout();
    fireEvent.click(await menuItem("Identify"));
    await waitFor(() =>
      expect(screen.getByText(/No catalog objects fall inside this field/)).toBeInTheDocument());
  });

  it("shows the picture's angular scale and a Moon comparison when Scale is toggled", async () => {
    vi.spyOn(client.api, "listStackRuns").mockResolvedValue([mkRun({ has_preview: true })]);
    const annot = vi.spyOn(client.api, "stackAnnotations").mockResolvedValue({
      width: 1000, height: 600, objects: [],
      scale_bar: {
        arcsec: 1800, label: "30′", fraction: 0.18, frame_arcmin: 166.6,
        moon_comparison: "the whole frame is about 5.4 full Moons wide",
      },
    });

    renderHistory();
    await waitFor(() => expect(screen.getByText("M42_stack_01")).toBeInTheDocument());
    // Not fetched until the user asks.
    expect(annot).not.toHaveBeenCalled();
    openAbout();
    fireEvent.click(await menuItem("Scale"));

    await waitFor(() => expect(annot).toHaveBeenCalledWith("M_42", 1));
    await waitFor(() =>
      expect(screen.getByText(/about 5.4 full Moons wide/)).toBeInTheDocument());
    // (The scale-bar overlay's on-image geometry needs a measured box — 0 in
    // jsdom — so it's covered by scaleBarLayout's pure unit test instead.)
  });

  it("describes the trimmed picture, not the canvas behind it", async () => {
    // The one-click "Process target" auto-edit trims a mosaic's ragged border, so
    // the stored preview — the picture on screen, downloaded and shared — is
    // narrower than the canvas. The Moon sentence is a claim about *that*
    // picture; sized on the canvas it overstates the field by 1/0.7 ≈ 1.43×.
    vi.spyOn(client.api, "listStackRuns").mockResolvedValue([
      mkRun({ has_preview: true, preview_crop: { x0: 0.15, y0: 0.15, x1: 0.85, y1: 0.85 } }),
    ]);
    vi.spyOn(client.api, "stackAnnotations").mockResolvedValue({
      width: 1000, height: 600, objects: [],
      scale_bar: {
        arcsec: 1800, label: "30′", fraction: 0.18, frame_arcmin: 166.6,
        moon_comparison: "the whole frame is about 5.4 full Moons wide",
      },
      preview_scale_bar: {
        arcsec: 1800, label: "30′", fraction: 0.26, frame_arcmin: 116.6,
        moon_comparison: "the whole frame is about 3.8 full Moons wide",
      },
    });

    renderHistory();
    await waitFor(() => expect(screen.getByText("M42_stack_01")).toBeInTheDocument());
    openAbout();
    fireEvent.click(await menuItem("Scale"));

    await waitFor(() =>
      expect(screen.getByText(/about 3.8 full Moons wide/)).toBeInTheDocument());
    expect(screen.queryByText(/about 5.4 full Moons wide/)).not.toBeInTheDocument();
  });

  it("copies a caption sized to the trimmed picture it shares", async () => {
    vi.spyOn(client.api, "listStackRuns").mockResolvedValue([
      mkRun({ has_preview: true, n_frames_used: 240, total_exposure_s: 40 * 60,
        timestamp_utc: "2026-07-20T22:14:03",
        preview_crop: { x0: 0.15, y0: 0.15, x1: 0.85, y1: 0.85 } }),
    ]);
    vi.spyOn(client.api, "identifyTarget").mockResolvedValue(mkIdentity());
    vi.spyOn(client.api, "stackAnnotations").mockResolvedValue({
      width: 1000, height: 600, objects: [],
      scale_bar: {
        arcsec: 1800, label: "30′", fraction: 0.18, frame_arcmin: 166.6,
        moon_comparison: "the whole frame is about 5.4 full Moons wide",
      },
      preview_scale_bar: {
        arcsec: 1800, label: "30′", fraction: 0.26, frame_arcmin: 116.6,
        moon_comparison: "the whole frame is about 3.8 full Moons wide",
      },
    });
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.assign(navigator, { clipboard: { writeText } });

    renderHistory();
    await waitFor(() => expect(screen.getByText("M42_stack_01")).toBeInTheDocument());
    openSaveShare();
    fireEvent.click(await menuItem("Copy caption"));

    await waitFor(() => expect(writeText).toHaveBeenCalledTimes(1));
    expect(writeText.mock.calls[0][0]).toContain("about 3.8 full Moons wide");
    expect(writeText.mock.calls[0][0]).not.toContain("5.4");
  });

  it("offers the compass alongside the scale, the pair the shared JPEG bakes", async () => {
    // The download has carried a scale bar *and* a North/East rose since
    // v0.284.0; the on-screen overlay only ever drew the bar. One toggle now
    // means one idea — "how big, and which way up?" — on screen and in the file.
    vi.spyOn(client.api, "listStackRuns").mockResolvedValue([mkRun({ has_preview: true })]);
    const annot = vi.spyOn(client.api, "stackAnnotations").mockResolvedValue({
      width: 1000, height: 600, objects: [], scale_bar: null,
      directions: { north_deg: -90, east_deg: 180 },
    });

    renderHistory();
    await waitFor(() => expect(screen.getByText("M42_stack_01")).toBeInTheDocument());
    openAbout();
    const item = await menuItem("Scale");
    expect(item).toHaveTextContent(/Scale & compass/);
    expect(item).toHaveTextContent(/which way is North/);
    fireEvent.click(item);
    await waitFor(() => expect(annot).toHaveBeenCalledWith("M_42", 1));
    // (The rose's on-image geometry needs a measured box — 0 in jsdom — so it is
    // covered by compassLayout's pure unit tests instead.)
  });

  it("copies a ready-to-post caption built from identity, run facts and scale", async () => {
    vi.spyOn(client.api, "listStackRuns").mockResolvedValue([
      // The date in the caption is the run's *capture* window, and the stack
      // stamp here is deliberately a different year: a caption that quotes when
      // the stack ran is the wrong-fact bug this pins.
      mkRun({ has_preview: true, n_frames_used: 240, total_exposure_s: 40 * 60,
        timestamp_utc: "2026-08-30T22:14:03",
        capture_night_start: "2026-07-20", capture_night_end: "2026-07-20" }),
    ]);
    vi.spyOn(client.api, "identifyTarget").mockResolvedValue(mkIdentity());
    vi.spyOn(client.api, "stackAnnotations").mockResolvedValue({
      width: 1000, height: 600, objects: [],
      scale_bar: {
        arcsec: 1800, label: "30′", fraction: 0.18, frame_arcmin: 166.6,
        moon_comparison: "the whole frame is about 5.4 full Moons wide",
      },
    });
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.assign(navigator, { clipboard: { writeText } });

    renderHistory();
    await waitFor(() => expect(screen.getByText("M42_stack_01")).toBeInTheDocument());
    openSaveShare();
    fireEvent.click(await menuItem("Copy caption"));

    await waitFor(() => expect(writeText).toHaveBeenCalledTimes(1));
    expect(writeText).toHaveBeenCalledWith(
      "Orion Nebula (M42), a nebula — a stack of 240 subs (40 min total), " +
        "shot on 20 Jul 2026 with a Seestar. " +
        "The whole frame is about 5.4 full Moons wide.",
    );
  });

  it("still copies an honest caption when the target isn't identified", async () => {
    vi.spyOn(client.api, "listStackRuns").mockResolvedValue([
      mkRun({ has_preview: true, has_fits: false, n_frames_used: 12,
        total_exposure_s: 5 * 60, timestamp_utc: "2026-09-01T03:00:00",
        capture_night_start: "2026-09-01", capture_night_end: "2026-09-01" }),
    ]);
    // identifyTarget defaults to null (unidentified) via beforeEach; no FITS →
    // no annotations fetch, so the caption drops the scale clause too.
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.assign(navigator, { clipboard: { writeText } });

    renderHistory();
    await waitFor(() => expect(screen.getByText("M42_stack_01")).toBeInTheDocument());
    openSaveShare();
    fireEvent.click(await menuItem("Copy caption"));

    await waitFor(() => expect(writeText).toHaveBeenCalledTimes(1));
    expect(writeText).toHaveBeenCalledWith(
      "M_42 — a stack of 12 subs (5 min total), shot on 1 Sep 2026 with a Seestar.",
    );
  });

  it("never dates the caption from the day the stack ran", async () => {
    // The owner's own case: subs from a 2024 back catalogue, stacked today. The
    // caption used to read the run stamp and publish it as the capture date.
    vi.spyOn(client.api, "listStackRuns").mockResolvedValue([
      mkRun({ has_preview: true, has_fits: false, n_frames_used: 300,
        total_exposure_s: 3600, timestamp_utc: "2026-08-30T12:00:00",
        capture_night_start: "2024-11-15", capture_night_end: "2024-11-18" }),
    ]);
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.assign(navigator, { clipboard: { writeText } });

    renderHistory();
    await waitFor(() => expect(screen.getByText("M42_stack_01")).toBeInTheDocument());
    openSaveShare();
    fireEvent.click(await menuItem("Copy caption"));

    await waitFor(() => expect(writeText).toHaveBeenCalledTimes(1));
    const caption = writeText.mock.calls[0][0] as string;
    expect(caption).toContain("shot between 15 and 18 Nov 2024 with a Seestar");
    expect(caption).not.toContain("2026");
  });

  it("says nothing about the date when the run has no capture window", async () => {
    // Every run made before the app recorded one. Dropping the clause is the
    // honest outcome; reaching for `timestamp_utc` is what went wrong.
    vi.spyOn(client.api, "listStackRuns").mockResolvedValue([
      mkRun({ has_preview: true, has_fits: false, n_frames_used: 12,
        total_exposure_s: 5 * 60, timestamp_utc: "2026-09-01T03:00:00" }),
    ]);
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.assign(navigator, { clipboard: { writeText } });

    renderHistory();
    await waitFor(() => expect(screen.getByText("M42_stack_01")).toBeInTheDocument());
    openSaveShare();
    fireEvent.click(await menuItem("Copy caption"));

    await waitFor(() => expect(writeText).toHaveBeenCalledTimes(1));
    expect(writeText).toHaveBeenCalledWith(
      "M_42 — a stack of 12 subs (5 min total), shot with a Seestar.",
    );
  });

  it("names an unidentified target the way the user does, not the way the URL does", async () => {
    // The same leak the share sheet had, one line further down: when the catalog
    // can't identify the object, the caption falls back to a name — and that
    // fallback was `safe`, the URL slug. A beginner shooting something the
    // catalog doesn't know copied "M 42 dim — …" as "M_42_dim — …" and pasted
    // the app's own underscore under their photo. (The test above keeps its
    // slug: there, no target has loaded, so the slug is genuinely all there is.)
    vi.spyOn(client.api, "getTarget").mockResolvedValue({
      safe_name: "M_42", name: "M 42 dim",
      ra_deg: null, dec_deg: null, n_frames: 12, n_frames_accepted: 12,
      total_exposure_s: 300, last_activity_utc: null, has_preview: true,
      notes: null, tags: [],
    } as client.Target);
    vi.spyOn(client.api, "listStackRuns").mockResolvedValue([
      mkRun({ has_preview: true, has_fits: false, n_frames_used: 12,
        total_exposure_s: 5 * 60 }),
    ]);
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.assign(navigator, { clipboard: { writeText } });

    renderHistory();
    await waitFor(() => expect(screen.getByText("M42_stack_01")).toBeInTheDocument());
    openSaveShare();
    fireEvent.click(await menuItem("Copy caption"));

    await waitFor(() => expect(writeText).toHaveBeenCalledTimes(1));
    const caption = writeText.mock.calls[0][0] as string;
    expect(caption).toContain("M 42 dim — a stack of 12 subs");
    expect(caption).not.toContain("M_42");
  });

  it("pins a run as the target's cover from a preview run", async () => {
    vi.spyOn(client.api, "listStackRuns").mockResolvedValue([mkRun({ has_preview: true })]);
    const setCover = vi.spyOn(client.api, "setTargetCover")
      .mockResolvedValue({} as never);

    renderHistory();
    await waitFor(() => expect(screen.getByText("M42_stack_01")).toBeInTheDocument());

    openAbout();
    fireEvent.click(await menuItem("Set as cover"));
    await waitFor(() => expect(setCover).toHaveBeenCalledWith("M_42", 1));
  });

  it("clears the cover when the current cover run's button is clicked", async () => {
    vi.spyOn(client.api, "listStackRuns")
      .mockResolvedValue([mkRun({ has_preview: true, is_cover: true })]);
    const setCover = vi.spyOn(client.api, "setTargetCover")
      .mockResolvedValue({} as never);

    renderHistory();
    await waitFor(() => expect(screen.getByText("M42_stack_01")).toBeInTheDocument());
    openAbout();
    // The pinned run shows the filled "Cover" affordance, not "Set as cover".
    const pinned = await menuItem("Cover");
    expect(screen.queryByRole("menuitem", { name: /^Set as cover/ })).not.toBeInTheDocument();

    fireEvent.click(pinned);
    await waitFor(() => expect(setCover).toHaveBeenCalledWith("M_42", null));
  });

  it("shows no cover button when a run has no preview to show", async () => {
    vi.spyOn(client.api, "listStackRuns").mockResolvedValue([mkRun({ has_preview: false })]);
    renderHistory();
    await waitFor(() => expect(screen.getByText("M42_stack_01")).toBeInTheDocument());
    openAbout();
    await menuItem("Info");
    expect(screen.queryByRole("menuitem", { name: /cover/i })).not.toBeInTheDocument();
  });

  it("offers PNG and JPEG downloads of the finished image when a preview exists", async () => {
    vi.spyOn(client.api, "listStackRuns").mockResolvedValue([mkRun({ has_preview: true })]);
    renderHistory();
    await waitFor(() => expect(screen.getByText("M42_stack_01")).toBeInTheDocument());
    openSaveShare();
    const png = await menuItem("PNG");
    expect(png).toHaveAttribute("href", "/api/targets/M_42/stack-runs/1/preview");
    const jpeg = await menuItem("JPEG");
    expect(jpeg).toHaveAttribute("href", "/api/targets/M_42/stack-runs/1/jpeg");
  });

  it("offers a full-resolution PNG download (native output size) when a FITS exists", async () => {
    vi.spyOn(client.api, "listStackRuns").mockResolvedValue([mkRun({ has_preview: true, has_fits: true })]);
    renderHistory();
    await waitFor(() => expect(screen.getByText("M42_stack_01")).toBeInTheDocument());
    openSaveShare();
    const full = await menuItem("Full-res PNG");
    expect(full).toHaveAttribute("href", "/api/targets/M_42/stack-runs/1/full-res-png");
    // Distinct from the small quick-preview PNG.
    const png = await menuItem("PNG");
    expect(png).toHaveAttribute("href", "/api/targets/M_42/stack-runs/1/preview");
  });

  it("tells the truth about what the full-res PNG contains", async () => {
    // This menu used to print the canvas dimensions beside the item — "Same
    // look, full size (12000×9000 px)" — on a download the server caps on its
    // long edge, so it quoted a number the file demonstrably misses.
    const w = FULL_RES_PNG_MAX_LONG_EDGE + 4000;
    vi.spyOn(client.api, "listStackRuns").mockResolvedValue([
      mkRun({ has_preview: true, has_fits: true, canvas_w: w, canvas_h: 9000 }),
    ]);
    renderHistory();
    await waitFor(() => expect(screen.getByText("M42_stack_01")).toBeInTheDocument());
    openSaveShare();
    await menuItem("Full-res PNG");
    expect(screen.queryByText(`Same look, full size (${w}×9000 px)`)).not.toBeInTheDocument();
    expect(screen.getByText(
      new RegExp(`up to ${FULL_RES_PNG_MAX_LONG_EDGE} px`))).toBeInTheDocument();
  });

  it("still quotes the exact size for a canvas the render does serve whole", async () => {
    vi.spyOn(client.api, "listStackRuns").mockResolvedValue([
      mkRun({ has_preview: true, has_fits: true, canvas_w: 1080, canvas_h: 1920 }),
    ]);
    renderHistory();
    await waitFor(() => expect(screen.getByText("M42_stack_01")).toBeInTheDocument());
    openSaveShare();
    await menuItem("Full-res PNG");
    expect(screen.getByText("Same look, full size (1080×1920 px)")).toBeInTheDocument();
  });

  it("warns that a plain stack's TIFF opens dark, and doesn't on an editor export", async () => {
    // The one download on this menu with nothing said about it, and the one most
    // likely to look broken: an ordinary stack's TIFF is linear.
    vi.spyOn(client.api, "listStackRuns").mockResolvedValue([
      mkRun({ has_preview: true, has_tiff: true, options: {} }),
    ]);
    renderHistory();
    await waitFor(() => expect(screen.getByText("M42_stack_01")).toBeInTheDocument());
    openSaveShare();
    await menuItem("TIFF");
    expect(screen.getByText(/opens dark until you stretch it/)).toBeInTheDocument();
  });

  it("calls an editor export's TIFF the finished picture, because it is", async () => {
    vi.spyOn(client.api, "listStackRuns").mockResolvedValue([
      mkRun({
        has_preview: true, has_tiff: true,
        options: { editor_recipe: { ops: [] }, display_space: true },
      }),
    ]);
    renderHistory();
    await waitFor(() => expect(screen.getByText("M42_stack_01")).toBeInTheDocument());
    openSaveShare();
    await menuItem("TIFF");
    expect(screen.getByText("16-bit — the finished picture, at full depth"))
      .toBeInTheDocument();
    expect(screen.queryByText(/opens dark/)).not.toBeInTheDocument();
  });

  it("does not offer a picture download when the run has no preview", async () => {
    vi.spyOn(client.api, "listStackRuns").mockResolvedValue([mkRun({ has_preview: false })]);
    renderHistory();
    await waitFor(() => expect(screen.getByText("M42_stack_01")).toBeInTheDocument());
    openSaveShare();
    // The FITS (raw-data) download is still offered.
    expect(await menuItem("FITS")).toBeInTheDocument();
    expect(screen.queryByRole("menuitem", { name: /^PNG/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("menuitem", { name: /^JPEG/ })).not.toBeInTheDocument();
  });

  it("keeps the run card to a handful of buttons, with the rest behind two menus", async () => {
    vi.spyOn(client.api, "listStackRuns")
      .mockResolvedValue([mkRun({ has_preview: true, has_fits: true, has_tiff: true, reusable: true })]);
    renderHistory();
    await waitFor(() => expect(screen.getByText("M42_stack_01")).toBeInTheDocument());

    // The job itself stays inline; every file/insight action is one tap away.
    expect(screen.getByRole("link", { name: "Edit" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Reuse settings" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Save / share" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "About this stack" })).toBeInTheDocument();
    // The fifteen that used to sit here as buttons no longer do.
    for (const collapsed of [
      "Info", "Identify", "Scale", "Adjust", "Set as cover", "PNG", "Full-res PNG",
      "JPEG", "Copy caption", "FITS", "TIFF", "Wallpaper", "To phone",
    ]) {
      expect(screen.queryByRole("button", { name: collapsed })).not.toBeInTheDocument();
      expect(screen.queryByRole("link", { name: collapsed })).not.toBeInTheDocument();
    }
  });

  it("keeps every save/share action, wallpapers included, inside the one menu", async () => {
    vi.spyOn(client.api, "listStackRuns")
      .mockResolvedValue([mkRun({ has_preview: true, has_fits: true, has_tiff: true })]);
    renderHistory();
    await waitFor(() => expect(screen.getByText("M42_stack_01")).toBeInTheDocument());

    openSaveShare();
    for (const item of ["PNG", "Full-res PNG", "JPEG", "FITS", "TIFF", "To phone", "Copy caption"]) {
      expect(await menuItem(item)).toBeInTheDocument();
    }
    // The wallpaper aspects come from WallpaperMenu's own items, not a copy.
    expect((await menuItem("Phone")).getAttribute("href"))
      .toBe(client.api.stackWallpaperUrl("M_42", 1, "phone"));
    expect(await menuItem("Desktop")).toBeInTheDocument();
    expect(await menuItem("Square")).toBeInTheDocument();
    // …and the zoom clip sits with the other share actions. jsdom has no
    // `URL.createObjectURL`, so what renders here is `DownloadMenuItem`'s
    // old-browser fallback — the plain `<a download>` this item has always been,
    // pinned so the progressive enhancement can never take the download away.
    // The spinner path a real browser takes is covered in
    // `components/DownloadMenuItem.test.tsx`.
    const clip = await menuItem("Zoom clip");
    expect(clip.getAttribute("href")).toBe(client.api.stackZoomClipUrl("M_42", 1));
    expect(clip.hasAttribute("download")).toBe(true);
  });

  it("offers no zoom clip for a run with no picture", async () => {
    // The whole Share section is gated on the run having a preview — there is
    // nothing for a camera to move over otherwise, and the endpoint would 404.
    vi.spyOn(client.api, "listStackRuns")
      .mockResolvedValue([mkRun({ has_preview: false, has_fits: true })]);
    renderHistory();
    await waitFor(() => expect(screen.getByText("M42_stack_01")).toBeInTheDocument());

    openSaveShare();
    expect(await menuItem("FITS")).toBeInTheDocument();
    expect(screen.queryByRole("menuitem", { name: /^Zoom clip/ })).toBeNull();
  });

  it("caps the save/share menu's height instead of letting it clip", async () => {
    // Measured in a real browser: twelve items with a line of help each is
    // taller than the space under a card halfway down a 900 px screen, and the
    // dropdown flipped upwards and lost its first item off the top. jsdom has no
    // layout, so pin the cause — the dropdown scrolls rather than growing.
    vi.spyOn(client.api, "listStackRuns")
      .mockResolvedValue([mkRun({ has_preview: true, has_fits: true, has_tiff: true })]);
    renderHistory();
    await waitFor(() => expect(screen.getByText("M42_stack_01")).toBeInTheDocument());

    openSaveShare();
    const dropdown = (await menuItem("PNG")).closest(".mantine-Menu-dropdown");
    expect(dropdown).not.toBeNull();
    expect((dropdown as HTMLElement).style.overflowY).toBe("auto");
    expect((dropdown as HTMLElement).style.maxHeight).not.toBe("");
  });

  it("ticks an About-menu toggle that is currently on", async () => {
    vi.spyOn(client.api, "listStackRuns").mockResolvedValue([mkRun()]);
    vi.spyOn(client.api, "stackRunInfo").mockResolvedValue({
      run_id: 1, integration_s: null, n_frames: 42, weighting: null, cards: [],
    });
    renderHistory();
    await waitFor(() => expect(screen.getByText("M42_stack_01")).toBeInTheDocument());

    // A menu hides the "filled button" affordance the old row used to show state
    // with, so an item that's on carries a tick instead.
    openAbout();
    expect((await menuItem("Info")).querySelector(".tabler-icon-check")).toBeNull();
    fireEvent.click(await menuItem("Info"));

    openAbout();
    expect((await menuItem("Info")).querySelector(".tabler-icon-check")).not.toBeNull();
  });

  it("opens the phone QR in a modal, so closing the menu doesn't take it away", async () => {
    vi.spyOn(client.api, "listStackRuns").mockResolvedValue([mkRun({ has_preview: true })]);
    renderHistory();
    await waitFor(() => expect(screen.getByText("M42_stack_01")).toBeInTheDocument());

    openSaveShare();
    fireEvent.click(await menuItem("To phone"));

    // The menu has closed behind it and the QR is still on screen.
    expect(await screen.findByRole("img", { name: /QR code/i })).toBeInTheDocument();
    await waitFor(() =>
      expect(screen.queryByRole("menuitem", { name: /^To phone/ })).not.toBeInTheDocument());
    expect(screen.getByRole("img", { name: /QR code/i })).toBeInTheDocument();
  });

  it("offers Compare linking to the previous run on all but the oldest card", async () => {
    vi.spyOn(client.api, "listStackRuns").mockResolvedValue([
      mkRun({ id: 3, output_basename: "newest_run" }),
      mkRun({ id: 2, output_basename: "middle_run" }),
      mkRun({ id: 1, output_basename: "oldest_run" }),
    ]);

    renderHistory();
    await waitFor(() => expect(screen.getByText("newest_run")).toBeInTheDocument());

    // The oldest run has no earlier run to compare against, so 2 of 3 cards
    // carry a Compare link, each pointing at the chronologically previous run.
    const links = screen.getAllByRole("link", { name: /Compare/ });
    expect(links).toHaveLength(2);
    const hrefs = links.map((l) => l.getAttribute("href"));
    expect(hrefs).toContain("/compare?a=M_42:3&b=M_42:2");
    expect(hrefs).toContain("/compare?a=M_42:2&b=M_42:1");
  });

  it("offers Reuse settings only for reusable runs", async () => {
    vi.spyOn(client.api, "listStackRuns").mockResolvedValue([
      mkRun({ id: 1, output_basename: "reusable_run", reusable: true }),
      mkRun({ id: 2, output_basename: "combine_run", reusable: false }),
    ]);

    renderHistory();
    await waitFor(() => expect(screen.getByText("reusable_run")).toBeInTheDocument());

    // Exactly one "Reuse settings" button (the reusable run) linking to the
    // Stack form with ?from=<runId>.
    const buttons = screen.getAllByRole("link", { name: /Reuse settings/ });
    expect(buttons).toHaveLength(1);
    expect(buttons[0]).toHaveAttribute("href", "/targets/M_42/stack?from=1");
  });

  it("edits a run's note and persists it via PATCH", async () => {
    vi.spyOn(client.api, "listStackRuns").mockResolvedValue([mkRun({ notes: null })]);
    const upd = vi.spyOn(client.api, "updateStackRunNotes")
      .mockResolvedValue({ id: 1, notes: "best RGB v2" });

    renderHistory();
    await waitFor(() => expect(screen.getByText("No label")).toBeInTheDocument());

    fireEvent.click(screen.getByRole("button", { name: "Edit note" }));
    fireEvent.change(screen.getByLabelText("Stack note"), { target: { value: "best RGB v2" } });
    fireEvent.click(screen.getByRole("button", { name: "Save note" }));

    await waitFor(() => expect(upd).toHaveBeenCalledWith("M_42", 1, "best RGB v2"));
  });

  it("shows an existing note as a quoted label", async () => {
    vi.spyOn(client.api, "listStackRuns").mockResolvedValue([mkRun({ notes: "cloudy" })]);
    renderHistory();
    await waitFor(() => expect(screen.getByText(/cloudy/)).toBeInTheDocument());
  });

  it("reorders cards cleanest-first when the sort is switched", async () => {
    vi.spyOn(client.api, "listStackRuns").mockResolvedValue([
      mkRun({ id: 1, output_basename: "noisy_run", noise_sigma: 0.05 }),
      mkRun({ id: 2, output_basename: "clean_run", noise_sigma: 0.01 }),
    ]);

    renderHistory();
    await waitFor(() => expect(screen.getByText("noisy_run")).toBeInTheDocument());

    // Default (newest) keeps API order: noisy_run first.
    let names = screen.getAllByText(/_run$/).map((n) => n.textContent);
    expect(names).toEqual(["noisy_run", "clean_run"]);

    fireEvent.click(screen.getByRole("radio", { name: "Cleanest" }));

    await waitFor(() => {
      names = screen.getAllByText(/_run$/).map((n) => n.textContent);
      expect(names).toEqual(["clean_run", "noisy_run"]);
    });
  });

  it("shows an error notification when deletion fails", async () => {
    vi.spyOn(client.api, "listStackRuns").mockResolvedValue([mkRun()]);
    vi.spyOn(client.api, "deleteStackRun").mockRejectedValue(new Error("stack is in use"));
    vi.spyOn(window, "confirm").mockReturnValue(true);

    renderHistory();
    await waitFor(() => expect(screen.getByText("M42_stack_01")).toBeInTheDocument());

    fireEvent.click(screen.getByRole("button", { name: "Delete stack" }));

    await waitFor(() => expect(screen.getByText("stack is in use")).toBeInTheDocument());
    // The run stays listed since the delete failed.
    expect(screen.getByText("M42_stack_01")).toBeInTheDocument();
  });
});

describe("sortRuns", () => {
  it("keeps API order for 'newest' and does not mutate the input", () => {
    const runs = [mkRun({ id: 1, noise_sigma: 0.05 }), mkRun({ id: 2, noise_sigma: 0.01 })];
    const out = sortRuns(runs, "newest");
    expect(out.map((r) => r.id)).toEqual([1, 2]);
    // input untouched
    expect(runs.map((r) => r.id)).toEqual([1, 2]);
  });

  it("orders by ascending noise for 'cleanest', with unmeasured runs kept last", () => {
    const runs = [
      mkRun({ id: 1, noise_sigma: 0.05 }),
      mkRun({ id: 2, noise_sigma: null }),
      mkRun({ id: 3, noise_sigma: 0.01 }),
      mkRun({ id: 4, noise_sigma: 0.03 }),
    ];
    const out = sortRuns(runs, "cleanest");
    expect(out.map((r) => r.id)).toEqual([3, 4, 1, 2]);
  });
});

describe("noiseDeltas", () => {
  it("compares each measured run against the previous measured stack (chronologically)", () => {
    // API order is timestamp-DESC (newest first). id 3 is newest, id 1 oldest.
    const runs = [
      mkRun({ id: 3, noise_sigma: 0.04 }),
      mkRun({ id: 2, noise_sigma: 0.05 }),
      mkRun({ id: 1, noise_sigma: 0.10 }),
    ];
    const d = noiseDeltas(runs);
    // id 1 is the first measured stack — no earlier run to compare against.
    expect(d.has(1)).toBe(false);
    // id 2: (0.05 - 0.10)/0.10 = -0.5 (halved the noise).
    expect(d.get(2)).toBeCloseTo(-0.5);
    // id 3: (0.04 - 0.05)/0.05 = -0.2.
    expect(d.get(3)).toBeCloseTo(-0.2);
  });

  it("skips runs with no measured σ and compares against the nearest earlier measured one", () => {
    const runs = [
      mkRun({ id: 4, noise_sigma: 0.02 }),
      mkRun({ id: 3, noise_sigma: null }),
      mkRun({ id: 2, noise_sigma: null }),
      mkRun({ id: 1, noise_sigma: 0.04 }),
    ];
    const d = noiseDeltas(runs);
    expect(d.has(1)).toBe(false);
    expect(d.has(2)).toBe(false);
    expect(d.has(3)).toBe(false);
    // id 4 compares against id 1 (the nearest earlier measured run).
    expect(d.get(4)).toBeCloseTo(-0.5);
  });

  it("guards against a zero baseline", () => {
    const runs = [mkRun({ id: 2, noise_sigma: 0.03 }), mkRun({ id: 1, noise_sigma: 0 })];
    // A prior σ of 0 would divide-by-zero, so no delta is produced.
    expect(noiseDeltas(runs).has(2)).toBe(false);
  });
});

describe("previousRunId", () => {
  it("returns the next-older run in a newest-first list", () => {
    const runs = [mkRun({ id: 3 }), mkRun({ id: 2 }), mkRun({ id: 1 })];
    expect(previousRunId(runs, 3)).toBe(2);
    expect(previousRunId(runs, 2)).toBe(1);
  });
  it("returns null for the oldest run and for an unknown id", () => {
    const runs = [mkRun({ id: 3 }), mkRun({ id: 1 })];
    expect(previousRunId(runs, 1)).toBeNull();
    expect(previousRunId(runs, 99)).toBeNull();
  });
});

describe("historyCompareHref", () => {
  it("builds a same-target /compare URL", () => {
    expect(historyCompareHref("M_42", 7, 3)).toBe("/compare?a=M_42:7&b=M_42:3");
  });
});

describe("noiseTrendSeries", () => {
  it("returns measured σ oldest→newest, skipping unmeasured runs", () => {
    // API order is newest-first; the series must come out chronological.
    const runs = [
      mkRun({ id: 3, noise_sigma: 0.02 }),
      mkRun({ id: 2, noise_sigma: null }),
      mkRun({ id: 1, noise_sigma: 0.05 }),
    ];
    expect(noiseTrendSeries(runs)).toEqual([0.05, 0.02]);
  });
  it("returns an empty series when nothing is measured", () => {
    expect(noiseTrendSeries([mkRun({ noise_sigma: null })])).toEqual([]);
  });
});

describe("combineMethodLabel", () => {
  it("translates each known STACKER method to plain language", () => {
    expect(combineMethodLabel([{ key: "STACKER", value: "mean" }]))
      .toMatch(/Plain mean/);
    expect(combineMethodLabel([{ key: "STACKER", value: "sigma-clip" }]))
      .toMatch(/κ-σ/);
    expect(combineMethodLabel([{ key: "STACKER", value: "min-max-reject" }]))
      .toMatch(/Min\/max/);
    expect(combineMethodLabel([{ key: "STACKER", value: "drizzle" }]))
      .toMatch(/Drizzle/);
  });
  it("is case-insensitive and trims", () => {
    expect(combineMethodLabel([{ key: "STACKER", value: " Sigma-Clip " }]))
      .toMatch(/κ-σ/);
  });
  it("returns null when STACKER is absent or unknown", () => {
    expect(combineMethodLabel([{ key: "OBJECT", value: "M42" }])).toBeNull();
    expect(combineMethodLabel([{ key: "STACKER", value: "quantum" }])).toBeNull();
    expect(combineMethodLabel([])).toBeNull();
  });
});

describe("calibrationSummaryText", () => {
  it("names the applied masters in plain language when CALSTAT is present", () => {
    const r = calibrationSummaryText([
      { key: "STACKER", value: "sigma-clip" },
      { key: "CALSTAT", value: "dark+flat" },
    ]);
    expect(r).toEqual({
      text: "Calibrated with your master dark and master flat.",
      calibrated: true,
    });
  });
  it("handles a single applied master", () => {
    expect(calibrationSummaryText([{ key: "CALSTAT", value: "flat" }]))
      .toEqual({ text: "Calibrated with your master flat.", calibrated: true });
  });
  it("tells the walk-away user when a stack that HAS provenance wasn't calibrated", () => {
    const r = calibrationSummaryText([{ key: "STACKER", value: "mean" }]);
    expect(r?.calibrated).toBe(false);
    expect(r?.text).toMatch(/No calibration masters were applied/);
    expect(r?.text).toMatch(/Calibration/);
  });
  it("says nothing when the stack carries no provenance at all", () => {
    expect(calibrationSummaryText([])).toBeNull();
  });
  it("shows the specific backend advice in place of the generic uncalibrated copy", () => {
    const advice =
      "You have a master dark taken at a different exposure (30s vs 10s) — " +
      "build a master bias and AstroStack will scale that dark to your subs automatically.";
    const r = calibrationSummaryText([{ key: "STACKER", value: "mean" }], advice);
    expect(r).toEqual({ text: advice, calibrated: false });
  });
  it("ignores advice when the stack IS calibrated (never replaces the positive line)", () => {
    const r = calibrationSummaryText(
      [{ key: "CALSTAT", value: "dark+flat" }],
      "You have a master dark taken at a different exposure — build a master bias.",
    );
    expect(r).toEqual({
      text: "Calibrated with your master dark and master flat.",
      calibrated: true,
    });
  });
  it("reports a saved calibration pick the run had to skip", () => {
    const skip =
      "Your saved master dark wasn't used: it's no longer in your calibration library.";
    const r = calibrationSummaryText([{ key: "STACKER", value: "mean" }], null, [skip]);
    expect(r?.calibrated).toBe(false);
    expect(r?.skipped).toBe(skip);
    // The status line still says what the picture *got*; the skip line says what
    // the user asked for and didn't get.
    expect(r?.text).toMatch(/No calibration masters were applied/);
  });
  it("reports a skipped pick even when the run IS calibrated by another master", () => {
    const skip =
      "Your saved master dark wasn't used: it's 1080×1920 pixels, but this " +
      "target's subs are 480×320.";
    const r = calibrationSummaryText([{ key: "CALSTAT", value: "flat" }], null, [skip]);
    expect(r).toEqual({
      text: "Calibrated with your master flat.",
      calibrated: true,
      skipped: skip,
    });
  });
  it("joins several skipped picks into one line and ignores blank entries", () => {
    const r = calibrationSummaryText([{ key: "STACKER", value: "mean" }], null, [
      "Your saved master dark wasn't used: it's no longer in your calibration library.",
      "   ",
      "Your saved master flat wasn't used: it couldn't be read from your calibration library.",
    ]);
    expect(r?.skipped).toBe(
      "Your saved master dark wasn't used: it's no longer in your calibration library. " +
        "Your saved master flat wasn't used: it couldn't be read from your calibration library.",
    );
  });
  it("leaves the skip line unset for a run that skipped nothing", () => {
    expect(calibrationSummaryText([{ key: "STACKER", value: "mean" }], null, [])?.skipped)
      .toBeUndefined();
    expect(calibrationSummaryText([{ key: "STACKER", value: "mean" }])?.skipped)
      .toBeUndefined();
  });
  it("reports a master that WAS applied but doesn't match the subs", () => {
    // The failure a calibrated-looking run hides best: the status line happily
    // says "Calibrated with your master dark", while a 30s dark's pedestal is
    // being over-subtracted out of every 10s sub.
    const warn = "Master dark is 30s but your subs are 10s — its pedestal will "
      + "be over-subtracted on every frame.";
    const r = calibrationSummaryText(
      [{ key: "CALSTAT", value: "dark" }], null, null, [warn]);
    expect(r).toEqual({
      text: "Calibrated with your master dark.",
      calibrated: true,
      mismatch: warn,
    });
  });
  it("joins several mismatches, ignores blanks, and stays unset when there are none", () => {
    const r = calibrationSummaryText([{ key: "CALSTAT", value: "dark" }], null, null, [
      "Master dark is 30s but your subs are 10s.",
      "  ",
      "Master dark was shot at -10°C but your subs are at 5°C.",
    ]);
    expect(r?.mismatch).toBe(
      "Master dark is 30s but your subs are 10s. "
      + "Master dark was shot at -10°C but your subs are at 5°C.",
    );
    expect(calibrationSummaryText([{ key: "CALSTAT", value: "dark" }], null, null, [])
      ?.mismatch).toBeUndefined();
    // An older backend omits the field entirely.
    expect(calibrationSummaryText([{ key: "CALSTAT", value: "dark" }])?.mismatch)
      .toBeUndefined();
  });
  it("keeps the skip and mismatch lines independent — they answer different questions", () => {
    const skip = "Your saved master flat wasn't used: it's no longer in your "
      + "calibration library.";
    const warn = "Master dark is 30s but your subs are 10s.";
    const r = calibrationSummaryText(
      [{ key: "CALSTAT", value: "dark" }], null, [skip], [warn]);
    expect(r?.skipped).toBe(skip);
    expect(r?.mismatch).toBe(warn);
  });
});

describe("HistoryView noise trend card", () => {
  it("shows a trend sparkline once at least two runs carry a measured σ", async () => {
    vi.spyOn(client.api, "listStackRuns").mockResolvedValue([
      mkRun({ id: 2, output_basename: "run_b", noise_sigma: 0.03 }),
      mkRun({ id: 1, output_basename: "run_a", noise_sigma: 0.05 }),
    ]);
    renderHistory();
    await waitFor(() =>
      expect(screen.getByLabelText(/Noise trend across 2 measured stacks/)).toBeInTheDocument());
    expect(screen.getByText("Noise trend")).toBeInTheDocument();
    // Latest σ (0.03) is below the first (0.05) → "Cleaner than" summary.
    expect(screen.getByText(/Cleaner than your first measured stack/)).toBeInTheDocument();
  });

  it("hides the trend card when only one run is measured", async () => {
    vi.spyOn(client.api, "listStackRuns").mockResolvedValue([
      mkRun({ id: 2, output_basename: "solo_measured", noise_sigma: 0.03 }),
      mkRun({ id: 1, output_basename: "unmeasured_run", noise_sigma: null }),
    ]);
    renderHistory();
    await waitFor(() => expect(screen.getByText("solo_measured")).toBeInTheDocument());
    expect(screen.queryByText("Noise trend")).not.toBeInTheDocument();
  });
});

describe("HistoryView noise delta", () => {
  it("shows the improvement readout on the newer stack", async () => {
    vi.spyOn(client.api, "listStackRuns").mockResolvedValue([
      mkRun({ id: 2, output_basename: "run_b", noise_sigma: 0.041 }),
      mkRun({ id: 1, output_basename: "run_a", noise_sigma: 0.05 }),
    ]);
    renderHistory();
    await waitFor(() =>
      expect(screen.getByText(/% noise vs your last stack/)).toBeInTheDocument());
    // 0.041 vs 0.05 = -18%.
    expect(screen.getByText(/-18% noise vs your last stack/)).toBeInTheDocument();
  });
});

describe("formatIntegration", () => {
  it("formats hours, minutes and seconds", () => {
    expect(formatIntegration(2520)).toBe("42 min");
    expect(formatIntegration(8280)).toBe("2.3 h");
    expect(formatIntegration(45)).toBe("45 s");
    expect(formatIntegration(0)).toBe("—");
    expect(formatIntegration(-5)).toBe("—");
    expect(formatIntegration(36000)).toBe("10 h");
  });
});

describe("formatEngineVersion", () => {
  it("prefixes a bare version with v", () => {
    expect(formatEngineVersion("0.75.0")).toBe("v0.75.0");
  });
  it("does not double-prefix an already-v-prefixed version", () => {
    expect(formatEngineVersion("v1.2.3")).toBe("v1.2.3");
  });
  it("returns empty for unknown/blank versions (pre-schema-9 runs)", () => {
    expect(formatEngineVersion(null)).toBe("");
    expect(formatEngineVersion(undefined)).toBe("");
    expect(formatEngineVersion("  ")).toBe("");
  });
});

describe("photometricSummaryText", () => {
  it("returns null when the run wasn't normalized", () => {
    expect(photometricSummaryText(null)).toBeNull();
    expect(photometricSummaryText(undefined)).toBeNull();
  });
  it("summarises frames gain-matched and the scale range", () => {
    expect(
      photometricSummaryText({ mode: "transparency", n_adjusted: 3, min: 0.7, max: 2.0, median: 1.05 }),
    ).toBe("Photometrically normalized · 3 frames gain-matched · scales 0.70–2.00 (median 1.05)");
  });
  it("singularises one frame and tolerates a missing scale range", () => {
    expect(photometricSummaryText({ mode: "transparency", n_adjusted: 1 })).toBe(
      "Photometrically normalized · 1 frame gain-matched",
    );
  });
  it("says when the mosaic path turned it on rather than the user", () => {
    expect(
      photometricSummaryText({ mode: "transparency", n_adjusted: 8, auto: true }),
    ).toBe("Photometrically normalized · 8 frames gain-matched · automatic for a mosaic");
    // The user's own choice reads exactly as it always has…
    expect(
      photometricSummaryText({ mode: "transparency", n_adjusted: 8, auto: false }),
    ).toBe("Photometrically normalized · 8 frames gain-matched");
    // …as does a master written before the flag existed.
    expect(photometricSummaryText({ mode: "transparency", n_adjusted: 8 })).toBe(
      "Photometrically normalized · 8 frames gain-matched",
    );
  });
  it("says a mosaic matched each panel against its own subs", () => {
    // Not against each other — which is what "gain-matched" on a mosaic would
    // otherwise sound like, and is exactly what the pass must never do.
    expect(
      photometricSummaryText({ mode: "transparency", n_adjusted: 6, auto: true, n_panels: 4 }),
    ).toBe(
      "Photometrically normalized · 6 frames gain-matched · " +
        "each of 4 panels matched against its own subs · automatic for a mosaic",
    );
  });
  it("says nothing about panels on a single-field run", () => {
    expect(
      photometricSummaryText({ mode: "transparency", n_adjusted: 2, n_panels: 0 }),
    ).toBe("Photometrically normalized · 2 frames gain-matched");
  });
});

describe("darkScalingSummaryText", () => {
  it("returns null when the run didn't scale its dark", () => {
    expect(darkScalingSummaryText(null)).toBeNull();
    expect(darkScalingSummaryText(undefined)).toBeNull();
  });
  it("names the two exposures the dark was scaled between", () => {
    expect(
      darkScalingSummaryText({ mode: "exposure", dark_exposure: 30, light_exposure: 10 }),
    ).toBe("Dark scaled to sub exposure · 30s → 10s");
  });
  it("keeps a fractional exposure to one decimal", () => {
    expect(
      darkScalingSummaryText({ mode: "exposure", dark_exposure: 30, light_exposure: 2.5 }),
    ).toBe("Dark scaled to sub exposure · 30s → 2.5s");
  });
  it("tolerates missing exposures (mode only)", () => {
    expect(darkScalingSummaryText({ mode: "exposure" })).toBe("Dark scaled to sub exposure");
  });
});

describe("drizzleDegradedNote", () => {
  it("says nothing on a run that fitted (the healthy case)", () => {
    expect(drizzleDegradedNote(null)).toBeNull();
    expect(drizzleDegradedNote(undefined)).toBeNull();
  });
  it("names both scales and reassures that nothing was dropped", () => {
    const s = drizzleDegradedNote({ reason: "memory", applied: 1.3, requested: 1.5 });
    expect(s).toContain("×1.3");
    expect(s).toContain("×1.5");
    expect(s).toContain("none of your subs were left out");
    // Never the user's fault, and never blames the picture quality.
    expect(s).toContain("slightly less zoomed-in");
  });
  it("still reads sensibly when the requested scale wasn't recorded", () => {
    const s = drizzleDegradedNote({ reason: "memory", applied: 1.25 });
    expect(s).toContain("×1.25");
    expect(s).not.toContain("instead of");
  });
  it("drops a nonsense or missing applied scale rather than inventing one", () => {
    expect(drizzleDegradedNote({ reason: "memory" })).toBeNull();
    expect(drizzleDegradedNote({ reason: "memory", applied: 0 })).toBeNull();
    expect(drizzleDegradedNote({ reason: "memory", applied: Number.NaN })).toBeNull();
  });
  it("omits the comparison when the recorded request isn't larger", () => {
    // Defensive: a bad/equal pair must not read "×1.5 instead of ×1.5".
    const s = drizzleDegradedNote({ reason: "memory", applied: 1.5, requested: 1.5 });
    expect(s).not.toContain("instead of");
  });
});

describe("See what stacking removed", () => {
  const withMap = {
    run_id: 1, integration_s: 2520, n_frames: 840, weighting: null, cards: [],
    rejection: { mode: "sigma-clip", fraction: 0.004, n_rejected: 40,
                 n_contributed: 10000, has_map: true },
  };

  it("offers the overlay only on a run that actually recorded one", async () => {
    // The offer rides the *listing* row, so a History page of runs without maps
    // costs no extra request at all.
    const info = vi.spyOn(client.api, "stackRunInfo").mockResolvedValue(withMap);
    vi.spyOn(client.api, "listStackRuns").mockResolvedValue([
      mkRun({ has_preview: true, has_rejection_map: false })]);
    renderHistory();
    await waitFor(() => expect(screen.getByText("M42_stack_01")).toBeInTheDocument());
    openAbout();
    // The Adjust item next to it is there, so the menu really did open.
    expect(await menuItem("Adjust")).toBeInTheDocument();
    expect(screen.queryByRole("menuitem", { name: /^Show what was removed/ })).toBeNull();
    expect(info).not.toHaveBeenCalled();
  });

  it("tints the picture and says what the tint is", async () => {
    vi.spyOn(client.api, "listStackRuns").mockResolvedValue([
      mkRun({ has_preview: true, has_rejection_map: true })]);
    vi.spyOn(client.api, "stackRunInfo").mockResolvedValue(withMap);
    renderHistory();
    await waitFor(() => expect(screen.getByText("M42_stack_01")).toBeInTheDocument());
    // Nothing is laid over the picture until the user asks for it.
    await waitFor(() =>
      expect(screen.getAllByRole("button", { name: "About this stack" }).length).toBeGreaterThan(0));
    expect(screen.queryByTestId("image-overlay")).toBeNull();

    openAbout();
    fireEvent.click(await menuItem("Show what was removed"));
    await waitFor(() => expect(screen.getByTestId("image-overlay")).toBeInTheDocument());
    expect(screen.getByTestId("image-overlay")).toHaveAttribute(
      "src", "/api/targets/M_42/stack-runs/1/rejection-overlay");
    // …and the caption that stops cyan speckle reading as damage.
    expect(screen.getByText(/what stacking removed/)).toBeInTheDocument();
  });

  it("keeps the tint on the picture when the view is turned North-up", async () => {
    // The one case that used to make the tint step aside: a processed run whose
    // stored bytes are being turned on the way out. The overlay endpoint takes
    // the same turn now, so both move together instead of the user being told
    // to untick the rotation to see what was removed.
    vi.spyOn(client.api, "listStackRuns").mockResolvedValue([
      mkRun({ has_fits: true, has_preview: true, has_rejection_map: true })]);
    vi.spyOn(client.api, "stackRunInfo").mockResolvedValue(withMap);
    vi.spyOn(client.api, "stackRenderSuggestion").mockResolvedValue({
      stretch: 0.5, black: 0.35, north_up_deg: 33.0,
      processed_preview: true, can_keep_processed: true,
    });

    renderHistory();
    await waitFor(() => expect(screen.getByText("M42_stack_01")).toBeInTheDocument());
    openAbout();
    fireEvent.click(await menuItem("Show what was removed"));
    await waitFor(() => expect(screen.getByTestId("image-overlay")).toBeInTheDocument());
    openAbout();
    fireEvent.click(await menuItem("Adjust"));
    fireEvent.click(await screen.findByText("Rotate so North is up"));

    // The picture is the stored bytes, turned; so is the tint over it.
    const img = () => screen.getByAltText("M42_stack_01").getAttribute("src") || "";
    await waitFor(() => expect(img()).toContain("/preview?north_up=true"));
    await waitFor(() => expect(screen.getByTestId("image-overlay")).toHaveAttribute(
      "src", "/api/targets/M_42/stack-runs/1/rejection-overlay?north_up=true"));
    expect(screen.queryByText(/Turn off .Rotate so North is up. to see what stacking removed/))
      .toBeNull();
  });
});

describe("removedOverlayCaption", () => {
  it("names the marks as protection delivered, not data thrown away", () => {
    const s = removedOverlayCaption({ mode: "sigma-clip", fraction: 0.004 });
    expect(s).toContain("satellite trails");
    expect(s).toContain("aren’t in your picture");
    expect(s).toContain("about 0.4% of your samples");
    expect(s).toContain("the rest is untouched");
  });
  it("says under 0.1% rather than a misleading 0.0%", () => {
    expect(removedOverlayCaption({ mode: "sigma-clip", fraction: 0.0003 }))
      .toContain("under 0.1%");
  });
  it("drops the fraction clause when there is no usable number", () => {
    for (const r of [undefined, null, { mode: "sigma-clip" },
                     { mode: "sigma-clip", fraction: 0 }]) {
      const s = removedOverlayCaption(r as never);
      expect(s).toContain("what stacking removed");
      expect(s).not.toContain("of your samples");
    }
  });
});

describe("rejectionSummaryText", () => {
  it("returns null when the run ran no rejection pass", () => {
    expect(rejectionSummaryText(null)).toBeNull();
    expect(rejectionSummaryText(undefined)).toBeNull();
  });
  it("reports a small fraction as transient outliers", () => {
    expect(
      rejectionSummaryText({ mode: "sigma-clip", fraction: 0.004, n_rejected: 40, n_contributed: 10000 }),
    ).toBe("Rejection clipped ~0.4% of samples (transient outliers)");
  });
  it("calls out a clean stack that clipped nothing", () => {
    expect(
      rejectionSummaryText({ mode: "sigma-clip", fraction: 0, n_rejected: 0, n_contributed: 500 }),
    ).toBe("Rejection clipped ~0% of samples (data was already clean)");
  });
  it("uses <0.1% for a tiny but nonzero fraction", () => {
    expect(
      rejectionSummaryText({ mode: "sigma-clip", fraction: 0.0003 }),
    ).toBe("Rejection clipped ~<0.1% of samples (transient outliers)");
  });
  it("flags an unusually high fraction as a possible too-tight κ", () => {
    const s = rejectionSummaryText({ mode: "sigma-clip", fraction: 0.15 });
    expect(s).toContain("~15% of samples");
    expect(s).toContain("check that κ isn't clipping real signal");
  });
  it("falls back to a plain label when the fraction is missing", () => {
    expect(rejectionSummaryText({ mode: "sigma-clip" })).toBe("Outlier rejection applied");
  });
  it("words min/max reject as a by-design extreme drop, with no κ caution", () => {
    // A structural fraction (2k/frames) — large at a short stack is by design,
    // so it must NOT show the "too-tight κ" over-clipping warning.
    expect(
      rejectionSummaryText({ mode: "min-max-reject", fraction: 0.5, n_rejected: 2, n_contributed: 4 }),
    ).toBe("Rejection dropped the ~50% most-extreme samples (min/max reject)");
    const small = rejectionSummaryText({ mode: "min-max-reject", fraction: 0.02 });
    expect(small).toBe("Rejection dropped the ~2.0% most-extreme samples (min/max reject)");
    expect(small).not.toContain("κ");
  });
  it("words drizzle-reject with the data-driven sigma-clip wording, not min/max's", () => {
    // Two-pass drizzle rejection is a genuine κ-σ clip (contributions outside
    // mean ± κ·σ), so its fraction is data-driven and reuses the sigma-clip
    // phrasing — a small share reads as transient outliers, a large one keeps
    // the too-tight-κ caution (unlike min/max's structural drop).
    expect(
      rejectionSummaryText({ mode: "drizzle-reject", fraction: 0.004, n_rejected: 40, n_contributed: 10000 }),
    ).toBe("Rejection clipped ~0.4% of samples (transient outliers)");
    const high = rejectionSummaryText({ mode: "drizzle-reject", fraction: 0.15 });
    expect(high).toContain("check that κ isn't clipping real signal");
  });
});

describe("weightingSummaryText", () => {
  it("returns null when weighting is off", () => {
    expect(weightingSummaryText(null)).toBeNull();
    expect(weightingSummaryText(undefined)).toBeNull();
  });
  it("names the down-weighted subs against the total, and reassures", () => {
    const s = weightingSummaryText(
      { mode: "quality", n_downweighted: 7 }, 840,
    );
    expect(s).toContain("of your 840 subs, 7 were softer or hazier");
    expect(s).toContain("not dropped — just weighted down");
    expect(s).toContain("Your best subs did the heavy lifting");
  });
  it("uses singular grammar for a single down-weighted sub", () => {
    const s = weightingSummaryText({ mode: "quality", n_downweighted: 1 }, 200);
    expect(s).toContain("of your 200 subs, 1 was softer");
    expect(s).toContain("trusted it a little less");
  });
  it("falls back to a bare count when the total is unknown", () => {
    expect(weightingSummaryText({ mode: "quality", n_downweighted: 3 })).toContain(
      "3 subs were softer or hazier",
    );
  });
  it("reassures consistency when nothing was down-weighted", () => {
    expect(weightingSummaryText({ mode: "quality", n_downweighted: 0 }, 500)).toBe(
      "Quality-weighted — your subs were consistent, so they all counted about equally.",
    );
    // Same reassurance when the count field is absent (older master).
    expect(weightingSummaryText({ mode: "quality" }, 500)).toContain(
      "your subs were consistent",
    );
  });
  it("formats large sub counts with thousands separators", () => {
    expect(weightingSummaryText({ mode: "quality", n_downweighted: 120 }, 2400)).toContain(
      "of your 2,400 subs, 120 were",
    );
  });
});

describe("weightingSkippedText", () => {
  it("returns null when nothing was skipped", () => {
    expect(weightingSkippedText(null)).toBeNull();
    expect(weightingSkippedText(undefined)).toBeNull();
  });
  it("explains an auto-picked min/max and when weighting comes back", () => {
    const s = weightingSkippedText({ reason: "minmax", auto: true, min_frames: 11 }, 6);
    expect(s).toContain("Quality weighting was on");
    expect(s).toContain("with 6 subs");
    expect(s).toContain("combines by rank instead of by weight");
    expect(s).toContain("from 11 subs");
    // An auto pick is not the user's mistake — don't tell them to change a setting.
    expect(s).not.toContain("Use sigma clipping instead");
  });
  it("tells a user who ticked min/max themselves how to get weighting back", () => {
    const s = weightingSkippedText({ reason: "minmax", auto: false }, 40);
    expect(s).toContain("with 40 subs");
    expect(s).toContain("Use sigma clipping instead");
    expect(s).not.toContain("picked automatically");
  });
  it("drops the sub count when it is unknown, and still explains", () => {
    const s = weightingSkippedText({ reason: "minmax", auto: false }, null);
    expect(s).toContain("this stack used min/max rejection");
    expect(s).not.toContain("with ");
  });
  it("copes with an auto pick whose crossover count is missing (older master)", () => {
    const s = weightingSkippedText({ reason: "minmax", auto: true }, 4);
    expect(s).toContain("picked automatically");
    expect(s).toContain("with more subs, weighting counts again");
  });
  it("formats large sub counts with thousands separators", () => {
    expect(weightingSkippedText({ reason: "minmax", auto: false }, 1200)).toContain(
      "with 1,200 subs",
    );
  });
});

describe("frameAccountingNote", () => {
  it("returns null when no accounting was recorded (older master)", () => {
    expect(frameAccountingNote(null)).toBeNull();
    expect(frameAccountingNote(undefined)).toBeNull();
    expect(frameAccountingNote({ n_offered: 0 })).toBeNull();
  });
  it("stays quiet when every attempted sub aligned", () => {
    // The "· N subs" integration line already tells the happy story, so there's
    // nothing to add.
    expect(frameAccountingNote({ n_offered: 2000, n_align_failed: 0 })).toBeNull();
    expect(frameAccountingNote({ n_offered: 2000 })).toBeNull();
  });
  it("reports a small align-failure count without a scary nudge", () => {
    const fa = frameAccountingNote({ n_offered: 2000, n_align_failed: 12 });
    expect(fa).not.toBeNull();
    expect(fa!.text).toBe("1,988 of 2,000 subs combined · 12 couldn't be aligned");
    expect(fa!.concern).toBe(false);
    expect(fa!.guidance).toBeNull();
  });
  it("guides a fix when a large share couldn't be aligned", () => {
    const fa = frameAccountingNote({ n_offered: 2000, n_align_failed: 840 });
    expect(fa!.text).toBe("1,160 of 2,000 subs combined · 840 couldn't be aligned");
    expect(fa!.concern).toBe(true);
    expect(fa!.guidance).toContain("two targets' frames");
    expect(fa!.guidance).toContain("Frames table");
  });
  it("doesn't nag on a tiny stack where one dud is a big fraction", () => {
    // 1 of 5 is 20%, but a 5-frame stack isn't worth a mixed-targets nudge.
    const fa = frameAccountingNote({ n_offered: 5, n_align_failed: 1 });
    expect(fa!.concern).toBe(false);
    expect(fa!.guidance).toBeNull();
  });
  it("clamps a failure count that exceeds the offered total", () => {
    const fa = frameAccountingNote({ n_offered: 10, n_align_failed: 99 });
    expect(fa!.text).toBe("0 of 10 subs combined · 10 couldn't be aligned");
  });
  it("names missing files as missing files, not as an alignment failure", () => {
    // A cleared Stage-1 cache over an offline share: sending this user to
    // re-solve frames or hunt for mixed targets wastes their evening.
    const fa = frameAccountingNote({
      n_offered: 500, n_align_failed: 142, n_unreadable: 142,
    });
    expect(fa!.text).toBe("358 of 500 subs combined · 142 couldn't be read");
    expect(fa!.concern).toBe(true);
    expect(fa!.guidance).toContain("weren't there");
    expect(fa!.guidance).toContain("offline");
    expect(fa!.guidance).not.toContain("Frames table");
  });
  it("reports both causes when the loss was mixed", () => {
    const fa = frameAccountingNote({
      n_offered: 500, n_align_failed: 150, n_unreadable: 40,
    });
    expect(fa!.text).toBe(
      "350 of 500 subs combined · 40 couldn't be read · 110 couldn't be aligned");
    // Alignment explains more of the loss here, so that's the fix to guide.
    expect(fa!.guidance).toContain("Frames table");
  });
  it("stays quiet about a stray unreadable sub in a big stack", () => {
    const fa = frameAccountingNote({
      n_offered: 2000, n_align_failed: 1, n_unreadable: 1,
    });
    expect(fa!.text).toBe("1,999 of 2,000 subs combined · 1 couldn't be read");
    expect(fa!.concern).toBe(false);
    expect(fa!.guidance).toBeNull();
  });
  it("clamps an unreadable count that exceeds the failures", () => {
    const fa = frameAccountingNote({
      n_offered: 100, n_align_failed: 5, n_unreadable: 80,
    });
    expect(fa!.text).toBe("95 of 100 subs combined · 5 couldn't be read");
  });
});

describe("readErrorNote", () => {
  it("returns null when nothing hit a read error", () => {
    expect(readErrorNote(null)).toBeNull();
    expect(readErrorNote(undefined)).toBeNull();
    // Healthy run → stamped 0 → nothing to say.
    expect(readErrorNote({ n_offered: 2000, n_read_errors: 0 })).toBeNull();
    // Master stacked before the tally existed → the card is simply absent.
    expect(readErrorNote({ n_offered: 2000 })).toBeNull();
    expect(readErrorNote({ n_offered: 0, n_read_errors: 4 })).toBeNull();
  });
  it("reports a blip that fully recovered without a scary nudge", () => {
    const re = readErrorNote({
      n_offered: 500, n_read_errors: 2, n_read_recovered: 2,
    });
    expect(re!.text).toBe(
      "2 of 500 subs hit a read error · all of them read fine on the second try");
    expect(re!.concern).toBe(false);
    expect(re!.guidance).toBeNull();
  });
  it("names the partial recovery so the owner knows what's actually lost", () => {
    const re = readErrorNote({
      n_offered: 500, n_read_errors: 40, n_read_recovered: 12,
    });
    expect(re!.text).toBe(
      "40 of 500 subs hit a read error · 12 read fine on the second try");
    expect(re!.concern).toBe(true);
    expect(re!.guidance).toContain("network share");
  });
  it("guides a fix when subs were genuinely lost to bad reads", () => {
    const re = readErrorNote({ n_offered: 200, n_read_errors: 40 });
    expect(re!.text).toBe("40 of 200 subs hit a read error");
    expect(re!.concern).toBe(true);
    expect(re!.guidance).toContain("stack again");
  });
  it("doesn't nag on a tiny stack where one bad read is a big fraction", () => {
    const re = readErrorNote({ n_offered: 5, n_read_errors: 1 });
    expect(re!.concern).toBe(false);
    expect(re!.guidance).toBeNull();
  });
  it("clamps counts that exceed what they're a subset of", () => {
    const re = readErrorNote({
      n_offered: 10, n_read_errors: 99, n_read_recovered: 99,
    });
    expect(re!.text).toBe(
      "10 of 10 subs hit a read error · all of them read fine on the second try");
    // Fully recovered → nothing was lost → no nudge, however big the share.
    expect(re!.concern).toBe(false);
  });
});

describe("roughlyAlignedNote", () => {
  it("returns null when no refine accounting was recorded", () => {
    expect(roughlyAlignedNote(null)).toBeNull();
    expect(roughlyAlignedNote(undefined)).toBeNull();
    // Refine ran but nothing was rough → stamped 0 → still nothing to say.
    expect(roughlyAlignedNote({ n_offered: 2000, n_roughly_aligned: 0 })).toBeNull();
    // Refine off → the field is simply absent.
    expect(roughlyAlignedNote({ n_offered: 2000 })).toBeNull();
  });
  it("reports a small roughly-aligned share without a scary nudge", () => {
    const ra = roughlyAlignedNote({ n_offered: 2000, n_roughly_aligned: 8 });
    expect(ra).not.toBeNull();
    expect(ra!.text).toBe(
      "8 of 2,000 subs were only roughly aligned · your stars may look a little soft");
    expect(ra!.concern).toBe(false);
    expect(ra!.guidance).toBeNull();
  });
  it("guides a fix when a large share only roughly aligned", () => {
    const ra = roughlyAlignedNote({ n_offered: 200, n_roughly_aligned: 90 });
    expect(ra!.text).toBe(
      "90 of 200 subs were only roughly aligned · your stars may look a little soft");
    expect(ra!.concern).toBe(true);
    expect(ra!.guidance).toContain("steadier");
    expect(ra!.guidance).toContain("re-solving");
  });
  it("doesn't nag on a tiny stack where one soft sub is a big fraction", () => {
    const ra = roughlyAlignedNote({ n_offered: 5, n_roughly_aligned: 2 });
    expect(ra!.concern).toBe(false);
    expect(ra!.guidance).toBeNull();
  });
  it("clamps a rough count that exceeds the offered total", () => {
    const ra = roughlyAlignedNote({ n_offered: 10, n_roughly_aligned: 99 });
    expect(ra!.text).toBe(
      "10 of 10 subs were only roughly aligned · your stars may look a little soft");
  });
});

describe("HistoryView panel-seam chip", () => {
  it("puts a mosaic's panel-flatness verdict on the run card", async () => {
    // Panel flatness is the third axis of "did my new stack get better?" for
    // anyone shooting mosaics — and the one they can't judge from a thumbnail.
    vi.spyOn(client.api, "listStackRuns")
      .mockResolvedValue([mkRun({ seam_verdict: "check" })]);
    renderHistory();
    await waitFor(() => expect(screen.getByText("M42_stack_01")).toBeInTheDocument());
    expect(screen.getByText("Panels: check")).toBeInTheDocument();
  });

  it("shows no seam chip at all on an ordinary single-field stack", async () => {
    // Every non-mosaic run and every run made before the measurement existed
    // serves no verdict, so the card must look exactly as it always did.
    vi.spyOn(client.api, "listStackRuns").mockResolvedValue([mkRun()]);
    renderHistory();
    await waitFor(() => expect(screen.getByText("M42_stack_01")).toBeInTheDocument());
    expect(screen.queryByText(/Panels/)).not.toBeInTheDocument();
  });
});

describe("HistoryView frame accounting", () => {
  it("surfaces a large align-failure fraction with guidance in the Info panel", async () => {
    vi.spyOn(client.api, "listStackRuns").mockResolvedValue([mkRun()]);
    vi.spyOn(client.api, "stackRunInfo").mockResolvedValue({
      run_id: 1, integration_s: 2520, n_frames: 1160, weighting: null,
      frame_accounting: { n_offered: 2000, n_align_failed: 840 },
      cards: [{ key: "STACKER", value: "sigma-clip", comment: "stacking method" }],
    });

    renderHistory();
    await waitFor(() => expect(screen.getByText("M42_stack_01")).toBeInTheDocument());
    openAbout();
    fireEvent.click(await menuItem("Info"));

    await waitFor(() =>
      expect(screen.getByText(/1,160 of 2,000 subs combined/)).toBeInTheDocument());
    expect(screen.getByText(/Open the Frames table/)).toBeInTheDocument();
  });

  it("surfaces a roughly-aligned share in the Info panel", async () => {
    vi.spyOn(client.api, "listStackRuns").mockResolvedValue([mkRun()]);
    vi.spyOn(client.api, "stackRunInfo").mockResolvedValue({
      run_id: 1, integration_s: 2520, n_frames: 2000, weighting: null,
      frame_accounting: { n_offered: 2000, n_align_failed: 0, n_roughly_aligned: 90 },
      cards: [{ key: "STACKER", value: "sigma-clip", comment: "stacking method" }],
    });

    renderHistory();
    await waitFor(() => expect(screen.getByText("M42_stack_01")).toBeInTheDocument());
    openAbout();
    fireEvent.click(await menuItem("Info"));

    await waitFor(() =>
      expect(screen.getByText(/90 of 2,000 subs were only roughly aligned/))
        .toBeInTheDocument());
  });
});

describe("HistoryView provenance", () => {
  it("shows the producing app version on the run card", async () => {
    vi.spyOn(client.api, "listStackRuns").mockResolvedValue([
      mkRun({ engine_version: "0.75.0" }),
    ]);
    renderHistory();
    await waitFor(() => expect(screen.getByText("M42_stack_01")).toBeInTheDocument());
    expect(screen.getByText(/v0\.75\.0/)).toBeInTheDocument();
  });

  it("omits the version for a legacy run that never recorded one", async () => {
    vi.spyOn(client.api, "listStackRuns").mockResolvedValue([
      mkRun({ engine_version: null }),
    ]);
    renderHistory();
    await waitFor(() => expect(screen.getByText("M42_stack_01")).toBeInTheDocument());
    expect(screen.queryByText(/·\s*v\d/)).toBeNull();
  });
});

describe("HistoryView adjustable render", () => {
  it("anchors the Adjust sliders to the run's own data suggestion", async () => {
    vi.spyOn(client.api, "listStackRuns").mockResolvedValue([
      mkRun({ has_fits: true, has_preview: true }),
    ]);
    const sug = vi.spyOn(client.api, "stackRenderSuggestion").mockResolvedValue({
      stretch: 0.72, black: 0.28, target_bg: 0.1,
    });

    renderHistory();
    await waitFor(() => expect(screen.getByText("M42_stack_01")).toBeInTheDocument());
    openAbout();
    fireEvent.click(await menuItem("Adjust"));

    await waitFor(() => expect(sug).toHaveBeenCalledWith("M_42", 1));
    // The sliders show the data-driven values, not the fixed 0.50 / 0.35 defaults.
    await waitFor(() => expect(screen.getByText("0.72")).toBeInTheDocument());
    expect(screen.getByText("0.28")).toBeInTheDocument();
  });

  it("falls back to the fixed defaults when there's no useful suggestion", async () => {
    vi.spyOn(client.api, "listStackRuns").mockResolvedValue([
      mkRun({ has_fits: true, has_preview: true }),
    ]);
    vi.spyOn(client.api, "stackRenderSuggestion").mockResolvedValue({
      stretch: null, black: null,
    });

    renderHistory();
    await waitFor(() => expect(screen.getByText("M42_stack_01")).toBeInTheDocument());
    openAbout();
    fireEvent.click(await menuItem("Adjust"));

    await waitFor(() => expect(screen.getByText("0.50")).toBeInTheDocument());
    expect(screen.getByText("0.35")).toBeInTheDocument();
  });

  it("offers the North-up toggle only when the run's WCS yields a correction", async () => {
    vi.spyOn(client.api, "listStackRuns").mockResolvedValue([
      mkRun({ has_fits: true, has_preview: true }),
    ]);
    vi.spyOn(client.api, "stackRenderSuggestion").mockResolvedValue({
      stretch: 0.5, black: 0.35, north_up_deg: 33.0,
    });

    renderHistory();
    await waitFor(() => expect(screen.getByText("M42_stack_01")).toBeInTheDocument());
    openAbout();
    fireEvent.click(await menuItem("Adjust"));

    // The toggle appears; ticking it threads north_up into the render image.
    const toggle = await screen.findByText("Rotate so North is up");
    fireEvent.click(toggle);
    await waitFor(() => {
      const rotated = Array.from(document.querySelectorAll("img")).some(
        (img) => (img.getAttribute("src") || "").includes("north_up=true"));
      expect(rotated).toBe(true);
    });

    // ...and the shared/downloaded JPEG link now carries north_up too, so the
    // picture the beginner posts is oriented like reference photos.
    openSaveShare();
    expect((await menuItem("JPEG")).getAttribute("href")).toContain("north_up=true");
  });

  it("hides the North-up toggle when the run has no orientation correction", async () => {
    vi.spyOn(client.api, "listStackRuns").mockResolvedValue([
      mkRun({ has_fits: true, has_preview: true }),
    ]);
    vi.spyOn(client.api, "stackRenderSuggestion").mockResolvedValue({
      stretch: 0.5, black: 0.35, north_up_deg: null,
    });

    renderHistory();
    await waitFor(() => expect(screen.getByText("M42_stack_01")).toBeInTheDocument());
    openAbout();
    fireEvent.click(await menuItem("Adjust"));
    await waitFor(() => expect(screen.getByText("0.50")).toBeInTheDocument());
    expect(screen.queryByLabelText("Rotate so North is up")).not.toBeInTheDocument();
  });

  it("warns before Save throws away a processed picture, and offers to keep it", async () => {
    vi.spyOn(client.api, "listStackRuns").mockResolvedValue([
      mkRun({ has_fits: true, has_preview: true }),
    ]);
    vi.spyOn(client.api, "stackRenderSuggestion").mockResolvedValue({
      stretch: null, black: null, north_up_deg: 33.0,
      processed_preview: true, can_keep_processed: true,
    });
    const save = vi.spyOn(client.api, "saveStackPreview")
      .mockResolvedValue({ ok: true });

    renderHistory();
    await waitFor(() => expect(screen.getByText("M42_stack_01")).toBeInTheDocument());
    openAbout();
    fireEvent.click(await menuItem("Adjust"));

    expect(await screen.findByText(/This picture was processed for you/))
      .toBeInTheDocument();
    // Rotate, then keep — the whole point: the turn shouldn't cost the picture.
    fireEvent.click(await screen.findByText("Rotate so North is up"));
    fireEvent.click(await screen.findByText("Keep the processed picture"));
    await waitFor(() => expect(save).toHaveBeenCalledWith(
      "M_42", 1, expect.any(Number), expect.any(Number), true, true));
  });

  it("still saves a plain stretch when the user asks for one", async () => {
    vi.spyOn(client.api, "listStackRuns").mockResolvedValue([
      mkRun({ has_fits: true, has_preview: true }),
    ]);
    vi.spyOn(client.api, "stackRenderSuggestion").mockResolvedValue({
      stretch: null, black: null, processed_preview: true, can_keep_processed: true,
    });
    const save = vi.spyOn(client.api, "saveStackPreview")
      .mockResolvedValue({ ok: true });

    renderHistory();
    await waitFor(() => expect(screen.getByText("M42_stack_01")).toBeInTheDocument());
    openAbout();
    fireEvent.click(await menuItem("Adjust"));
    fireEvent.click(await screen.findByText("Save as preview"));
    await waitFor(() => expect(save).toHaveBeenCalledWith(
      "M_42", 1, expect.any(Number), expect.any(Number), false, false));
  });

  it("warns without offering a rescue when the run's recipe is gone", async () => {
    vi.spyOn(client.api, "listStackRuns").mockResolvedValue([
      mkRun({ has_fits: true, has_preview: true }),
    ]);
    vi.spyOn(client.api, "stackRenderSuggestion").mockResolvedValue({
      stretch: null, black: null, processed_preview: true, can_keep_processed: false,
    });

    renderHistory();
    await waitFor(() => expect(screen.getByText("M42_stack_01")).toBeInTheDocument());
    openAbout();
    fireEvent.click(await menuItem("Adjust"));
    expect(await screen.findByText(/re-open it in the editor/)).toBeInTheDocument();
    expect(screen.queryByText("Keep the processed picture")).toBeNull();
  });

  it("says nothing about processing on an ordinary linear run", async () => {
    vi.spyOn(client.api, "listStackRuns").mockResolvedValue([
      mkRun({ has_fits: true, has_preview: true }),
    ]);
    vi.spyOn(client.api, "stackRenderSuggestion").mockResolvedValue({
      stretch: 0.5, black: 0.35,
    });

    renderHistory();
    await waitFor(() => expect(screen.getByText("M42_stack_01")).toBeInTheDocument());
    openAbout();
    fireEvent.click(await menuItem("Adjust"));
    await waitFor(() => expect(screen.getByText("0.50")).toBeInTheDocument());
    expect(screen.queryByText(/This picture was processed for you/)).toBeNull();
    expect(screen.queryByText("Keep the processed picture")).toBeNull();
  });

  it("keeps a processed picture on screen until a slider is actually moved", async () => {
    vi.spyOn(client.api, "listStackRuns").mockResolvedValue([
      mkRun({ has_fits: true, has_preview: true }),
    ]);
    vi.spyOn(client.api, "stackRenderSuggestion").mockResolvedValue({
      stretch: 0.5, black: 0.35,
      processed_preview: true, can_keep_processed: true,
    });

    renderHistory();
    await waitFor(() => expect(screen.getByText("M42_stack_01")).toBeInTheDocument());
    openAbout();
    fireEvent.click(await menuItem("Adjust"));
    // The panel is open (its warning is up) — and the picture is still the
    // processed one "Keep the processed picture" would save, not a live render
    // of the raw stack that neither button writes.
    expect(await screen.findByText(/This picture was processed for you/))
      .toBeInTheDocument();
    const src = () => screen.getByAltText("M42_stack_01").getAttribute("src") || "";
    expect(src()).toContain("/stack-runs/1/preview");
    expect(src()).not.toContain("/render?");

    // Move a slider and the panel switches to the live render — which is now
    // exactly what "Save as preview" would write.
    fireEvent.keyDown(screen.getAllByRole("slider")[0], { key: "ArrowRight" });
    await waitFor(() => expect(src()).toContain("/render?"));
  });

  it("previews the North-up turn on the processed picture itself", async () => {
    vi.spyOn(client.api, "listStackRuns").mockResolvedValue([
      mkRun({ has_fits: true, has_preview: true }),
    ]);
    vi.spyOn(client.api, "stackRenderSuggestion").mockResolvedValue({
      stretch: 0.5, black: 0.35, north_up_deg: 33.0,
      processed_preview: true, can_keep_processed: true,
    });

    renderHistory();
    await waitFor(() => expect(screen.getByText("M42_stack_01")).toBeInTheDocument());
    openAbout();
    fireEvent.click(await menuItem("Adjust"));
    fireEvent.click(await screen.findByText("Rotate so North is up"));

    // The turn is shown on the *stored* bytes (rotated server-side on the way
    // out), so the rotation preview doesn't cost the processed look.
    const src = () => screen.getByAltText("M42_stack_01").getAttribute("src") || "";
    await waitFor(() => expect(src()).toContain("/preview?north_up=true"));
    expect(src()).not.toContain("/render");
  });

  it("still renders live from the master on an ordinary linear run", async () => {
    vi.spyOn(client.api, "listStackRuns").mockResolvedValue([
      mkRun({ has_fits: true, has_preview: true }),
    ]);
    vi.spyOn(client.api, "stackRenderSuggestion").mockResolvedValue({
      stretch: 0.5, black: 0.35,
    });

    renderHistory();
    await waitFor(() => expect(screen.getByText("M42_stack_01")).toBeInTheDocument());
    openAbout();
    fireEvent.click(await menuItem("Adjust"));
    // No slider touched, but nothing is being kept here — the sliders *are* what
    // Save writes, so the picture follows them from the moment the panel opens.
    const src = () => screen.getByAltText("M42_stack_01").getAttribute("src") || "";
    await waitFor(() => expect(src()).toContain("/render?"));
  });

  it("ends the sample tour here — where a beginner's finished pictures live", async () => {
    localStorage.clear();
    vi.spyOn(client.api, "listStackRuns").mockResolvedValue([mkRun()]);
    vi.spyOn(client.api, "getSampleStatus").mockResolvedValue({
      loaded: true, safe: "M_42", n_frames: 6,
    } as client.SampleStatus);
    renderHistory();
    expect(await screen.findByText(SAMPLE_TOUR_COPY.history.title)).toBeInTheDocument();
  });

  it("says nothing about the tour on a real target, even with the sample loaded", async () => {
    localStorage.clear();
    vi.spyOn(client.api, "listStackRuns").mockResolvedValue([mkRun()]);
    const sample = vi.spyOn(client.api, "getSampleStatus").mockResolvedValue({
      loaded: true, safe: "Sample__Orion_Nebula__M42_", n_frames: 6,
    } as client.SampleStatus);
    renderHistory();
    await waitFor(() => expect(sample).toHaveBeenCalled());
    expect(screen.queryByText(SAMPLE_TOUR_COPY.history.title)).not.toBeInTheDocument();
  });
});

// The History card's thumbnail is the same baked preview the Target hero shows,
// so it needs the same honesty about an edit that was saved but never exported.
describe("HistoryView — an edit saved but never exported", () => {
  it("labels the run whose picture doesn't include the saved edit", async () => {
    vi.spyOn(client.api, "listStackRuns").mockResolvedValue([
      mkRun({ unexported_edit: true }),
    ]);
    renderHistory();
    await waitFor(() => expect(screen.getByText("M42_stack_01")).toBeInTheDocument());
    expect(screen.getByText("edit not exported")).toBeInTheDocument();
  });

  it("says nothing on an ordinary run", async () => {
    vi.spyOn(client.api, "listStackRuns").mockResolvedValue([mkRun()]);
    renderHistory();
    await waitFor(() => expect(screen.getByText("M42_stack_01")).toBeInTheDocument());
    expect(screen.queryByText("edit not exported")).not.toBeInTheDocument();
  });
});

describe("HistoryView heading", () => {
  // Same gap the editor had: the two screens you reach *from* the Target page
  // titled themselves with the raw filesystem-safe name while the Target and
  // Stack screens named the target properly.
  it("names the target the way every other screen does", async () => {
    vi.spyOn(client.api, "listStackRuns").mockResolvedValue([mkRun()]);
    vi.spyOn(client.api, "getTarget").mockResolvedValue({
      safe_name: "M_42", name: "Sample: Orion Nebula (M42)",
      ra_deg: null, dec_deg: null, n_frames: 6, n_frames_accepted: 6,
      total_exposure_s: 60, last_activity_utc: null, has_preview: true,
      notes: null, tags: [],
    });

    renderHistory();
    expect(await screen.findByText("Stack history — Sample: Orion Nebula (M42)"))
      .toBeInTheDocument();
    expect(screen.queryByText("Stack history — M_42")).not.toBeInTheDocument();
  });

  it("falls back to the safe name when the target can't be loaded", async () => {
    vi.spyOn(client.api, "listStackRuns").mockResolvedValue([mkRun()]);
    vi.spyOn(client.api, "getTarget").mockRejectedValue(new Error("gone"));

    renderHistory();
    expect(await screen.findByText("Stack history — M_42")).toBeInTheDocument();
  });
});

describe("HistoryView — what a shared picture is called", () => {
  // The same class as the heading above, one layer further out: History shared a
  // run under `output_basename` — a *filename* — so a picture posted to a group
  // chat arrived titled "M42_stack_01" and saved as `m42-stack-01.jpg`, while
  // the identical run shared from Gallery or Best pictures went out as "M 42".
  function stubShare(share: (d?: ShareData) => Promise<void>) {
    const nav = navigator as unknown as Record<string, unknown>;
    nav.canShare = () => true;
    nav.share = share;
    vi.stubGlobal("fetch", vi.fn(async () => ({
      ok: true,
      blob: async () => new Blob([new Uint8Array([1])], { type: "image/jpeg" }),
    })));
    return () => { delete nav.canShare; delete nav.share; };
  }

  function stubTarget(name: string) {
    vi.spyOn(client.api, "getTarget").mockResolvedValue({
      safe_name: "M_42", name,
      ra_deg: null, dec_deg: null, n_frames: 6, n_frames_accepted: 6,
      total_exposure_s: 60, last_activity_utc: null, has_preview: true,
      notes: null, tags: [],
    });
  }

  it("shares the target's display name, not the stack's filename", async () => {
    const share = vi.fn(async (_d?: ShareData) => {});
    const restore = stubShare(share);
    vi.spyOn(client.api, "listStackRuns").mockResolvedValue([
      mkRun({ has_preview: true, capture_night_start: "2024-11-15",
              capture_night_end: "2024-11-15" }),
    ]);
    stubTarget("M 42");

    renderHistory();
    await waitFor(() => expect(screen.getByText("M42_stack_01")).toBeInTheDocument());
    openSaveShare();
    fireEvent.click(await screen.findByRole("menuitem", { name: "Share picture" }));

    await waitFor(() => expect(share).toHaveBeenCalledTimes(1));
    const data = share.mock.calls[0][0] as ShareData;
    expect(data.title).toBe("M 42 · 15 Nov 2024");
    expect(data.files?.[0].name).toBe("m-42.jpg");
    // The card still *heads* itself with the basename — that is how you tell one
    // of a target's stacks from another in here. Only what leaves the app changed.
    expect(screen.getByText("M42_stack_01")).toBeInTheDocument();
    restore();
  });

  it("falls back to the URL slug when the target can't be loaded", async () => {
    const share = vi.fn(async (_d?: ShareData) => {});
    const restore = stubShare(share);
    vi.spyOn(client.api, "listStackRuns")
      .mockResolvedValue([mkRun({ has_preview: true })]);
    vi.spyOn(client.api, "getTarget").mockRejectedValue(new Error("gone"));

    renderHistory();
    await waitFor(() => expect(screen.getByText("M42_stack_01")).toBeInTheDocument());
    openSaveShare();
    fireEvent.click(await screen.findByRole("menuitem", { name: "Share picture" }));

    await waitFor(() => expect(share).toHaveBeenCalledTimes(1));
    const data = share.mock.calls[0][0] as ShareData;
    expect(data.title).toBe("M_42");
    expect(data.files?.[0].name).toBe("m-42.jpg");
    restore();
  });
});

describe("HistoryView — the run's two dates, each labelled", () => {
  it("says both when the run knows when its subs were shot", async () => {
    // This row's stamp is *which run* it is; the capture window is what the
    // picture is of. On a re-stack of a back catalogue they are years apart, and
    // the raw `2026-08-30T22:14:03` this replaces read as the latter.
    vi.spyOn(client.api, "listStackRuns").mockResolvedValue([
      mkRun({ timestamp_utc: "2026-08-30T22:14:03",
        capture_night_start: "2024-11-15", capture_night_end: "2024-11-18" }),
    ]);
    renderHistory();
    const line = await screen.findByText(/Shot 15–18 Nov 2024/);
    expect(line).toHaveTextContent(/Stacked/);
    expect(line.textContent).not.toMatch(/2026-08-30T/);
  });

  it("keeps the clock time, so two re-stacks in one afternoon stay apart", async () => {
    // `output_basename` is reused across a re-stack, so the stamp is the only
    // thing separating these two rows — the date alone would collapse them.
    vi.spyOn(client.api, "listStackRuns").mockResolvedValue([
      mkRun({ id: 1, timestamp_utc: "2026-08-30T14:05:00" }),
      mkRun({ id: 2, timestamp_utc: "2026-08-30T17:41:00" }),
    ]);
    renderHistory();
    const lines = await screen.findAllByText(/^Stacked /);
    expect(lines).toHaveLength(2);
    expect(lines[0].textContent).not.toBe(lines[1].textContent);
    // …and a run with no capture window says nothing about when it was shot.
    for (const l of lines) expect(l.textContent).not.toMatch(/Shot/);
  });

  it("drops the label and its separator when the stamp is unreadable", async () => {
    vi.spyOn(client.api, "listStackRuns").mockResolvedValue([
      mkRun({ timestamp_utc: "not-a-date" }),
    ]);
    renderHistory();
    const line = await screen.findByText(/100×100/);
    expect(line.textContent).not.toMatch(/Stacked/);
    expect(line.textContent).not.toMatch(/Invalid/);
    expect(line.textContent?.trimStart()).toMatch(/^100×100/);
  });
});

describe("derivedFromNote", () => {
  const source = mkRun({ id: 3, output_basename: "M42_master" });
  const exported = mkRun({
    id: 4, output_basename: "M42_master_edit", notes: "edited",
    options: { editor_recipe: {}, derived_from: 3, display_space: true },
  });

  it("names the stack an editor export was rendered from", () => {
    expect(derivedFromNote(exported, [source, exported]))
      .toEqual({ text: "Edited from M42_master", runId: 3 });
  });

  it("says nothing on an ordinary run", () => {
    // Only the *export* path writes `derived_from`; an "Apply & save" run
    // records its own row and must not claim an ancestor it doesn't have.
    expect(derivedFromNote(source, [source, exported])).toBeNull();
    expect(derivedFromNote(mkRun({ options: {} }), [])).toBeNull();
  });

  it("degrades to plain text when the source run is gone", () => {
    // Deleting the linear stack must never leave a dead link behind.
    expect(derivedFromNote(exported, [exported]))
      .toEqual({ text: "Edited from a stack that's no longer here", runId: null });
  });

  it("ignores a derived_from that isn't a usable run id", () => {
    // `options` is whatever JSON the run stored, so anything can be in there.
    for (const bad of ["3", null, undefined, NaN, {}, [3]]) {
      expect(derivedFromNote(
        mkRun({ id: 4, options: { derived_from: bad } }), [source],
      )).toBeNull();
    }
    // …and a row pointing at itself is a loop, not an ancestor.
    expect(derivedFromNote(
      mkRun({ id: 3, options: { derived_from: 3 } }), [source],
    )).toBeNull();
  });
});

describe("HistoryView — which row is the original?", () => {
  it("says which stack an export was edited from, and jumps to it", async () => {
    vi.spyOn(client.api, "listStackRuns").mockResolvedValue([
      mkRun({ id: 3, output_basename: "M42_master" }),
      mkRun({
        id: 4, output_basename: "M42_master_edit", notes: "edited",
        options: { derived_from: 3 },
      }),
    ]);
    renderHistory();
    const link = await screen.findByText("Edited from M42_master");
    expect(link).toHaveAttribute("href", "#stack-run-3");

    const scrollIntoView = vi.fn();
    const sourceCard = document.getElementById("stack-run-3");
    expect(sourceCard).not.toBeNull();
    sourceCard!.scrollIntoView = scrollIntoView;
    fireEvent.click(link);
    expect(scrollIntoView).toHaveBeenCalled();
  });

  it("shows no such line on a target whose runs are all plain stacks", async () => {
    vi.spyOn(client.api, "listStackRuns").mockResolvedValue([mkRun()]);
    renderHistory();
    await waitFor(() => expect(screen.getByText("M42_stack_01")).toBeInTheDocument());
    expect(screen.queryByText(/Edited from/)).not.toBeInTheDocument();
  });

  it("keeps the sentence but drops the link when the source was deleted", async () => {
    vi.spyOn(client.api, "listStackRuns").mockResolvedValue([
      mkRun({
        id: 4, output_basename: "M42_master_edit", notes: "edited",
        options: { derived_from: 3 },
      }),
    ]);
    renderHistory();
    const line = await screen.findByText("Edited from a stack that's no longer here");
    expect(line).not.toHaveAttribute("href");
  });
});
