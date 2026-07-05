import { MantineProvider } from "@mantine/core";
import { Notifications } from "@mantine/notifications";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { TargetView } from "./Target";
import * as client from "../api/client";
import type { Frame, Target } from "../api/client";

function mkFrame(id: number, overrides: Partial<Frame> = {}): Frame {
  return {
    id, name: `f${id}.fits`, timestamp_utc: "2026-01-01T00:00:00",
    exposure_s: 30, gain: 100, width_px: 480, height_px: 320,
    bayer_pattern: "RGGB", solved: true, ra_center_deg: 10, dec_center_deg: 20,
    ra_hint_deg: null, dec_hint_deg: null, fwhm_px: 2.5, star_count: 100,
    sky_adu_median: 500, eccentricity_median: 0.4, transparency_score: 5000,
    streak_detected: false,
    accept: true, reject_reason: null, user_override: false, ...overrides,
  };
}

function mkTarget(overrides: Partial<Target> = {}): Target {
  return {
    safe_name: "M_42", name: "M42", ra_deg: 10, dec_deg: 20,
    n_frames: 3, n_frames_accepted: 3, total_exposure_s: 90,
    last_activity_utc: "2026-01-01T00:00:00", has_preview: false,
    notes: null, tags: [], ...overrides,
  };
}

function renderTarget(qc = new QueryClient()) {
  return render(
    <MantineProvider>
      <Notifications />
      <QueryClientProvider client={qc}>
        <MemoryRouter initialEntries={["/targets/M_42"]}>
          <Routes>
            <Route path="/targets/:safe" element={<TargetView />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>
    </MantineProvider>,
  );
}

afterEach(() => vi.restoreAllMocks());

describe("TargetView streaked badge", () => {
  it("shows a streaked-frame count for accepted frames carrying a trail", async () => {
    vi.spyOn(client.api, "getTarget").mockResolvedValue(mkTarget());
    vi.spyOn(client.api, "listStackRuns").mockResolvedValue([]);
    vi.spyOn(client.api, "listFrames").mockResolvedValue([
      mkFrame(1, { streak_detected: true }),
      mkFrame(2, { streak_detected: true }),
      // a rejected streaked frame should not count
      mkFrame(3, { streak_detected: true, accept: false }),
    ]);

    renderTarget();

    await waitFor(() =>
      expect(screen.getByText("2 streaked")).toBeInTheDocument());
  });

  it("rejects all streaked frames in one gesture from the badge action", async () => {
    vi.spyOn(client.api, "getTarget").mockResolvedValue(mkTarget());
    vi.spyOn(client.api, "listStackRuns").mockResolvedValue([]);
    vi.spyOn(client.api, "listFrames").mockResolvedValue([
      mkFrame(1, { streak_detected: true }),
      mkFrame(2, { streak_detected: true }),
    ]);
    const bulk = vi
      .spyOn(client.api, "bulkFrames")
      .mockResolvedValue({ changed: 2, changed_ids: [1, 2] });
    vi.spyOn(window, "confirm").mockReturnValue(true);

    renderTarget();

    const btn = await screen.findByRole("button", {
      name: "Reject all streaked frames",
    });
    btn.click();

    await waitFor(() =>
      expect(bulk).toHaveBeenCalledWith("M_42", { action: "reject_streaked" }));
  });

  it("omits the badge when no accepted frame carries a trail", async () => {
    vi.spyOn(client.api, "getTarget").mockResolvedValue(mkTarget());
    vi.spyOn(client.api, "listStackRuns").mockResolvedValue([]);
    vi.spyOn(client.api, "listFrames").mockResolvedValue([
      mkFrame(1), mkFrame(2),
    ]);

    renderTarget();

    await waitFor(() =>
      expect(screen.getByText("3/3 accepted")).toBeInTheDocument());
    expect(screen.queryByText(/streaked/)).not.toBeInTheDocument();
  });

  it("gives the metric column headers plain-language hint tooltips", async () => {
    vi.spyOn(client.api, "getTarget").mockResolvedValue(mkTarget());
    vi.spyOn(client.api, "listStackRuns").mockResolvedValue([]);
    vi.spyOn(client.api, "listFrames").mockResolvedValue([mkFrame(1)]);

    renderTarget();

    // Each metric header is a dotted-underline span carrying a Tooltip hint, so
    // a beginner can learn what "Ecc." / "FWHM" mean without leaving the table.
    // (Some labels also appear in the frame-detail panel, so match the header
    // span by its dotted-underline styling.)
    await screen.findAllByText("Ecc.");
    for (const label of ["FWHM", "Stars", "Ecc.", "Sky", "Transp."]) {
      const header = screen.getAllByText(label).find(
        (el) => el.tagName === "SPAN"
          && (el.getAttribute("style") ?? "").includes("underline dotted"));
      expect(header, `${label} header should carry a hint`).toBeTruthy();
    }
  });
});

describe("TargetView trailed badge", () => {
  // Eight tight, round subs plus one strongly-elongated one: only the outlier
  // (both >3·MAD and above the 0.6 floor) counts as trailed.
  const trailedSet = () => [
    ...Array.from({ length: 8 }, (_, i) =>
      mkFrame(i + 1, { eccentricity_median: 0.2 })),
    mkFrame(9, { eccentricity_median: 0.85 }),
  ];

  it("counts accepted frames whose stars are strong eccentricity outliers", async () => {
    vi.spyOn(client.api, "getTarget").mockResolvedValue(mkTarget({ n_frames: 9, n_frames_accepted: 9 }));
    vi.spyOn(client.api, "listStackRuns").mockResolvedValue([]);
    vi.spyOn(client.api, "listFrames").mockResolvedValue(trailedSet());

    renderTarget();

    await waitFor(() =>
      expect(screen.getByText("1 trailed")).toBeInTheDocument());
  });

  it("rejects all trailed frames in one gesture from the badge action", async () => {
    vi.spyOn(client.api, "getTarget").mockResolvedValue(mkTarget({ n_frames: 9, n_frames_accepted: 9 }));
    vi.spyOn(client.api, "listStackRuns").mockResolvedValue([]);
    vi.spyOn(client.api, "listFrames").mockResolvedValue(trailedSet());
    const bulk = vi
      .spyOn(client.api, "bulkFrames")
      .mockResolvedValue({ changed: 1, changed_ids: [9] });
    vi.spyOn(window, "confirm").mockReturnValue(true);

    renderTarget();

    const btn = await screen.findByRole("button", {
      name: "Reject all trailed frames",
    });
    btn.click();

    await waitFor(() =>
      expect(bulk).toHaveBeenCalledWith("M_42", { action: "reject_trailed" }));
  });

  it("omits the badge when the set is uniformly round", async () => {
    vi.spyOn(client.api, "getTarget").mockResolvedValue(mkTarget({ n_frames: 6, n_frames_accepted: 6 }));
    vi.spyOn(client.api, "listStackRuns").mockResolvedValue([]);
    vi.spyOn(client.api, "listFrames").mockResolvedValue(
      Array.from({ length: 6 }, (_, i) => mkFrame(i + 1, { eccentricity_median: 0.3 })),
    );

    renderTarget();

    await waitFor(() =>
      expect(screen.getByText("6/6 accepted")).toBeInTheDocument());
    expect(screen.queryByText(/trailed/)).not.toBeInTheDocument();
  });
});

describe("TargetView auto-grade", () => {
  function mkReport(overrides: Partial<client.GradeReport> = {}): client.GradeReport {
    return {
      sensitivity: "balanced", n_accepted: 30, n_considered: 30,
      recommendations: [], metrics_used: ["fwhm_px"], metrics_skipped: {},
      capped: false, changed_ids: null, ...overrides,
    };
  }

  it("previews outliers with reasons, applies, and offers undo", async () => {
    vi.spyOn(client.api, "getTarget").mockResolvedValue(mkTarget());
    vi.spyOn(client.api, "listStackRuns").mockResolvedValue([]);
    vi.spyOn(client.api, "listFrames").mockResolvedValue([mkFrame(1), mkFrame(2)]);
    const preview = vi.spyOn(client.api, "autoGradePreview").mockResolvedValue(
      mkReport({
        recommendations: [{
          frame_id: 2, name: "f2.fits",
          reasons: [{
            metric: "fwhm_px", value: 8.0, typical: 3.0, z: 6.1,
            label: "much softer than typical (FWHM 8.0 px vs 3.0 px) — poor seeing, focus drift or cloud",
          }],
        }],
      }),
    );
    const apply = vi.spyOn(client.api, "autoGradeApply").mockResolvedValue(
      mkReport({ changed_ids: [2] }),
    );
    const bulk = vi.spyOn(client.api, "bulkFrames")
      .mockResolvedValue({ changed: 1, changed_ids: [2] });

    renderTarget();

    (await screen.findByRole("button", { name: /Auto-grade/ })).click();

    // The preview modal lists the flagged frame with its plain-language reason.
    await waitFor(() => expect(preview).toHaveBeenCalledWith("M_42", undefined));
    expect(await screen.findByText(/of 30 accepted frames look/)).toBeInTheDocument();
    expect(screen.getByText(/much softer than typical/)).toBeInTheDocument();

    (await screen.findByRole("button", { name: "Reject 1 frame" })).click();
    await waitFor(() => expect(apply).toHaveBeenCalledWith("M_42", undefined));

    // The apply flows into the shared undo affordance.
    const undo = await screen.findByRole("button", { name: "Undo last bulk reject" });
    undo.click();
    await waitFor(() =>
      expect(bulk).toHaveBeenCalledWith("M_42", { action: "accept", ids: [2] }));
  });

  it("shows a quiet all-consistent state when nothing is flagged", async () => {
    vi.spyOn(client.api, "getTarget").mockResolvedValue(mkTarget());
    vi.spyOn(client.api, "listStackRuns").mockResolvedValue([]);
    vi.spyOn(client.api, "listFrames").mockResolvedValue([mkFrame(1)]);
    vi.spyOn(client.api, "autoGradePreview").mockResolvedValue(mkReport());

    renderTarget();
    (await screen.findByRole("button", { name: /Auto-grade/ })).click();

    expect(await screen.findByText(/No outliers found/)).toBeInTheDocument();
    // The apply button is disabled with nothing to reject.
    const rejectBtn = screen.getByRole("button", { name: "Reject 0 frames" });
    expect(rejectBtn).toBeDisabled();
  });

  it("explains when there aren't enough graded frames yet", async () => {
    vi.spyOn(client.api, "getTarget").mockResolvedValue(mkTarget());
    vi.spyOn(client.api, "listStackRuns").mockResolvedValue([]);
    vi.spyOn(client.api, "listFrames").mockResolvedValue([mkFrame(1)]);
    vi.spyOn(client.api, "autoGradePreview").mockResolvedValue(
      mkReport({ metrics_used: [], metrics_skipped: { fwhm_px: "only 3 of 3" } }),
    );

    renderTarget();
    (await screen.findByRole("button", { name: /Auto-grade/ })).click();

    expect(await screen.findByText(/Not enough graded frames/)).toBeInTheDocument();
  });

  it("labels auto-grade rejections on frame rows", async () => {
    vi.spyOn(client.api, "getTarget").mockResolvedValue(
      mkTarget({ n_frames: 2, n_frames_accepted: 1 }),
    );
    vi.spyOn(client.api, "listStackRuns").mockResolvedValue([]);
    vi.spyOn(client.api, "rejectSummary").mockResolvedValue({
      counts: { "auto:grade:transparency_score": 1 }, total: 1,
    });
    vi.spyOn(client.api, "listFrames").mockResolvedValue([
      mkFrame(1),
      mkFrame(2, { accept: false, reject_reason: "auto:grade:transparency_score" }),
    ]);

    renderTarget();

    await waitFor(() =>
      expect(screen.getByText("Auto-grade: transparency")).toBeInTheDocument());
  });
});

describe("TargetView reject breakdown + undo", () => {
  it("shows a rejected-count badge with a why breakdown", async () => {
    vi.spyOn(client.api, "getTarget").mockResolvedValue(
      mkTarget({ n_frames: 5, n_frames_accepted: 3 }),
    );
    vi.spyOn(client.api, "listStackRuns").mockResolvedValue([]);
    vi.spyOn(client.api, "listFrames").mockResolvedValue([mkFrame(1)]);
    const summary = vi
      .spyOn(client.api, "rejectSummary")
      .mockResolvedValue({ counts: { "qc:fwhm": 1, user: 1 }, total: 2 });

    renderTarget();

    await waitFor(() =>
      expect(screen.getByText("2 rejected")).toBeInTheDocument());
    expect(summary).toHaveBeenCalledWith("M_42");
  });

  it("shows a per-row plain-language reason chip on rejected frames", async () => {
    vi.spyOn(client.api, "getTarget").mockResolvedValue(
      mkTarget({ n_frames: 3, n_frames_accepted: 1 }),
    );
    vi.spyOn(client.api, "listStackRuns").mockResolvedValue([]);
    vi.spyOn(client.api, "rejectSummary").mockResolvedValue({
      counts: { "auto:streak": 1, solve_failed: 1 }, total: 2,
    });
    vi.spyOn(client.api, "listFrames").mockResolvedValue([
      mkFrame(1),
      mkFrame(2, { accept: false, reject_reason: "auto:streak" }),
      mkFrame(3, { accept: false, reject_reason: "solve_failed:no stars" }),
    ]);

    renderTarget();

    // Each rejected row shows its own plain-language reason; an accepted row shows none.
    await waitFor(() =>
      expect(screen.getByText("Auto: streak")).toBeInTheDocument());
    expect(screen.getByText("Plate-solve failed")).toBeInTheDocument();
  });

  it("shows an actionable setup banner when ASTAP is missing for the whole target", async () => {
    vi.spyOn(client.api, "getTarget").mockResolvedValue(
      mkTarget({ n_frames: 3, n_frames_accepted: 0 }),
    );
    vi.spyOn(client.api, "listStackRuns").mockResolvedValue([]);
    vi.spyOn(client.api, "rejectSummary").mockResolvedValue({
      counts: {
        "solve_failed:astap.exe not found. Install ASTAP from https://www.hnsky.org/astap.htm":
          3,
      },
      total: 3,
    });
    vi.spyOn(client.api, "listFrames").mockResolvedValue([
      mkFrame(1, { accept: false, solved: false }),
    ]);

    renderTarget();

    await waitFor(() =>
      expect(
        screen.getByText("Plate-solving isn't set up — ASTAP wasn't found"),
      ).toBeInTheDocument());
    // The banner offers the one-time fix, not per-frame drops.
    expect(
      screen.getByRole("button", { name: "Re-run QC + Solve" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open Settings" })).toBeInTheDocument();
  });

  it("prefers the server's solve_setup_problem classification (reliable for the database case)", async () => {
    vi.spyOn(client.api, "getTarget").mockResolvedValue(
      mkTarget({ n_frames: 4, n_frames_accepted: 0 }),
    );
    vi.spyOn(client.api, "listStackRuns").mockResolvedValue([]);
    // The stored `counts` key lacks the "no star database" phrase (the old
    // unreliable truncation case), so client-side detection alone would miss it —
    // but the server classified it, so the banner still fires.
    vi.spyOn(client.api, "rejectSummary").mockResolvedValue({
      counts: { "solve_failed:Reading FITS header... found 214 stars...": 4 },
      total: 4,
      solve_setup_problem: { kind: "database", frames: 4 },
    });
    vi.spyOn(client.api, "listFrames").mockResolvedValue([
      mkFrame(1, { accept: false, solved: false }),
    ]);

    renderTarget();

    await waitFor(() =>
      expect(
        screen.getByText("Plate-solving needs a star database"),
      ).toBeInTheDocument());
  });

  it("shows no setup banner for ordinary per-frame solve failures", async () => {
    vi.spyOn(client.api, "getTarget").mockResolvedValue(
      mkTarget({ n_frames: 3, n_frames_accepted: 2 }),
    );
    vi.spyOn(client.api, "listStackRuns").mockResolvedValue([]);
    vi.spyOn(client.api, "rejectSummary").mockResolvedValue({
      counts: { "solve_failed:no solution": 1 }, total: 1,
    });
    vi.spyOn(client.api, "listFrames").mockResolvedValue([
      mkFrame(1),
      mkFrame(2),
      mkFrame(3, { accept: false, solved: false, reject_reason: "solve_failed:no solution" }),
    ]);

    renderTarget();

    await waitFor(() => expect(screen.getByText("2/3 accepted")).toBeInTheDocument());
    expect(
      screen.queryByText(/Plate-solving isn't set up/),
    ).not.toBeInTheDocument();
  });

  it("offers Undo after a bulk reject and re-accepts exactly those ids", async () => {
    vi.spyOn(client.api, "getTarget").mockResolvedValue(mkTarget());
    vi.spyOn(client.api, "listStackRuns").mockResolvedValue([]);
    vi.spyOn(client.api, "listFrames").mockResolvedValue([
      mkFrame(1, { streak_detected: true }),
      mkFrame(2, { streak_detected: true }),
    ]);
    const bulk = vi
      .spyOn(client.api, "bulkFrames")
      .mockResolvedValue({ changed: 2, changed_ids: [1, 2] });
    vi.spyOn(window, "confirm").mockReturnValue(true);

    renderTarget();

    const reject = await screen.findByRole("button", {
      name: "Reject all streaked frames",
    });
    reject.click();

    const undo = await screen.findByRole("button", {
      name: "Undo last bulk reject",
    });
    undo.click();

    await waitFor(() =>
      expect(bulk).toHaveBeenCalledWith("M_42", { action: "accept", ids: [1, 2] }));
  });
});

describe("TargetView error state", () => {
  it("shows a recoverable error (not a broken shell) when the target 404s", async () => {
    // A deleted target / stale bookmark: api.getTarget rejects with the 404.
    vi.spyOn(client.api, "getTarget").mockRejectedValue(new Error("No target 'M_42'"));
    vi.spyOn(client.api, "listStackRuns").mockResolvedValue([]);
    vi.spyOn(client.api, "listFrames").mockResolvedValue([]);

    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    renderTarget(qc);

    // The shared QueryError surfaces instead of a blank title + empty table.
    await waitFor(() =>
      expect(screen.getByText("Couldn't load this page")).toBeInTheDocument());
    expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
  });
});
