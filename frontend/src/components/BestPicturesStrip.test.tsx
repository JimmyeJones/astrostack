import { MantineProvider } from "@mantine/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { BestPicturesStrip } from "./BestPicturesStrip";
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

function renderStrip() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <MantineProvider>
      <QueryClientProvider client={qc}>
        <MemoryRouter><BestPicturesStrip /></MemoryRouter>
      </QueryClientProvider>
    </MantineProvider>,
  );
}

afterEach(() => vi.restoreAllMocks());

describe("BestPicturesStrip", () => {
  it("renders the top few pictures with their reason lines", async () => {
    vi.spyOn(client.api, "getGalleryBest").mockResolvedValue({
      items: [pic({}), pic({ safe: "m42", target_name: "M42", run_id: 2, score: 0.6 })],
    });
    renderStrip();
    await waitFor(() => expect(screen.getByText("M31")).toBeInTheDocument());
    expect(screen.getByText("M42")).toBeInTheDocument();
    expect(screen.getAllByText("3.4 h · 500 frames").length).toBeGreaterThan(0);
  });

  it("stars a pinned favourite, so leading the strip isn't a mystery", async () => {
    vi.spyOn(client.api, "getGalleryBest").mockResolvedValue({
      items: [
        pic({ safe: "m42", target_name: "M42", run_id: 2, score: 0.4, pinned: true }),
        pic({}),
      ],
    });
    const { container } = renderStrip();
    await waitFor(() => expect(screen.getByText("M42")).toBeInTheDocument());
    const stars = container.querySelectorAll("svg title");
    expect(stars).toHaveLength(1);  // only the pinned card carries one
    expect(stars[0].textContent).toContain("M42");
  });

  it("shows no star when nothing is pinned", async () => {
    vi.spyOn(client.api, "getGalleryBest").mockResolvedValue({
      items: [pic({}), pic({ safe: "m42", target_name: "M42", run_id: 2 })],
    });
    const { container } = renderStrip();
    await waitFor(() => expect(screen.getByText("M42")).toBeInTheDocument());
    expect(container.querySelectorAll("svg title")).toHaveLength(0);
  });

  it("self-hides rather than showing an empty card", async () => {
    const spy = vi.spyOn(client.api, "getGalleryBest").mockResolvedValue({ items: [] });
    renderStrip();
    await waitFor(() => expect(spy).toHaveBeenCalled());
    expect(screen.queryByText("My best pictures")).not.toBeInTheDocument();
  });
});
