import { MantineProvider } from "@mantine/core";
import { Notifications } from "@mantine/notifications";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { HistoryView, sortRuns } from "./History";
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
