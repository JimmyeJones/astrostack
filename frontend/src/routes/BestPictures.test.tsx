import { MantineProvider } from "@mantine/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { BestPicturesView } from "./BestPictures";
import * as client from "../api/client";
import type { BestPicture } from "../api/client";

function pic(over: Partial<BestPicture>): BestPicture {
  return {
    safe: "m31", target_name: "M31", run_id: 1, output_basename: "master",
    timestamp_utc: "2026-05-02T00:00:00Z", n_frames_used: 500,
    canvas_w: 480, canvas_h: 320, total_exposure_s: 12240, noise_sigma: 0.02,
    has_preview: true, has_fits: false, has_tiff: false,
    preview_url: "/api/targets/m31/stack-runs/1/preview", score: 1, ...over,
  };
}

function renderWall() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <MantineProvider>
      <QueryClientProvider client={qc}>
        <MemoryRouter><BestPicturesView /></MemoryRouter>
      </QueryClientProvider>
    </MantineProvider>,
  );
}

afterEach(() => vi.restoreAllMocks());

describe("BestPicturesView", () => {
  it("renders the ranked wall with target names and reason lines", async () => {
    vi.spyOn(client.api, "getGalleryBest").mockResolvedValue({
      items: [
        pic({ safe: "m31", target_name: "M31", run_id: 1, total_exposure_s: 12240, n_frames_used: 500 }),
        pic({ safe: "m42", target_name: "M42", run_id: 2, total_exposure_s: 3600, n_frames_used: 120, score: 0.6 }),
      ],
    });
    renderWall();
    await waitFor(() => expect(screen.getByText("M31")).toBeInTheDocument());
    expect(screen.getByText("M42")).toBeInTheDocument();
    // The "why it's good" line blends integration time and frame count.
    expect(screen.getByText("3.4 h · 500 frames")).toBeInTheDocument();
    // The top three carry a rank chip.
    expect(screen.getByText("#1")).toBeInTheDocument();
    expect(screen.getByText("#2")).toBeInTheDocument();
  });

  it("shows a friendly empty state when the wall self-hides", async () => {
    vi.spyOn(client.api, "getGalleryBest").mockResolvedValue({ items: [] });
    renderWall();
    await waitFor(() =>
      expect(screen.getByText(/your best pictures will gather here/i)).toBeInTheDocument());
  });
});
