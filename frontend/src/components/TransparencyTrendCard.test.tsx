import { MantineProvider } from "@mantine/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { TransparencyTrendCard } from "./TransparencyTrendCard";
import type { TransparencyTrend } from "../api/client";
import * as client from "../api/client";

function trend(over: Partial<TransparencyTrend> = {}): TransparencyTrend {
  return {
    verdict: "clear",
    points: [
      { t_utc: "2026-07-10T22:00:00+00:00", transparency: 1000 },
      { t_utc: "2026-07-10T22:30:00+00:00", transparency: 1010 },
      { t_utc: "2026-07-10T23:00:00+00:00", transparency: 990 },
    ],
    n_points: 3,
    median_transparency: 1000,
    early_transparency: 1000,
    late_transparency: 990,
    start_utc: "2026-07-10T22:00:00+00:00",
    end_utc: "2026-07-10T23:00:00+00:00",
    degraded_after_utc: null,
    ...over,
  };
}

function renderCard(safe = "M_42") {
  return render(
    <MantineProvider>
      <QueryClientProvider client={new QueryClient()}>
        <TransparencyTrendCard safe={safe} />
      </QueryClientProvider>
    </MantineProvider>,
  );
}

afterEach(() => vi.restoreAllMocks());

describe("TransparencyTrendCard", () => {
  it("shows the sparkline + verdict for a night clouds rolled into", async () => {
    vi.spyOn(client.api, "transparencyTrend").mockResolvedValue(trend({
      verdict: "degraded",
      early_transparency: 1000,
      late_transparency: 450,
      degraded_after_utc: "2026-07-10T01:10:00+00:00",
    }));
    const { container } = renderCard();
    await waitFor(() =>
      expect(screen.getByText("Clouds & haze")).toBeInTheDocument(),
    );
    expect(screen.getByText("clouds rolled in")).toBeInTheDocument();
    expect(screen.getByText(/hazier after 01:10 UTC/)).toBeInTheDocument();
    // The sparkline is drawn.
    expect(container.querySelector("svg polyline")).not.toBeNull();
  });

  it("self-hides when there's no trend to show (null)", async () => {
    vi.spyOn(client.api, "transparencyTrend").mockResolvedValue(null);
    const { container } = renderCard();
    await waitFor(() => expect(client.api.transparencyTrend).toHaveBeenCalled());
    expect(container.querySelector(".mantine-Paper-root")).toBeNull();
  });
});
