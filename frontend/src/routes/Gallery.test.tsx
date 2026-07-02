import { MantineProvider } from "@mantine/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { GalleryView } from "./Gallery";
import * as client from "../api/client";
import type { GalleryItem } from "../api/client";

function item(run_id: number, safe = "M_42"): GalleryItem {
  return {
    safe, target_name: safe, run_id, output_basename: `m${run_id}`,
    timestamp_utc: "2026-05-02T00:00:00Z", n_frames_used: 5, canvas_w: 100, canvas_h: 80,
    has_preview: false, has_fits: true, has_tiff: false,
    preview_url: "", options: {},
  };
}

function renderGallery() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <MantineProvider>
      <QueryClientProvider client={qc}>
        <MemoryRouter><GalleryView /></MemoryRouter>
      </QueryClientProvider>
    </MantineProvider>,
  );
}

afterEach(() => vi.restoreAllMocks());

describe("Gallery batch apply", () => {
  it("selects images and applies a preset via the batch endpoint", async () => {
    vi.spyOn(client.api, "getGallery").mockResolvedValue({ items: [item(1), item(2)] });
    vi.spyOn(client.api, "optionsSchema").mockResolvedValue([]);
    vi.spyOn(client.api, "listPresets").mockResolvedValue({
      builtin: [{ id: "galaxy_broadband", label: "Galaxy", group: "Built-in", ops: [] }],
      user: [],
    });
    const batch = vi.spyOn(client.api, "batchApply").mockResolvedValue({ job_id: "j1" });
    vi.spyOn(window, "confirm").mockReturnValue(true);

    renderGallery();

    await waitFor(() => expect(screen.getAllByLabelText("Select for batch edit").length).toBe(2));
    fireEvent.click(screen.getAllByLabelText("Select for batch edit")[0]);
    expect(screen.getByText("1 selected")).toBeInTheDocument();

    fireEvent.click(screen.getByText("Apply preset to selected"));
    fireEvent.click(await screen.findByText("Galaxy"));

    await waitFor(() => expect(batch).toHaveBeenCalledTimes(1));
    expect(batch.mock.calls[0][0]).toMatchObject({
      preset_id: "galaxy_broadband",
      items: [{ safe: "M_42", run_id: 1 }],
    });
  });
});
