import { MantineProvider } from "@mantine/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { FocusTrendCard } from "./FocusTrendCard";
import type { FocusTrend } from "../api/client";
import * as client from "../api/client";

function trend(over: Partial<FocusTrend> = {}): FocusTrend {
  return {
    verdict: "steady",
    points: [
      { t_utc: "2026-07-10T22:00:00+00:00", fwhm_px: 2.8 },
      { t_utc: "2026-07-10T22:30:00+00:00", fwhm_px: 2.7 },
      { t_utc: "2026-07-10T23:00:00+00:00", fwhm_px: 2.9 },
    ],
    n_points: 3,
    median_fwhm_px: 2.8,
    early_fwhm_px: 2.8,
    late_fwhm_px: 2.9,
    start_utc: "2026-07-10T22:00:00+00:00",
    end_utc: "2026-07-10T23:00:00+00:00",
    soft_after_utc: null,
    ...over,
  };
}

function renderCard(safe = "M_42") {
  return render(
    <MantineProvider>
      <QueryClientProvider client={new QueryClient()}>
        <FocusTrendCard safe={safe} />
      </QueryClientProvider>
    </MantineProvider>,
  );
}

afterEach(() => vi.restoreAllMocks());

describe("FocusTrendCard", () => {
  it("shows the sparkline + verdict for a softening night", async () => {
    vi.spyOn(client.api, "focusTrend").mockResolvedValue(trend({
      verdict: "softened",
      early_fwhm_px: 2.6,
      late_fwhm_px: 4.8,
      soft_after_utc: "2026-07-10T01:30:00+00:00",
    }));
    const { container } = renderCard();
    await waitFor(() =>
      expect(screen.getByText("Focus & sharpness")).toBeInTheDocument(),
    );
    expect(screen.getByText("softened")).toBeInTheDocument();
    expect(screen.getByText(/softened after 01:30 UTC/)).toBeInTheDocument();
    // The sparkline is drawn.
    expect(container.querySelector("svg polyline")).not.toBeNull();
  });

  it("self-hides when there's no trend to show (null)", async () => {
    vi.spyOn(client.api, "focusTrend").mockResolvedValue(null);
    const { container } = renderCard();
    await waitFor(() => expect(client.api.focusTrend).toHaveBeenCalled());
    expect(container.querySelector(".mantine-Paper-root")).toBeNull();
  });
});
