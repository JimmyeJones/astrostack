import { MantineProvider } from "@mantine/core";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { CompareWithLastCard } from "./CompareWithLastCard";
import type { StackRun } from "../api/client";

function run(id: number, over: Partial<StackRun> = {}): StackRun {
  return {
    id,
    timestamp_utc: "2026-05-02T00:00:00Z",
    n_frames_used: 100,
    canvas_w: 1000,
    canvas_h: 800,
    has_preview: true,
    has_fits: true,
    has_tiff: false,
    ...over,
  } as StackRun;
}

function renderCard(runs?: StackRun[] | null) {
  return render(
    <MantineProvider>
      <MemoryRouter>
        <CompareWithLastCard safe="M_42" runs={runs} />
      </MemoryRouter>
    </MantineProvider>,
  );
}

describe("CompareWithLastCard", () => {
  it("renders nothing at all until there are two pictures to compare", () => {
    const { container } = renderCard([run(9)]);
    expect(container.querySelector(".mantine-Paper-root")).toBeNull();
    expect(screen.queryByTestId("compare-with-last")).toBeNull();
    // …which is what keeps the Story tab itself hidden (InsightTabs measures DOM).
    renderCard(undefined);
    expect(screen.queryByTestId("compare-with-last")).toBeNull();
  });

  it("links the newest picture against the one before it", () => {
    renderCard([run(9), run(7), run(3)]);
    const link = screen.getByRole("link", { name: /Compare with my last one/ });
    expect(link).toHaveAttribute("href", "/compare?a=M_42:9&b=M_42:7");
  });

  it("names the two nights by when the subs were SHOT, not when the stack ran", () => {
    // A re-stack of a back catalogue runs years after the capture; dating the
    // sides by `timestamp_utc` would say they were both taken today.
    renderCard([
      run(9, {
        capture_night_start: "2024-11-18T20:00:00Z",
        capture_night_end: "2024-11-18T23:00:00Z",
        capture_nights: 1,
      }),
      run(7, {
        capture_night_start: "2024-11-15T20:00:00Z",
        capture_night_end: "2024-11-15T23:00:00Z",
        capture_nights: 1,
      }),
    ]);
    expect(screen.getByTestId("compare-with-last")).toHaveTextContent(/2024/);
    expect(screen.getByTestId("compare-with-last")).not.toHaveTextContent(/2026/);
  });

  it("still offers the link when neither run carries a usable date", () => {
    renderCard([run(9), run(7)]);
    expect(screen.getByRole("link", { name: /Compare with my last one/ }))
      .toHaveAttribute("href", "/compare?a=M_42:9&b=M_42:7");
  });
});
