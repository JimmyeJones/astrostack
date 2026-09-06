import { MantineProvider } from "@mantine/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { OffNightCard } from "./OffNightCard";
import * as client from "../api/client";
import type { ActivityCalendar, OffNight } from "../api/client";

function cal(off: OffNight | null): ActivityCalendar {
  return {
    start_date: "2025-08-18", end_date: "2026-08-18", months: 12,
    nights: [], n_nights: 12, total_exposure_s: 30000,
    nights_this_month: 2, best_streak_nights: 3,
    off_night: off,
  };
}

const SOFT: OffNight = {
  level: "fatter",
  label: "Softer than usual",
  text: "On 2026-08-17 your stars came out about 45% fatter than your usual "
    + "night. That is often dew on the lens or a little focus drift, though it "
    + "can just be poor seeing. Worth a quick look before your next session.",
  night: "2026-08-17",
  baseline_nights: 9,
  ratio: 1.45,
  median_fwhm_px: 4.35,
  baseline_fwhm_px: 3.0,
};

function renderCard() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <MantineProvider>
      <QueryClientProvider client={qc}><OffNightCard /></QueryClientProvider>
    </MantineProvider>,
  );
}

afterEach(() => vi.restoreAllMocks());

describe("OffNightCard", () => {
  it("says what was measured and what to check", async () => {
    vi.spyOn(client.api, "getActivityCalendar").mockResolvedValue(cal(SOFT));
    renderCard();
    expect(await screen.findByText("Softer than usual")).toBeInTheDocument();
    expect(screen.getByText(/45% fatter/)).toBeInTheDocument();
    // The claim is checkable, not just asserted.
    expect(screen.getByText(/4\.3 px that night vs 3\.0 px/))
      .toBeInTheDocument();
    expect(screen.getByText(/previous 9 measured nights/)).toBeInTheDocument();
  });

  it("never asserts a fault — poor seeing is offered as a cause", async () => {
    vi.spyOn(client.api, "getActivityCalendar").mockResolvedValue(cal(SOFT));
    renderCard();
    expect(await screen.findByText(/poor seeing/)).toBeInTheDocument();
  });

  it("keeps the baseline singular when there is only one night behind it", async () => {
    vi.spyOn(client.api, "getActivityCalendar")
      .mockResolvedValue(cal({ ...SOFT, baseline_nights: 1 }));
    renderCard();
    expect(await screen.findByText(/previous 1 measured night\./))
      .toBeInTheDocument();
  });

  it("renders nothing on a normal night", async () => {
    vi.spyOn(client.api, "getActivityCalendar").mockResolvedValue(cal(null));
    renderCard();
    await waitFor(() =>
      expect(client.api.getActivityCalendar).toHaveBeenCalled());
    expect(screen.queryByTestId("off-night")).not.toBeInTheDocument();
  });

  it("renders nothing against an older backend that doesn't send the field", async () => {
    const older = cal(null);
    delete (older as Partial<ActivityCalendar>).off_night;
    vi.spyOn(client.api, "getActivityCalendar").mockResolvedValue(older);
    renderCard();
    await waitFor(() =>
      expect(client.api.getActivityCalendar).toHaveBeenCalled());
    expect(screen.queryByTestId("off-night")).not.toBeInTheDocument();
  });

  it("swallows a failed fetch rather than showing an error", async () => {
    vi.spyOn(client.api, "getActivityCalendar")
      .mockRejectedValue(new Error("nope"));
    renderCard();
    await waitFor(() =>
      expect(client.api.getActivityCalendar).toHaveBeenCalled());
    expect(screen.queryByTestId("off-night")).not.toBeInTheDocument();
  });
});
