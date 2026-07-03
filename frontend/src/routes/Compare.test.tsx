import { MantineProvider } from "@mantine/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { CompareView, parseRef, compareHref } from "./Compare";
import * as client from "../api/client";
import type { GalleryItem } from "../api/client";

function item(run_id: number, safe: string, target_name = safe): GalleryItem {
  return {
    safe, target_name, run_id, output_basename: `out${run_id}`,
    timestamp_utc: "2026-05-02T00:00:00Z", n_frames_used: 5, canvas_w: 100, canvas_h: 80,
    total_exposure_s: 300, has_preview: true, has_fits: true, has_tiff: false,
    preview_url: `/p/${safe}/${run_id}`, options: {},
  };
}

function renderCompare(qs: string) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <MantineProvider>
      <QueryClientProvider client={qc}>
        <MemoryRouter initialEntries={[`/compare${qs}`]}>
          <Routes>
            <Route path="/compare" element={<CompareView />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>
    </MantineProvider>,
  );
}

afterEach(() => vi.restoreAllMocks());

describe("parseRef", () => {
  it("parses a safe:run_id reference", () => {
    expect(parseRef("M_42:3")).toEqual({ safe: "M_42", run_id: 3 });
  });
  it("splits on the last colon so a safe key could (defensively) contain one", () => {
    expect(parseRef("a:b:7")).toEqual({ safe: "a:b", run_id: 7 });
  });
  it("rejects malformed or missing references", () => {
    expect(parseRef(null)).toBeNull();
    expect(parseRef("")).toBeNull();
    expect(parseRef("M_42")).toBeNull();
    expect(parseRef(":3")).toBeNull();
    expect(parseRef("M_42:x")).toBeNull();
  });
});

describe("compareHref", () => {
  it("builds a bookmarkable compare URL for two items", () => {
    expect(compareHref(item(3, "M_42"), item(7, "NGC_7000"))).toBe(
      "/compare?a=M_42:3&b=NGC_7000:7",
    );
  });
});

describe("CompareView", () => {
  it("prompts to pick two stacks when refs are missing", async () => {
    vi.spyOn(client.api, "getGallery").mockResolvedValue({ items: [] });
    renderCompare("");
    expect(await screen.findByText(/Pick two stacks to compare/)).toBeInTheDocument();
  });

  it("renders both stacks side by side", async () => {
    vi.spyOn(client.api, "getGallery").mockResolvedValue({
      items: [item(3, "M_42", "Orion"), item(7, "NGC_7000", "Pelican")],
    });
    renderCompare("?a=M_42:3&b=NGC_7000:7");
    await waitFor(() => expect(screen.getByText("Orion")).toBeInTheDocument());
    expect(screen.getByText("Pelican")).toBeInTheDocument();
    // Both A and B tags present.
    expect(screen.getByText("A")).toBeInTheDocument();
    expect(screen.getByText("B")).toBeInTheDocument();
  });

  it("warns when a referenced stack was deleted", async () => {
    vi.spyOn(client.api, "getGallery").mockResolvedValue({ items: [item(3, "M_42")] });
    renderCompare("?a=M_42:3&b=M_42:999");
    expect(await screen.findByText(/no longer exists/)).toBeInTheDocument();
  });
});
