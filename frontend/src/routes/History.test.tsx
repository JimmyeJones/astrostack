import { MantineProvider } from "@mantine/core";
import { Notifications } from "@mantine/notifications";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { HistoryView, sortRuns, noiseDeltas, previousRunId, historyCompareHref, noiseTrendSeries, combineMethodLabel, formatEngineVersion, photometricSummaryText, darkScalingSummaryText, rejectionSummaryText, frameAccountingNote } from "./History";
import { formatIntegration } from "../format";
import * as client from "../api/client";
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

afterEach(() => vi.restoreAllMocks());

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

    fireEvent.click(screen.getByRole("button", { name: "Info" }));

    await waitFor(() => expect(info).toHaveBeenCalledWith("M_42", 1));
    await waitFor(() => expect(screen.getByText(/Integration: 42 min/)).toBeInTheDocument());
    expect(screen.getByText("sigma-clip")).toBeInTheDocument();
    // Plain-language combine line derived from the raw STACKER card.
    expect(screen.getByText(/Combined: κ-σ \(sigma-clip\) outlier rejection/)).toBeInTheDocument();
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
    fireEvent.click(screen.getByRole("button", { name: "Info" }));
    await waitFor(() =>
      expect(screen.getByText(/Auto-edited: flattened the background/)).toBeInTheDocument());
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
    fireEvent.click(screen.getByRole("button", { name: "Info" }));

    await waitFor(() =>
      expect(screen.getByText(/7 frames down-weighted/)).toBeInTheDocument());
    expect(screen.getByText(/weights 0.31–1.00/)).toBeInTheDocument();
  });

  it("shows integration time inline on a card without opening Info", async () => {
    vi.spyOn(client.api, "listStackRuns").mockResolvedValue([
      mkRun({ total_exposure_s: 2520 }),
    ]);

    renderHistory();
    // 2520 s → "42 min" on the card metadata line, no Info toggle needed.
    await waitFor(() => expect(screen.getByText(/42 min/)).toBeInTheDocument());
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
    fireEvent.click(screen.getByRole("button", { name: "Info" }));

    await waitFor(() =>
      expect(screen.getByText(/1,160 of 2,000 subs combined/)).toBeInTheDocument());
    expect(screen.getByText(/Open the Frames table/)).toBeInTheDocument();
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
