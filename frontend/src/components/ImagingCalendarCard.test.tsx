import { MantineProvider } from "@mantine/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { CALENDAR_PROMPT, ImagingCalendarCard } from "./ImagingCalendarCard";
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

  it("names the night a tap lands on, where 'Less … More' already sat", async () => {
    // Fail-before: every night's date, hours and targets lived in a hover-only
    // `Tooltip` on an 11 px square. On the phone this app is mostly read on, the
    // heatmap was a grid of colours with no way to ask about any of them.
    vi.spyOn(client.api, "getActivityCalendar").mockResolvedValue(cal());
    renderCard();
    await screen.findByText("Your imaging calendar");

    // Before anything is picked the slot invites the tap rather than sitting empty.
    expect(screen.getByText(CALENDAR_PROMPT)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /10 Jul 2026/ }));
    expect(await screen.findByText(/10 Jul 2026 · 1\.0 h across M31/))
      .toBeInTheDocument();
    expect(screen.queryByText(CALENDAR_PROMPT)).toBeNull();
    // The legend stays put — the read-out shares its row rather than adding one.
    expect(screen.getByText("Less")).toBeInTheDocument();
  });

  it("puts one night in the tab order, and the arrow keys walk the rest", async () => {
    vi.spyOn(client.api, "getActivityCalendar").mockResolvedValue(cal());
    renderCard();
    await screen.findByText("Your imaging calendar");

    // A tab stop per night would put one on the Dashboard for every night the
    // owner has ever imaged; exactly one cell is reachable, the most recent.
    const nights = screen.getAllByRole("button");
    expect(nights.map((n) => n.getAttribute("tabindex")).filter((t) => t === "0"))
      .toEqual(["0"]);
    const recent = screen.getByRole("button", { name: /20 Jul 2026/ });
    expect(recent).toHaveAttribute("tabindex", "0");

    // ArrowLeft steps to the earlier night, and the read-out follows.
    fireEvent.keyDown(recent, { key: "ArrowLeft" });
    expect(await screen.findByText(/10 Jul 2026 · 1\.0 h across M31/))
      .toBeInTheDocument();
    expect(screen.getByRole("button", { name: /10 Jul 2026/ }))
      .toHaveAttribute("tabindex", "0");

    // …and it stops at the oldest night rather than wrapping round the year.
    fireEvent.keyDown(screen.getByRole("button", { name: /10 Jul 2026/ }),
      { key: "ArrowLeft" });
    expect(screen.getByText(/10 Jul 2026 · 1\.0 h across M31/)).toBeInTheDocument();
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
