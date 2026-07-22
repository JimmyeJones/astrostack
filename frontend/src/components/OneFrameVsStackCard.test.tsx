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
    vi.spyOn(client.api, "oneSubVsStackNoise").mockResolvedValue({ ratio: 15.3 });
    renderCard("M_42", 7);
    await waitFor(() =>
      expect(screen.getByText("One frame vs your stack")).toBeInTheDocument());
    // The caption is filled from the run's own provenance.
    expect(
      screen.getByText(/One 30-second frame vs your 505-frame stack/),
    ).toBeInTheDocument();
    // Collapsed: no image yet (History lists many runs — don't fetch each up front).
    expect(document.querySelector("img")).toBeNull();
    // The noise number isn't measured until the user reveals the comparison.
    expect(client.api.oneSubVsStackNoise).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: /see the difference/i }));
    // Both halves load: the raw sub and the finished stack preview.
    const sub = await screen.findByAltText("A single raw sub");
    expect(sub).toHaveAttribute("src", "/api/targets/M_42/stack-runs/7/reference-sub");
    const stack = screen.getByAltText("Your finished stack");
    expect(stack).toHaveAttribute("src", "/api/targets/M_42/stack-runs/7/preview");
    // …and the concrete "cut your noise ~N×" badge appears once measured.
    expect(await screen.findByTestId("noise-badge")).toHaveTextContent(
      "Stacking your 505 subs cut the background noise about 15×.");
  });

  it("omits the noise badge when the ratio can't be measured", async () => {
    vi.spyOn(client.api, "oneSubVsStack").mockResolvedValue({
      available: true, n_frames: 505, sub_exposure_s: 30, integration_s: 15150,
    });
    vi.spyOn(client.api, "oneSubVsStackNoise").mockResolvedValue({ ratio: null });
    renderCard("M_42", 7);
    fireEvent.click(await screen.findByRole("button", { name: /see the difference/i }));
    await screen.findByAltText("A single raw sub");
    await waitFor(() =>
      expect(client.api.oneSubVsStackNoise).toHaveBeenCalled());
    expect(screen.queryByTestId("noise-badge")).toBeNull();
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
