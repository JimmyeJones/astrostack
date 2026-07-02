import { MantineProvider } from "@mantine/core";
import { Notifications } from "@mantine/notifications";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { HistoryView } from "./History";
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
