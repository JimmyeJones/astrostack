import { MantineProvider } from "@mantine/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { BestNightCard } from "./BestNightCard";
import * as client from "../api/client";
import type { ActivityCalendar, NightActivity } from "../api/client";

function cal(sharpest: NightActivity | null): ActivityCalendar {
  return {
    start_date: "2025-08-18", end_date: "2026-08-18", months: 12,
    nights: [], n_nights: 12, total_exposure_s: 30000,
    nights_this_month: 2, best_streak_nights: 3,
    sharpest_night: sharpest,
  };
}

function renderCard() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <MantineProvider>
      <QueryClientProvider client={qc}><BestNightCard /></QueryClientProvider>
    </MantineProvider>,
  );
}

afterEach(() => vi.restoreAllMocks());

describe("BestNightCard", () => {
  it("names the sharpest night of the last year", async () => {
    vi.spyOn(client.api, "getActivityCalendar").mockResolvedValue(cal({
      date: "2026-01-12", exposure_s: 5400, n_frames: 180,
      targets: ["M 42"], median_fwhm_px: 2.44, n_measured: 180,
    }));
    renderCard();
    expect(await screen.findByText(/Your best night · 12 Jan 2026/))
      .toBeInTheDocument();
    expect(screen.getByText("2.4 px stars")).toBeInTheDocument();
    expect(screen.getByText(/Your steadiest sky yet on M 42/)).toBeInTheDocument();
  });

  it("renders nothing when the backend named no best night", async () => {
    vi.spyOn(client.api, "getActivityCalendar").mockResolvedValue(cal(null));
    renderCard();
    await waitFor(() =>
      expect(client.api.getActivityCalendar).toHaveBeenCalled());
    expect(screen.queryByTestId("best-night")).not.toBeInTheDocument();
  });

  it("renders nothing against an older backend that doesn't send the field", async () => {
    const older = cal(null);
    delete (older as Partial<ActivityCalendar>).sharpest_night;
    vi.spyOn(client.api, "getActivityCalendar").mockResolvedValue(older);
    renderCard();
    await waitFor(() =>
      expect(client.api.getActivityCalendar).toHaveBeenCalled());
    expect(screen.queryByTestId("best-night")).not.toBeInTheDocument();
  });

  it("renders nothing while loading, and swallows a failed fetch", async () => {
    vi.spyOn(client.api, "getActivityCalendar")
      .mockRejectedValue(new Error("nope"));
    renderCard();
    await waitFor(() =>
      expect(client.api.getActivityCalendar).toHaveBeenCalled());
    expect(screen.queryByTestId("best-night")).not.toBeInTheDocument();
  });
});
