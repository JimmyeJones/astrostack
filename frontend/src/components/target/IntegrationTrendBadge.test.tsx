import { MantineProvider } from "@mantine/core";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { IntegrationTrendBadge } from "./IntegrationTrendBadge";
import type { NextBestMoveKind } from "./nextBestMove";

// Two measured stacks spanning a real time increase whose noise barely fell —
// integrationTrend reads this as a plateau (sky-limited, exponent ≈ 0).
const PLATEAUED = [
  { total_exposure_s: 3600, noise_sigma: 0.1 },
  { total_exposure_s: 14400, noise_sigma: 0.098 },
];
// Noise halved as time quadrupled — tracking the ideal √t, so "improving".
const IMPROVING = [
  { total_exposure_s: 3600, noise_sigma: 0.2 },
  { total_exposure_s: 14400, noise_sigma: 0.1 },
];

function renderBadge(props: {
  runs?: { total_exposure_s?: number | null; noise_sigma?: number | null }[] | null;
  coachKind?: NextBestMoveKind | null;
}) {
  return render(
    <MantineProvider>
      <IntegrationTrendBadge runs={props.runs ?? null} coachKind={props.coachKind ?? null} />
    </MantineProvider>,
  );
}

describe("IntegrationTrendBadge", () => {
  it("shows the plateau verdict when the target has gone sky-limited", () => {
    renderBadge({ runs: PLATEAUED });
    expect(screen.getByText(/About as clean as your sky allows/)).toBeInTheDocument();
    expect(screen.getByText(/sky-limited/)).toBeInTheDocument();
  });

  it("is suppressed while the coaching is nudging to add more time (integration)", () => {
    renderBadge({ runs: PLATEAUED, coachKind: "integration" });
    expect(screen.queryByText(/sky allows/)).toBeNull();
  });

  it("is suppressed while the coaching shows the 'good, add time' note", () => {
    renderBadge({ runs: PLATEAUED, coachKind: "good" });
    expect(screen.queryByText(/sky allows/)).toBeNull();
  });

  it("still shows beside a non-add-time coaching tip (e.g. locate)", () => {
    renderBadge({ runs: PLATEAUED, coachKind: "locate" });
    expect(screen.getByText(/About as clean as your sky allows/)).toBeInTheDocument();
  });

  it("renders nothing for an improving target (that verdict stays History-only)", () => {
    renderBadge({ runs: IMPROVING });
    expect(screen.queryByText(/sky allows/)).toBeNull();
  });

  it("renders nothing without enough measured history to judge the trend", () => {
    renderBadge({ runs: [{ total_exposure_s: 3600, noise_sigma: 0.1 }] });
    expect(screen.queryByText(/sky allows/)).toBeNull();
  });
});
