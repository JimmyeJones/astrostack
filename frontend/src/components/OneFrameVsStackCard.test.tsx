import { MantineProvider } from "@mantine/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { OneFrameVsStackCard } from "./OneFrameVsStackCard";
import * as client from "../api/client";

function renderCard(safe = "M_42", runId = 7) {
  return render(
    <MantineProvider>
      <QueryClientProvider client={new QueryClient()}>
        <OneFrameVsStackCard safe={safe} runId={runId} />
      </QueryClientProvider>
    </MantineProvider>,
  );
}

afterEach(() => vi.restoreAllMocks());

describe("OneFrameVsStackCard", () => {
  it("renders nothing when the reveal isn't available", async () => {
    vi.spyOn(client.api, "oneSubVsStack").mockResolvedValue({
      available: false, n_frames: null, sub_exposure_s: null, integration_s: null,
    });
    const { container } = renderCard();
    await waitFor(() => expect(client.api.oneSubVsStack).toHaveBeenCalled());
    expect(container.querySelector(".mantine-Paper-root")).toBeNull();
  });

  it("shows the caption and reveals the split comparison on click", async () => {
    vi.spyOn(client.api, "oneSubVsStack").mockResolvedValue({
      available: true, n_frames: 505, sub_exposure_s: 30, integration_s: 15150,
    });
    renderCard("M_42", 7);
    await waitFor(() =>
      expect(screen.getByText("One frame vs your stack")).toBeInTheDocument());
    // The caption is filled from the run's own provenance.
    expect(
      screen.getByText(/One 30-second frame vs your 505-frame stack/),
    ).toBeInTheDocument();
    // Collapsed: no image yet (History lists many runs — don't fetch each up front).
    expect(document.querySelector("img")).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: /see the difference/i }));
    // Both halves load: the raw sub and the finished stack preview.
    const sub = await screen.findByAltText("A single raw sub");
    expect(sub).toHaveAttribute("src", "/api/targets/M_42/stack-runs/7/reference-sub");
    const stack = screen.getByAltText("Your finished stack");
    expect(stack).toHaveAttribute("src", "/api/targets/M_42/stack-runs/7/preview");
  });

  it("degrades the caption when provenance is missing", async () => {
    vi.spyOn(client.api, "oneSubVsStack").mockResolvedValue({
      available: true, n_frames: null, sub_exposure_s: null, integration_s: null,
    });
    renderCard();
    await waitFor(() =>
      expect(screen.getByText(/One frame vs your stack —/)).toBeInTheDocument());
  });
});
