import { MantineProvider } from "@mantine/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { DeepeningReelCard } from "./DeepeningReelCard";
import * as client from "../api/client";

function renderCard(safe = "M_31", name = "M31") {
  return render(
    <MantineProvider>
      <QueryClientProvider client={new QueryClient()}>
        <DeepeningReelCard safe={safe} name={name} />
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
});
