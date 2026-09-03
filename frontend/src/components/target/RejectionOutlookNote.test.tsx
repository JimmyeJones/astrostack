import { MantineProvider } from "@mantine/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import * as client from "../../api/client";
import type { RejectionOutlook } from "../../api/client";
import { RejectionOutlookNote } from "./RejectionOutlookNote";

function outlook(over: Partial<RejectionOutlook> = {}): RejectionOutlook {
  return {
    method: "sigma-clip",
    n_frames: 6,
    panel_depth: null,
    lone_outlier_min_frames: 11,
    reaches: false,
    user_chose: true,
    ...over,
  };
}

function renderNote(streaked: number) {
  return render(
    <MantineProvider>
      <MemoryRouter>
        <QueryClientProvider client={new QueryClient()}>
          <RejectionOutlookNote safe="m_42" streaked={streaked} />
        </QueryClientProvider>
      </MemoryRouter>
    </MantineProvider>,
  );
}

/** Let the query resolve (or reject) before asserting the note stayed away. */
const settle = () => act(async () => { await Promise.resolve(); });

afterEach(() => vi.restoreAllMocks());

describe("RejectionOutlookNote", () => {
  it("warns, and points at the form where the setting lives", async () => {
    vi.spyOn(client.api, "rejectionOutlook").mockResolvedValue(outlook());
    renderNote(2);

    await waitFor(() =>
      expect(screen.getByTestId("rejection-outlook-note")).toBeInTheDocument());
    expect(screen.getByRole("link", { name: /Change how this target stacks/ }))
      .toHaveAttribute("href", "/targets/m_42/stack");
  });

  it("also offers the one-time fix that covers every target", async () => {
    // Per-target is the narrow answer; a walk-away owner wants the switch that
    // hands the choice back to the app on every hands-off stack — and will never
    // find a Settings toggle by name. It must land on the section that holds it.
    vi.spyOn(client.api, "rejectionOutlook").mockResolvedValue(outlook());
    renderNote(2);

    const link = await screen.findByRole(
      "link", { name: /Let AstroStack choose on every hands-off stack/ });
    expect(link).toHaveAttribute("href", "/settings/automation");
  });

  it("never asks the question when nothing carries a trail", async () => {
    const spy = vi.spyOn(client.api, "rejectionOutlook")
      .mockResolvedValue(outlook());
    renderNote(0);
    await settle();
    expect(screen.queryByTestId("rejection-outlook-note")).toBeNull();
    expect(spy).not.toHaveBeenCalled();
  });

  it("renders nothing when the fetch fails", async () => {
    vi.spyOn(client.api, "rejectionOutlook")
      .mockRejectedValue(new Error("older backend"));
    renderNote(3);
    await settle();
    expect(screen.queryByTestId("rejection-outlook-note")).toBeNull();
  });

  it("renders nothing when the saved rejection does reach", async () => {
    vi.spyOn(client.api, "rejectionOutlook")
      .mockResolvedValue(outlook({ reaches: true }));
    renderNote(3);
    await settle();
    expect(screen.queryByTestId("rejection-outlook-note")).toBeNull();
  });
});
