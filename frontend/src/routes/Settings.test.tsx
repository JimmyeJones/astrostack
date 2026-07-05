import { MantineProvider } from "@mantine/core";
import { Notifications } from "@mantine/notifications";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { Maintenance, reprocessNudgeText } from "./Settings";
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

    // Default: outdated-only on, deep rescan off.
    await waitFor(() => expect(call).toHaveBeenCalledWith(true, false));
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

    await waitFor(() => expect(call).toHaveBeenCalledWith(false, false));
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
    await waitFor(() => expect(call).toHaveBeenCalledWith(true, true));
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
