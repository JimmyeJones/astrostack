import { MantineProvider } from "@mantine/core";
import { Notifications } from "@mantine/notifications";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Maintenance } from "./Settings";
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

afterEach(() => vi.restoreAllMocks());

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

    await waitFor(() => expect(call).toHaveBeenCalledWith(true));
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

    await waitFor(() => expect(call).toHaveBeenCalledWith(false));
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
