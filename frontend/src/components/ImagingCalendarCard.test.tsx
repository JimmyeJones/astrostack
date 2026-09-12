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
    // Three nights, not two: with two, "the night before the most recent" and
    // "the oldest night" are the same cell, and an arrow-key test cannot tell a
    // one-night step from a jump to the far end of the grid.
    nights: [
      { date: "2026-07-03", exposure_s: 1800, n_frames: 15, targets: ["M13"] },
      { date: "2026-07-10", exposure_s: 3600, n_frames: 30, targets: ["M31"] },
      { date: "2026-07-20", exposure_s: 600, n_frames: 5, targets: ["M42"] },
    ],
    n_nights: 3,
    total_exposure_s: 6000,
    nights_this_month: 3,
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
    expect(screen.getByText(/imaged 3 nights this month/)).toBeInTheDocument();
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

    // ArrowLeft steps ONE night back from where the focus is — 10 Jul, not the
    // oldest night in the grid. Stepping from "nothing is picked" instead of
    // from the focused cell would answer this press by jumping to 3 Jul.
    fireEvent.keyDown(recent, { key: "ArrowLeft" });
    expect(await screen.findByText(/10 Jul 2026 · 1\.0 h across M31/))
      .toBeInTheDocument();
    expect(screen.getByRole("button", { name: /10 Jul 2026/ }))
      .toHaveAttribute("tabindex", "0");

    // …and it stops at the oldest night rather than wrapping round the year.
    fireEvent.keyDown(screen.getByRole("button", { name: /10 Jul 2026/ }),
      { key: "ArrowLeft" });
    expect(await screen.findByText(/3 Jul 2026 · .* across M13/))
      .toBeInTheDocument();
    fireEvent.keyDown(screen.getByRole("button", { name: /3 Jul 2026/ }),
      { key: "ArrowLeft" });
    expect(screen.getByText(/3 Jul 2026 · .* across M13/)).toBeInTheDocument();
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
