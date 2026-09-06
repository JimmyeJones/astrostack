import { MantineProvider } from "@mantine/core";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";

import { RejectionBreakdownCard } from "./RejectionBreakdownCard";
import type { RejectionSummary } from "../../api/client";

function summary(over: Partial<RejectionSummary> = {}): RejectionSummary {
  return {
    used: 412,
    dropped: 88,
    dropped_fraction: 0.176,
    verdict: { tone: "ok", key: "minor", text: "A few frames didn't make the cut." },
    buckets: [{
      key: "solve_timeout",
      label: "Ran out of time being located",
      count: 88,
      note: "…raise the ASTAP timeout in Settings and run Plate Solve again.",
    }],
    ...over,
  };
}

function renderCard(s: RejectionSummary | null | undefined) {
  return render(
    <MantineProvider>
      <MemoryRouter>
        <RejectionBreakdownCard summary={s} />
      </MemoryRouter>
    </MantineProvider>,
  );
}

describe("RejectionBreakdownCard", () => {
  it("gives the breakdown a home a finger can reach, with its advice clickable", () => {
    renderCard(summary());
    expect(screen.getByText("Why some frames were left out")).toBeInTheDocument();
    expect(screen.getByText("Ran out of time being located")).toBeInTheDocument();
    expect(screen.getByText("Open plate-solving settings →"))
      .toHaveAttribute("href", "/settings/plate-solving");
  });

  it("renders nothing when nothing was left out", () => {
    const { container } = renderCard(summary({ buckets: [] }));
    expect(container.querySelector(".mantine-Paper-root")).toBeNull();
  });

  it("renders nothing without a summary (older backend, or still loading)", () => {
    expect(renderCard(undefined).container.querySelector(".mantine-Paper-root")).toBeNull();
    expect(renderCard(null).container.querySelector(".mantine-Paper-root")).toBeNull();
  });
});
