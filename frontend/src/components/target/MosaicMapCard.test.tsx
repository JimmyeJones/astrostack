import { MantineProvider } from "@mantine/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { MosaicMapCard } from "./MosaicMapCard";
import { panelGrid, panelShade, panelTooltip } from "./mosaicMap";
import type { MosaicDepthMap, MosaicPanel } from "../../api/client";
import * as client from "../../api/client";

function panel(over: Partial<MosaicPanel> = {}): MosaicPanel {
  return {
    row: 0, col: 0, n_frames: 120, exposure_s: 1200,
    ra_deg: 200, dec_deg: 30, ...over,
  };
}

/** An even 2×2 mosaic unless `thin` says otherwise. */
function map(over: Partial<MosaicDepthMap> = {}): MosaicDepthMap {
  return {
    rows: 2,
    cols: 2,
    panels: [
      panel({ row: 0, col: 0 }),
      panel({ row: 0, col: 1 }),
      panel({ row: 1, col: 0 }),
      panel({ row: 1, col: 1 }),
    ],
    median_exposure_s: 1200,
    thin: null,
    text: "All 4 panels of your 2×2 mosaic have had a similar amount of time.",
    ...over,
  };
}

function renderCard(safe = "M_42") {
  return render(
    <MantineProvider>
      <QueryClientProvider client={new QueryClient()}>
        <MosaicMapCard safe={safe} />
      </QueryClientProvider>
    </MantineProvider>,
  );
}

afterEach(() => vi.restoreAllMocks());

describe("MosaicMapCard", () => {
  it("draws one cell per panel with the verdict above it", async () => {
    vi.spyOn(client.api, "mosaicMap").mockResolvedValue(map());
    renderCard();

    await screen.findByText("Your mosaic, panel by panel");
    expect(screen.getByText(/similar amount of time/)).toBeTruthy();
    const grid = screen.getByTestId("mosaic-panel-grid");
    expect(grid.children.length).toBe(4);
  });

  it("marks the thin panel and says so in each cell's label", async () => {
    const thin = panel({ row: 1, col: 1, n_frames: 8, exposure_s: 80 });
    vi.spyOn(client.api, "mosaicMap").mockResolvedValue(
      map({
        panels: [
          panel({ row: 0, col: 0 }), panel({ row: 0, col: 1 }),
          panel({ row: 1, col: 0 }), thin,
        ],
        thin,
        text: "Your 2×2 mosaic is thinnest at the bottom-right.",
      }),
    );
    renderCard();

    await screen.findByText(/thinnest at the bottom-right/);
    expect(screen.getByText("thin")).toBeTruthy();
    // The map is readable without a pointer: every cell carries its numbers.
    expect(screen.getByLabelText("1 min over 8 subs — the thinnest panel")).toBeTruthy();
    expect(screen.getAllByLabelText("20 min over 120 subs").length).toBe(3);
  });

  it("renders nothing at all when the target isn't a mosaic", async () => {
    vi.spyOn(client.api, "mosaicMap").mockResolvedValue(null);
    renderCard();

    await waitFor(() => expect(client.api.mosaicMap).toHaveBeenCalled());
    expect(screen.queryByText("Your mosaic, panel by panel")).toBeNull();
    expect(screen.queryByTestId("mosaic-panel-grid")).toBeNull();
  });

  it("stays silent against a backend that has no such endpoint", async () => {
    vi.spyOn(client.api, "mosaicMap").mockRejectedValue(new Error("404 Not Found"));
    renderCard();

    await waitFor(() => expect(client.api.mosaicMap).toHaveBeenCalled());
    expect(screen.queryByText("Your mosaic, panel by panel")).toBeNull();
    expect(screen.queryByTestId("mosaic-panel-grid")).toBeNull();
  });
});

describe("panelGrid", () => {
  it("places every panel at its own row and column", () => {
    const grid = panelGrid(map());
    expect(grid.length).toBe(2);
    expect(grid[0].length).toBe(2);
    expect(grid[1][1]).not.toBeNull();
  });

  it("leaves a gap where an L-shaped mosaic has no panel", () => {
    const grid = panelGrid(map({
      panels: [panel({ row: 0, col: 0 }), panel({ row: 1, col: 0 }),
               panel({ row: 1, col: 1 })],
    }));

    expect(grid[0][1]).toBeNull();      // the missing corner stays a hole…
    expect(grid[1][1]).not.toBeNull();  // …and nothing slides into it
  });

  it("ignores a panel outside the stated grid rather than throwing", () => {
    const grid = panelGrid(map({ panels: [panel({ row: 9, col: 9 })] }));
    expect(grid.flat().every((c) => c === null)).toBe(true);
  });
});

describe("panelShade", () => {
  it("shades against this mosaic's own range, deepest solid", () => {
    const thin = panel({ row: 1, col: 1, exposure_s: 200 });
    const m = map({
      panels: [panel({ exposure_s: 1200 }), thin],
      thin,
    });

    expect(panelShade(m.panels[0], m)).toBe(1);
    expect(panelShade(thin, m)).toBe(0);
  });

  it("puts an even mosaic at the top of the scale, not the bottom", () => {
    // Every panel equal: there is nothing behind, and the map should read that
    // way rather than rendering a flat wash of "thin".
    const m = map();
    expect(panelShade(m.panels[0], m)).toBe(1);
  });
});

describe("panelTooltip", () => {
  it("gives the time and the sub count, and names the thin panel", () => {
    const thin = panel({ row: 1, col: 1, n_frames: 8, exposure_s: 80 });
    const m = map({ panels: [panel(), thin], thin });

    expect(panelTooltip(m.panels[0], m)).toBe("20 min over 120 subs");
    expect(panelTooltip(thin, m)).toBe("1 min over 8 subs — the thinnest panel");
  });

  it("says 'sub' once, not '1 subs'", () => {
    const m = map({ panels: [panel({ n_frames: 1, exposure_s: 10 })] });
    expect(panelTooltip(m.panels[0], m)).toBe("10 s over 1 sub");
  });
});
