import { MantineProvider } from "@mantine/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";
import { DeepeningReelCard } from "./DeepeningReelCard";
import * as client from "../api/client";

function renderCard(safe = "M_31", name = "M31") {
  return render(
    <MantineProvider>
      <QueryClientProvider client={new QueryClient()}>
        {/* The offer branch links into the Stack form, so the card needs a
            router around it — the reel branch is unaffected. */}
        <MemoryRouter>
          <DeepeningReelCard safe={safe} name={name} />
        </MemoryRouter>
      </QueryClientProvider>
    </MantineProvider>,
  );
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("DeepeningReelCard", () => {
  it("renders nothing until a target has two stacks", async () => {
    vi.spyOn(client.api, "deepeningReelInfo").mockResolvedValue({
      available: false, n_stacks: 1,
    });
    const { container } = renderCard();
    await waitFor(() => expect(client.api.deepeningReelInfo).toHaveBeenCalled());
    expect(container.querySelector(".mantine-Paper-root")).toBeNull();
  });

  it("shows the deepening arc and reveals the animation on Play", async () => {
    vi.spyOn(client.api, "deepeningReelInfo").mockResolvedValue({
      available: true, n_stacks: 3,
      first_subs: 120, last_subs: 1240,
      first_utc: "2026-06-28T00:00:00Z", last_utc: "2026-07-28T00:00:00Z",
      format: "webp",
    });
    renderCard("M_31", "M31");
    await waitFor(() =>
      expect(screen.getByText("Your target, night after night")).toBeInTheDocument());
    // The depth gain is surfaced in the plain-language blurb.
    expect(screen.getByText(/1,240/)).toBeInTheDocument();
    // Collapsed: no animation fetched up front.
    expect(document.querySelector("img")).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: /play/i }));
    const img = await screen.findByRole("img");
    expect(img).toHaveAttribute("src", "/api/targets/M_31/deepening-reel");
    // The provenance caption appears under the animation.
    expect(screen.getByText(/120 → 1,240 subs/)).toBeInTheDocument();
    const dl = screen.getByRole("link", { name: /download clip/i });
    expect(dl).toHaveAttribute("href", "/api/targets/M_31/deepening-reel");
  });

  it("offers to build the reel on a target stacked once across several nights", async () => {
    // The whole point of the offer: the subs are already there, and the only
    // reason there is no clip is a switch that is advanced and off by default.
    vi.spyOn(client.api, "deepeningReelInfo").mockResolvedValue({
      available: false, n_stacks: 1,
      reel_offer: { run_id: 12, nights: 6, subs: 1234, last_duration_s: 1500 },
    });
    renderCard("M_31", "M31");
    await waitFor(() =>
      expect(screen.getByText("Your target, night after night")).toBeInTheDocument());
    expect(screen.getByText(/all 6/)).toBeInTheDocument();
    // The cost and the consequence, both on screen before the button.
    expect(screen.getByText(/25 min/)).toBeInTheDocument();
    expect(screen.getByText(/stays in History/)).toBeInTheDocument();
    // It sets the form up; it does not start a job.
    expect(screen.queryByRole("button", { name: /play/i })).toBeNull();
    expect(screen.getByRole("link", { name: /set up that stack/i }))
      .toHaveAttribute("href", "/targets/M_31/stack?from=12&open=advanced&reel=1");
  });

  it("still renders nothing when the backend offers nothing", async () => {
    // An older backend (no field at all) and a target the offer declines both
    // read the same way — silence, exactly as before this existed.
    for (const info of [
      { available: false, n_stacks: 1 },
      { available: false, n_stacks: 1, reel_offer: null },
    ] as const) {
      vi.spyOn(client.api, "deepeningReelInfo").mockResolvedValue(info);
      const { container, unmount } = renderCard();
      await waitFor(() => expect(client.api.deepeningReelInfo).toHaveBeenCalled());
      expect(container.querySelector(".mantine-Paper-root")).toBeNull();
      unmount();
      vi.restoreAllMocks();
    }
  });
});
