import { MantineProvider } from "@mantine/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ImagingCalendarCard } from "./ImagingCalendarCard";
import type { ActivityCalendar } from "../api/client";
import * as client from "../api/client";

function cal(over: Partial<ActivityCalendar> = {}): ActivityCalendar {
  return {
    start_date: "2026-07-01",
    end_date: "2026-07-24",
    months: 12,
    nights: [
      { date: "2026-07-10", exposure_s: 3600, n_frames: 30, targets: ["M31"] },
      { date: "2026-07-20", exposure_s: 600, n_frames: 5, targets: ["M42"] },
    ],
    n_nights: 2,
    total_exposure_s: 4200,
    nights_this_month: 2,
    best_streak_nights: 1,
    ...over,
  };
}

function renderCard() {
  return render(
    <MantineProvider>
      <QueryClientProvider client={new QueryClient()}>
        <ImagingCalendarCard />
      </QueryClientProvider>
    </MantineProvider>,
  );
}

afterEach(() => vi.restoreAllMocks());

describe("ImagingCalendarCard", () => {
  it("renders the headline, total and a grid", async () => {
    vi.spyOn(client.api, "getActivityCalendar").mockResolvedValue(cal());
    renderCard();
    await waitFor(() =>
      expect(screen.getByText("Your imaging calendar")).toBeInTheDocument());
    expect(screen.getByText(/imaged 2 nights this month/)).toBeInTheDocument();
    expect(screen.getByLabelText("Imaging activity by night")).toBeInTheDocument();
  });

  it("renders nothing on a library with no imaged nights", async () => {
    vi.spyOn(client.api, "getActivityCalendar").mockResolvedValue(
      cal({ nights: [], n_nights: 0, total_exposure_s: 0, nights_this_month: 0 }),
    );
    const { container } = renderCard();
    await waitFor(() => expect(client.api.getActivityCalendar).toHaveBeenCalled());
    expect(container.querySelector(".mantine-Paper-root")).toBeNull();
  });
});
