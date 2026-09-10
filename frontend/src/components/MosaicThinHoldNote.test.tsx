import { MantineProvider } from "@mantine/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { MosaicThinHoldNote } from "./MosaicThinHoldNote";
import * as client from "../api/client";

function renderNote() {
  return render(
    <MantineProvider>
      <QueryClientProvider client={new QueryClient()}>
        <MosaicThinHoldNote safe="m_42" />
      </QueryClientProvider>
    </MantineProvider>,
  );
}

afterEach(() => vi.restoreAllMocks());

describe("MosaicThinHoldNote", () => {
  it("explains a mosaic held on depth in the numbers the scan recorded", async () => {
    vi.spyOn(client.api, "autoStackThinHold").mockResolvedValue({
      frames: 9, min_frames: 3, panel_depth: 1, panels: 9,
      when_utc: "2026-09-10T02:00:00Z",
    });
    renderNote();

    await waitFor(() =>
      expect(screen.getByTestId("mosaic-thin-hold-note")).toBeInTheDocument());
    // The whole point: it must NOT send a mosaic owner at Plate Solve. Their
    // subs are located; what is missing is time on each panel.
    expect(screen.getByText(/All 9 of your subs are located/)).toBeInTheDocument();
    expect(screen.getByText(/spread over 9 panels/)).toBeInTheDocument();
    expect(screen.getByText(/only 1 sub on it/)).toBeInTheDocument();
    expect(screen.getByText(/at least 3/)).toBeInTheDocument();
    expect(screen.queryByText(/Plate Solve/)).not.toBeInTheDocument();
  });

  it("pluralises the depth once a panel has more than one sub", async () => {
    vi.spyOn(client.api, "autoStackThinHold").mockResolvedValue({
      frames: 8, min_frames: 3, panel_depth: 2, panels: 4,
    });
    renderNote();
    await waitFor(() =>
      expect(screen.getByText(/only 2 subs on it/)).toBeInTheDocument());
  });

  it("says nothing for a hold that is not about panels", async () => {
    // A single field held on its plain count is already explained by the
    // Target page's own "waiting for more of your subs to be located" note —
    // two notices for one hold is the banner-piling the owner complained about.
    vi.spyOn(client.api, "autoStackThinHold").mockResolvedValue({
      frames: 2, min_frames: 3, panel_depth: 0, panels: 0,
    });
    renderNote();
    await waitFor(() => expect(client.api.autoStackThinHold).toHaveBeenCalled());
    expect(screen.queryByTestId("mosaic-thin-hold-note")).not.toBeInTheDocument();
  });

  it("says nothing when the newest scan held nothing back", async () => {
    vi.spyOn(client.api, "autoStackThinHold").mockResolvedValue(null);
    renderNote();
    await waitFor(() => expect(client.api.autoStackThinHold).toHaveBeenCalled());
    expect(screen.queryByTestId("mosaic-thin-hold-note")).not.toBeInTheDocument();
  });

  it("says nothing against an older backend that has no such endpoint", async () => {
    vi.spyOn(client.api, "autoStackThinHold").mockRejectedValue(new Error("404"));
    renderNote();
    await waitFor(() => expect(client.api.autoStackThinHold).toHaveBeenCalled());
    expect(screen.queryByTestId("mosaic-thin-hold-note")).not.toBeInTheDocument();
  });
});
