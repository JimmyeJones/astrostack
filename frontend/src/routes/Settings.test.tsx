import { MantineProvider } from "@mantine/core";
import { Notifications } from "@mantine/notifications";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  autoCastSummaryText, Maintenance, reprocessNudgeText,
  WALK_AWAY_KEYS, walkAwayEnabled, withWalkAway,
} from "./Settings";
import * as client from "../api/client";

function renderMaintenance() {
  const qc = new QueryClient();
  return render(
    <MantineProvider>
      <Notifications />
      <QueryClientProvider client={qc}>
        <MemoryRouter>
          <Maintenance />
        </MemoryRouter>
      </QueryClientProvider>
    </MantineProvider>,
  );
}

// Maintenance now queries reprocess-status on mount; default it to "nothing
// outdated" so the existing button tests don't hit an unmocked fetch. Individual
// tests override it.
beforeEach(() => {
  vi.spyOn(client.api, "reprocessStatus").mockResolvedValue({
    current_version: "0.81.3", outdated: 0, up_to_date: 3, total_targets: 3,
  });
  // Maintenance also queries the auto-cast summary on mount; default to "nothing
  // measured yet" so the button tests don't hit an unmocked fetch.
  vi.spyOn(client.api, "autoCastSummary").mockResolvedValue({
    measured: 0, neutral: 0, cast: 0, by_cast: {}, median_deviation: null,
  });
});

afterEach(() => vi.restoreAllMocks());

describe("reprocessNudgeText", () => {
  it("returns null when nothing is outdated or status is missing", () => {
    expect(reprocessNudgeText(undefined)).toBeNull();
    expect(reprocessNudgeText({
      current_version: "0.81.3", outdated: 0, up_to_date: 4, total_targets: 4,
    })).toBeNull();
  });

  it("names a single outdated target with the running version", () => {
    const msg = reprocessNudgeText({
      current_version: "0.81.3", outdated: 1, up_to_date: 2, total_targets: 3,
    });
    expect(msg).toContain("1 target was");
    expect(msg).toContain("v0.81.3");
    expect(msg).toContain("non-destructive");
  });

  it("pluralises multiple outdated targets", () => {
    const msg = reprocessNudgeText({
      current_version: "0.81.3", outdated: 3, up_to_date: 0, total_targets: 3,
    });
    expect(msg).toContain("3 targets were");
    expect(msg).toContain("Reprocess them");
  });
});

describe("autoCastSummaryText", () => {
  it("returns null when nothing has been measured or the summary is missing", () => {
    expect(autoCastSummaryText(undefined)).toBeNull();
    expect(autoCastSummaryText({
      measured: 0, neutral: 0, cast: 0, by_cast: {}, median_deviation: null,
    })).toBeNull();
  });

  it("reports an all-neutral result cleanly", () => {
    const msg = autoCastSummaryText({
      measured: 5, neutral: 5, cast: 0, by_cast: {}, median_deviation: 0.004,
    });
    expect(msg).toContain("neutral on all 5 auto-edited results");
    expect(msg).toContain("landing clean");
  });

  it("splits neutral vs cast and names the dominant tints commonest-first", () => {
    const msg = autoCastSummaryText({
      measured: 10, neutral: 7, cast: 3,
      by_cast: { magenta: 1, green: 2 }, median_deviation: 0.018,
    });
    expect(msg).toContain("neutral on 7 of 10 auto-edited results");
    expect(msg).toContain("3 carried a slight cast");
    // Green (2) is listed before magenta (1).
    expect(msg).toMatch(/2 green, 1 magenta/);
  });

  it("uses the singular for a single measured result", () => {
    const msg = autoCastSummaryText({
      measured: 1, neutral: 0, cast: 1,
      by_cast: { green: 1 }, median_deviation: 0.02,
    });
    expect(msg).toContain("neutral on 0 of 1 auto-edited result;");
  });
});

describe("Walk-away mode", () => {
  it("is off unless every one of the bundled switches is on", () => {
    expect(walkAwayEnabled({})).toBe(false);
    // All but one on → still off (the master switch mirrors the real state).
    const allButOne: Record<string, unknown> = {};
    WALK_AWAY_KEYS.forEach((k) => (allButOne[k] = true));
    allButOne[WALK_AWAY_KEYS[0]] = false;
    expect(walkAwayEnabled(allButOne)).toBe(false);
  });

  it("is on exactly when all bundled switches are on", () => {
    const all: Record<string, unknown> = {};
    WALK_AWAY_KEYS.forEach((k) => (all[k] = true));
    expect(walkAwayEnabled(all)).toBe(true);
  });

  it("turning it on sets every bundled switch true without touching others", () => {
    const before = { auto_qc: true, keep_streaked_frames: false };
    const after = withWalkAway(before, true);
    WALK_AWAY_KEYS.forEach((k) => expect(after[k]).toBe(true));
    // Unrelated settings are preserved untouched.
    expect(after.auto_qc).toBe(true);
    expect(after.keep_streaked_frames).toBe(false);
    // Input is not mutated (returns a fresh object).
    expect(before).not.toHaveProperty("auto_stack");
  });

  it("turning it off clears every bundled switch", () => {
    const on: Record<string, unknown> = { auto_qc: true };
    WALK_AWAY_KEYS.forEach((k) => (on[k] = true));
    const after = withWalkAway(on, false);
    WALK_AWAY_KEYS.forEach((k) => expect(after[k]).toBe(false));
    expect(after.auto_qc).toBe(true);
  });

  it("bundles the five hands-off pipeline switches", () => {
    expect([...WALK_AWAY_KEYS]).toEqual([
      "auto_stack",
      "auto_edit_on_autostack",
      "auto_bind_calibration",
      "auto_grade_frames",
      "mixed_pointing_guard",
    ]);
  });
});

describe("Maintenance — Auto colour self-check", () => {
  it("shows the sky-cast read-out once auto-edited runs are measured", async () => {
    vi.spyOn(client.api, "autoCastSummary").mockResolvedValue({
      measured: 4, neutral: 3, cast: 1, by_cast: { green: 1 }, median_deviation: 0.012,
    });
    renderMaintenance();
    await waitFor(() =>
      expect(screen.getByText(/neutral on 3 of 4 auto-edited results/))
        .toBeInTheDocument());
  });

  it("shows no read-out before any auto-edited run is measured", async () => {
    renderMaintenance();
    await waitFor(() =>
      expect(screen.getByRole("button", { name: /Reprocess .* targets/ }))
        .toBeInTheDocument());
    expect(screen.queryByText(/auto-edited result/)).toBeNull();
  });
});

describe("Maintenance — outdated-images nudge", () => {
  it("shows the nudge Alert when targets are outdated", async () => {
    vi.spyOn(client.api, "reprocessStatus").mockResolvedValue({
      current_version: "0.81.3", outdated: 2, up_to_date: 1, total_targets: 3,
    });
    renderMaintenance();
    await waitFor(() =>
      expect(screen.getByText(/2 targets were last stacked with an older/))
        .toBeInTheDocument());
    expect(screen.getByText("Some images are out of date")).toBeInTheDocument();
  });

  it("shows no nudge when everything is up to date", async () => {
    renderMaintenance();
    // Let the (mocked) status query settle, then assert the nudge is absent.
    await waitFor(() =>
      expect(screen.getByRole("button", { name: /Reprocess .* targets/ }))
        .toBeInTheDocument());
    expect(screen.queryByText("Some images are out of date")).toBeNull();
  });
});

describe("Maintenance — reprocess everything", () => {
  it("does nothing when the confirm is declined", () => {
    vi.spyOn(window, "confirm").mockReturnValue(false);
    const call = vi.spyOn(client.api, "reprocessAll");

    renderMaintenance();
    fireEvent.click(screen.getByRole("button", { name: /Reprocess .* targets/ }));

    expect(call).not.toHaveBeenCalled();
  });

  it("defaults to reprocessing only outdated targets (stale_only=true)", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    const call = vi
      .spyOn(client.api, "reprocessAll")
      .mockResolvedValue({ job_id: "job-9", already_running: false });

    renderMaintenance();
    // The default button names the "outdated" scope, matching the default toggle.
    fireEvent.click(screen.getByRole("button", { name: /Reprocess outdated targets/ }));

    // Default: outdated-only on, deep rescan off, auto-edit off.
    await waitFor(() => expect(call).toHaveBeenCalledWith(true, false, false));
    await waitFor(() =>
      expect(screen.getByText(/Reprocessing targets/)).toBeInTheDocument());
  });

  it("reprocesses every target when the outdated-only toggle is turned off", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    const call = vi
      .spyOn(client.api, "reprocessAll")
      .mockResolvedValue({ job_id: "job-9", already_running: false });

    renderMaintenance();
    fireEvent.click(screen.getByLabelText(/Only targets not already stacked on this version/));
    fireEvent.click(screen.getByRole("button", { name: /Reprocess all targets/ }));

    await waitFor(() => expect(call).toHaveBeenCalledWith(false, false, false));
  });

  it("passes deep_rescan when the QC/solve/grade toggle is turned on", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    const call = vi
      .spyOn(client.api, "reprocessAll")
      .mockResolvedValue({ job_id: "job-9", already_running: false });

    renderMaintenance();
    fireEvent.click(screen.getByLabelText(/re-run QC, plate-solving & grading/));
    fireEvent.click(screen.getByRole("button", { name: /Reprocess .* targets/ }));

    // Still outdated-only by default, now with the deep rescan opted in.
    await waitFor(() => expect(call).toHaveBeenCalledWith(true, true, false));
  });

  it("passes auto_edit when the auto-edit toggle is turned on", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    const call = vi
      .spyOn(client.api, "reprocessAll")
      .mockResolvedValue({ job_id: "job-9", already_running: false });

    renderMaintenance();
    fireEvent.click(screen.getByLabelText(/auto-edit each result into a finished picture/));
    fireEvent.click(screen.getByRole("button", { name: /Reprocess .* targets/ }));

    // Still outdated-only by default, now with the auto-edit opted in.
    await waitFor(() => expect(call).toHaveBeenCalledWith(true, false, true));
  });

  it("surfaces the already-running case", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    vi.spyOn(client.api, "reprocessAll")
      .mockResolvedValue({ job_id: "job-9", already_running: true });

    renderMaintenance();
    fireEvent.click(screen.getByRole("button", { name: /Reprocess .* targets/ }));

    await waitFor(() =>
      expect(screen.getByText(/already running/)).toBeInTheDocument());
  });

  it("shows an error notification when the request fails", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    vi.spyOn(client.api, "reprocessAll").mockRejectedValue(new Error("boom"));

    renderMaintenance();
    fireEvent.click(screen.getByRole("button", { name: /Reprocess .* targets/ }));

    await waitFor(() => expect(screen.getByText("boom")).toBeInTheDocument());
  });
});
