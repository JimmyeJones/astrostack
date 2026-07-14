import { MantineProvider } from "@mantine/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Library, expo } from "./Library";
import * as client from "../api/client";
import type { Target } from "../api/client";

function mk(name: string, tags: string[], exposure = 0, notes: string | null = null): Target {
  return {
    safe_name: name.replace(/\s/g, "_"), name, ra_deg: null, dec_deg: null,
    n_frames: 10, n_frames_accepted: 8, total_exposure_s: exposure,
    last_activity_utc: null, has_preview: false, notes, tags,
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

afterEach(() => {
  vi.restoreAllMocks();
  localStorage.clear();  // filters persist to localStorage — isolate tests
});

describe("expo", () => {
  it("formats exposure and rolls minutes into hours (never '1h 60m')", () => {
    expect(expo(0)).toBe("—");
    expect(expo(90)).toBe("2m");
    expect(expo(3600)).toBe("1h 0m");
    expect(expo(5400)).toBe("1h 30m");
    // 7190 s = 1h 59.8m: the minutes remainder rounds to 60 and must roll over.
    expect(expo(7190)).toBe("2h 0m");
  });
});

describe("Library", () => {
  it("filters targets by search text and by tag", async () => {
    vi.spyOn(client.api, "listTargets").mockResolvedValue([
      mk("Orion Nebula", ["nebula"]),
      mk("Andromeda", ["galaxy"]),
    ]);
    renderLibrary();

    await waitFor(() => expect(screen.getByText("Orion Nebula")).toBeInTheDocument());
    expect(screen.getByText("Andromeda")).toBeInTheDocument();

    const searchBox = screen.getByPlaceholderText("Search name, tag or note…");
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

  it("matches the search against a target's notes", async () => {
    vi.spyOn(client.api, "listTargets").mockResolvedValue([
      mk("Orion Nebula", [], 0, "shot on a hazy night"),
      mk("Andromeda", [], 0, "crystal clear"),
    ]);
    renderLibrary();

    await waitFor(() => expect(screen.getByText("Orion Nebula")).toBeInTheDocument());
    const searchBox = screen.getByPlaceholderText("Search name, tag or note…");
    fireEvent.change(searchBox, { target: { value: "hazy" } });

    await waitFor(() => expect(screen.queryByText("Andromeda")).not.toBeInTheDocument());
    expect(screen.getByText("Orion Nebula")).toBeInTheDocument();
  });

  it("restores the saved search filter on remount", async () => {
    localStorage.setItem(
      "astrostack.library.filters",
      JSON.stringify({ search: "andro", sort: "recent", tags: [] }),
    );
    vi.spyOn(client.api, "listTargets").mockResolvedValue([
      mk("Orion Nebula", ["nebula"]),
      mk("Andromeda", ["galaxy"]),
    ]);
    renderLibrary();

    // The persisted "andro" search is applied immediately, hiding Orion.
    await waitFor(() => expect(screen.getByText("Andromeda")).toBeInTheDocument());
    expect(screen.queryByText("Orion Nebula")).not.toBeInTheDocument();
    expect(screen.getByPlaceholderText("Search name, tag or note…")).toHaveValue("andro");
  });

  it("points an empty library at upload, not an empty jobs page", async () => {
    // A brand-new user has zero targets *and* zero jobs. The empty state's only
    // prominent button used to be "View jobs", which sent them to an empty page
    // away from the upload card the copy points them at. The upload on-ramp must
    // be the CTA, with no misdirecting "View jobs" button.
    vi.spyOn(client.api, "listTargets").mockResolvedValue([]);
    renderLibrary();

    await waitFor(() => expect(screen.getByText("No targets yet.")).toBeInTheDocument());
    expect(screen.queryByRole("link", { name: "View jobs" })).not.toBeInTheDocument();
    // The upload card is present (its file picker button anchors it).
    expect(screen.getByRole("button", { name: /Choose FITS files/i })).toBeInTheDocument();
  });
});
