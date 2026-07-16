import { MantineProvider } from "@mantine/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ProgressReelCard } from "./ProgressReelCard";
import * as client from "../api/client";

function renderCard(safe = "M_42", runId = 7) {
  return render(
    <MantineProvider>
      <QueryClientProvider client={new QueryClient()}>
        <ProgressReelCard safe={safe} runId={runId} />
      </QueryClientProvider>
    </MantineProvider>,
  );
}

afterEach(() => {
  vi.restoreAllMocks();
  const nav = navigator as unknown as Record<string, unknown>;
  delete nav.canShare;
  delete nav.share;
});

describe("ProgressReelCard", () => {
  it("renders nothing when the run has no reel", async () => {
    vi.spyOn(client.api, "stackProgressInfo").mockResolvedValue({
      available: false, frames: 0, format: "",
    });
    const { container } = renderCard();
    await waitFor(() => expect(client.api.stackProgressInfo).toHaveBeenCalled());
    expect(container.querySelector(".mantine-Paper-root")).toBeNull();
  });

  it("shows the reel and reveals the animation on Play", async () => {
    vi.spyOn(client.api, "stackProgressInfo").mockResolvedValue({
      available: true, frames: 8, format: "webp",
    });
    renderCard("M_42", 7);
    await waitFor(() =>
      expect(screen.getByText("Watch your picture appear")).toBeInTheDocument());
    // The frame count is surfaced in the plain-language blurb.
    expect(screen.getByText(/8 frames/)).toBeInTheDocument();
    // Collapsed: no image yet (History lists many runs — don't fetch each up front).
    expect(document.querySelector("img")).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: /play/i }));
    // After Play, the animation <img> and a download link point at the reel URL.
    const img = await screen.findByRole("img");
    expect(img).toHaveAttribute("src", "/api/targets/M_42/stack-runs/7/progress");
    const dl = screen.getByRole("link", { name: /download clip/i });
    expect(dl).toHaveAttribute("href", "/api/targets/M_42/stack-runs/7/progress");
    // On a browser without file-share, the Share control is absent (progressive
    // enhancement) — only the download link is offered.
    expect(screen.queryByRole("button", { name: "Share clip" })).not.toBeInTheDocument();
  });

  it("offers a Share clip control when the browser can share files", async () => {
    const nav = navigator as unknown as Record<string, unknown>;
    nav.canShare = () => true;
    nav.share = async () => {};
    vi.spyOn(client.api, "stackProgressInfo").mockResolvedValue({
      available: true, frames: 8, format: "webp",
    });
    renderCard("M_42", 7);
    await waitFor(() =>
      expect(screen.getByText("Watch your picture appear")).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: /play/i }));
    // The Share control appears alongside Download once the clip is revealed.
    expect(await screen.findByRole("button", { name: "Share clip" })).toBeInTheDocument();
  });
});
