import { MantineProvider } from "@mantine/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { StackNoiseBadge } from "./StackNoiseBadge";
import * as client from "../api/client";

function renderBadge(props: { safe?: string; runId?: number; nFrames?: number | null } = {}) {
  const { safe = "M_42", runId = 7, nFrames = 505 } = props;
  return render(
    <MantineProvider>
      <QueryClientProvider client={new QueryClient()}>
        <StackNoiseBadge safe={safe} runId={runId} nFrames={nFrames} />
      </QueryClientProvider>
    </MantineProvider>,
  );
}

afterEach(() => vi.restoreAllMocks());

describe("StackNoiseBadge", () => {
  it("shows the measured 'cut your noise ~N×' payoff with the sub count", async () => {
    vi.spyOn(client.api, "oneSubVsStackNoise").mockResolvedValue({ ratio: 17.2 });
    renderBadge({ nFrames: 300 });
    await waitFor(() =>
      expect(screen.getByTestId("stack-noise-badge")).toBeInTheDocument());
    // ≥10× reads as a whole number; the frame count fills the "your N subs" clause.
    expect(
      screen.getByText("Stacking your 300 subs cut the background noise about 17×."),
    ).toBeInTheDocument();
  });

  it("still reads cleanly when the frame count is unknown", async () => {
    vi.spyOn(client.api, "oneSubVsStackNoise").mockResolvedValue({ ratio: 4 });
    renderBadge({ nFrames: null });
    await waitFor(() =>
      expect(screen.getByText(
        "Stacking your subs cut the background noise about 4×.",
      )).toBeInTheDocument());
  });

  it("renders nothing for an unmeasurable (null) ratio", async () => {
    vi.spyOn(client.api, "oneSubVsStackNoise").mockResolvedValue({ ratio: null });
    const { container } = renderBadge();
    await waitFor(() => expect(client.api.oneSubVsStackNoise).toHaveBeenCalled());
    expect(container.querySelector('[data-testid="stack-noise-badge"]')).toBeNull();
  });

  it("renders nothing for a too-small ratio (a thin stack's weak number)", async () => {
    vi.spyOn(client.api, "oneSubVsStackNoise").mockResolvedValue({ ratio: 1.2 });
    const { container } = renderBadge({ nFrames: 2 });
    await waitFor(() => expect(client.api.oneSubVsStackNoise).toHaveBeenCalled());
    expect(container.querySelector('[data-testid="stack-noise-badge"]')).toBeNull();
  });
});
