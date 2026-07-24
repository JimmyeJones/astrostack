import { describe, expect, it } from "vitest";
import type { ActivityCalendar } from "./api/client";
import {
  buildCalendarGrid,
  calendarHeadline,
  exposureLevel,
  nightLabel,
} from "./activityCalendar";

function cal(over: Partial<ActivityCalendar>): ActivityCalendar {
  return {
    start_date: "2026-07-01",
    end_date: "2026-07-24",
    months: 12,
    nights: [],
    n_nights: 0,
    total_exposure_s: 0,
    nights_this_month: 0,
    best_streak_nights: 0,
    ...over,
  };
}

describe("exposureLevel", () => {
  it("buckets by hours", () => {
    expect(exposureLevel(0)).toBe(0);
    expect(exposureLevel(60)).toBe(1); // 1 min
    expect(exposureLevel(0.6 * 3600)).toBe(2);
    expect(exposureLevel(2 * 3600)).toBe(3);
    expect(exposureLevel(5 * 3600)).toBe(4);
  });
});

describe("buildCalendarGrid", () => {
  it("produces full-height week columns and marks imaged nights", () => {
    const c = cal({
      start_date: "2026-07-01", // a Wednesday (getUTCDay = 3)
      end_date: "2026-07-14",
      nights: [
        { date: "2026-07-02", exposure_s: 3600, n_frames: 10, targets: ["M31"] },
        { date: "2026-07-10", exposure_s: 600, n_frames: 5, targets: ["M42"] },
      ],
    });
    const grid = buildCalendarGrid(c);
    // Every column is 7 tall.
    for (const week of grid) expect(week).toHaveLength(7);
    // Leading days before the Wednesday start are padding (date null).
    expect(grid[0][0].date).toBeNull(); // Sunday 2026-06-28
    expect(grid[0][3].date).toBe("2026-07-01"); // Wednesday
    // The imaged nights land on real cells with a non-zero shade.
    const cells = grid.flat().filter((d) => d.night);
    expect(cells.map((d) => d.date).sort()).toEqual(["2026-07-02", "2026-07-10"]);
    expect(cells.find((d) => d.date === "2026-07-02")!.level).toBe(2);
  });

  it("returns an empty grid when the window is degenerate", () => {
    expect(buildCalendarGrid(cal({ start_date: "2026-07-24", end_date: "2026-07-01" }))).toEqual(
      [],
    );
  });

  it("never places a night on the wrong weekday", () => {
    // 2026-07-02 is a Thursday → getUTCDay 4.
    const grid = buildCalendarGrid(
      cal({
        start_date: "2026-07-01",
        end_date: "2026-07-07",
        nights: [{ date: "2026-07-02", exposure_s: 60, n_frames: 1, targets: ["A"] }],
      }),
    );
    const cell = grid.flat().find((d) => d.date === "2026-07-02")!;
    // Its row index within its column must be Thursday = 4.
    const col = grid.find((w) => w.includes(cell))!;
    expect(col.indexOf(cell)).toBe(4);
  });
});

describe("calendarHeadline", () => {
  it("is empty when nothing has been imaged", () => {
    expect(calendarHeadline(cal({}))).toBe("");
  });

  it("leads with this month and adds a streak when there is one", () => {
    expect(
      calendarHeadline(cal({ n_nights: 20, nights_this_month: 14, best_streak_nights: 5 })),
    ).toBe("You've imaged 14 nights this month — best run: 5 clear nights in a row.");
  });

  it("singularises one night and omits a trivial streak", () => {
    expect(
      calendarHeadline(cal({ n_nights: 1, nights_this_month: 1, best_streak_nights: 1 })),
    ).toBe("You've imaged 1 night this month.");
  });

  it("falls back to the window when nothing this month", () => {
    expect(
      calendarHeadline(cal({ n_nights: 3, nights_this_month: 0, best_streak_nights: 1, months: 12 })),
    ).toBe("You've imaged 3 nights in the last 12 months.");
  });
});

describe("nightLabel", () => {
  it("formats the date, integration and targets", () => {
    const label = nightLabel(
      { date: "2026-07-12", exposure_s: 8280, n_frames: 40, targets: ["M31", "M42"] },
      (s) => `${(s / 3600).toFixed(1)} h`,
    );
    expect(label).toBe("12 Jul 2026 · 2.3 h across M31, M42");
  });
});
