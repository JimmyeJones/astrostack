import { MantineProvider } from "@mantine/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { CalibrationSkippedNote } from "./CalibrationSkippedNote";
import * as client from "../api/client";

function renderNote() {
  return render(
    <MantineProvider>
      <QueryClientProvider client={new QueryClient()}>
        <CalibrationSkippedNote safe="m_42" runId={7} />
      </QueryClientProvider>
    </MantineProvider>,
  );
}

const INFO = { run_id: 7, integration_s: 2520, n_frames: 840, cards: [] };

afterEach(() => vi.restoreAllMocks());

describe("CalibrationSkippedNote", () => {
  it("says which saved master the run had to drop", async () => {
    vi.spyOn(client.api, "stackRunInfo").mockResolvedValue({
      ...INFO,
      calibration_skipped: [
        "Your saved master dark wasn't used: it's no longer in your calibration library.",
      ],
    } as never);
    renderNote();

    await waitFor(() =>
      expect(
        screen.getByText(/Your saved master dark wasn't used: it's no longer in your/),
      ).toBeInTheDocument());
  });

  it("joins several skips into one line", async () => {
    vi.spyOn(client.api, "stackRunInfo").mockResolvedValue({
      ...INFO,
      calibration_skipped: [
        "Your saved master dark wasn't used: it's no longer in your calibration library.",
        "Your saved master flat wasn't used: it was built for a different camera.",
      ],
    } as never);
    renderNote();

    await waitFor(() =>
      expect(screen.getByTestId("calibration-skipped-note").textContent)
        .toContain("master flat wasn't used"));
    expect(screen.getByTestId("calibration-skipped-note").textContent)
      .toContain("master dark wasn't used");
  });

  it("renders nothing when the run skipped nothing", async () => {
    vi.spyOn(client.api, "stackRunInfo")
      .mockResolvedValue({ ...INFO, calibration_skipped: [] } as never);
    renderNote();

    await waitFor(() => expect(client.api.stackRunInfo).toHaveBeenCalled());
    expect(screen.queryByTestId("calibration-skipped-note")).toBeNull();
  });

  it("stays silent on an older backend that doesn't report skips", async () => {
    vi.spyOn(client.api, "stackRunInfo").mockResolvedValue({ ...INFO } as never);
    renderNote();

    await waitFor(() => expect(client.api.stackRunInfo).toHaveBeenCalled());
    expect(screen.queryByTestId("calibration-skipped-note")).toBeNull();
  });

  it("stays silent (never errors) when the run info can't be fetched", async () => {
    vi.spyOn(client.api, "stackRunInfo").mockRejectedValue(new Error("boom"));
    renderNote();

    await waitFor(() => expect(client.api.stackRunInfo).toHaveBeenCalled());
    expect(screen.queryByTestId("calibration-skipped-note")).toBeNull();
  });
});
