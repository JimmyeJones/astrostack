import { MantineProvider } from "@mantine/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Library } from "./Library";
import * as client from "../api/client";
import type { Target } from "../api/client";

function mk(name: string, tags: string[], exposure = 0): Target {
  return {
    safe_name: name.replace(/\s/g, "_"), name, ra_deg: null, dec_deg: null,
    n_frames: 10, n_frames_accepted: 8, total_exposure_s: exposure,
    last_activity_utc: null, has_preview: false, notes: null, tags,
  };
}

function renderLibrary() {
  const qc = new QueryClient();
  return render(
    <MantineProvider>
      <QueryClientProvider client={qc}>
        <MemoryRouter><Library /></MemoryRouter>
      </QueryClientProvider>
    </MantineProvider>,
  );
}

afterEach(() => vi.restoreAllMocks());

describe("Library", () => {
  it("filters targets by search text and by tag", async () => {
    vi.spyOn(client.api, "listTargets").mockResolvedValue([
      mk("Orion Nebula", ["nebula"]),
      mk("Andromeda", ["galaxy"]),
    ]);
    renderLibrary();

    await waitFor(() => expect(screen.getByText("Orion Nebula")).toBeInTheDocument());
    expect(screen.getByText("Andromeda")).toBeInTheDocument();

    const searchBox = screen.getByPlaceholderText("Search name or tag…");
    fireEvent.change(searchBox, { target: { value: "andro" } });
    await waitFor(() => expect(screen.queryByText("Orion Nebula")).not.toBeInTheDocument());
    expect(screen.getByText("Andromeda")).toBeInTheDocument();

    fireEvent.change(searchBox, { target: { value: "" } });
    await waitFor(() => expect(screen.getByText("Orion Nebula")).toBeInTheDocument());

    // Filter by the "nebula" tag chip (the Chip renders a checkbox input).
    fireEvent.click(screen.getByRole("checkbox", { name: "nebula" }));
    await waitFor(() => expect(screen.queryByText("Andromeda")).not.toBeInTheDocument());
    expect(screen.getByText("Orion Nebula")).toBeInTheDocument();
  });
});
