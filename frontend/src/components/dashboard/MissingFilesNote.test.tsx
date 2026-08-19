import { MantineProvider } from "@mantine/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { MissingFilesNote } from "./MissingFilesNote";
import * as client from "../../api/client";
import type { LibraryMissingFiles } from "../../api/client";

function payload(o: Partial<LibraryMissingFiles> = {}): LibraryMissingFiles {
  return { n_missing: 0, n_accepted: 8000, n_targets_missing: 0, targets: [], ...o };
}

function renderNote() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <MantineProvider>
      <QueryClientProvider client={qc}>
        <MemoryRouter><MissingFilesNote /></MemoryRouter>
      </QueryClientProvider>
    </MantineProvider>,
  );
}

afterEach(() => vi.restoreAllMocks());

describe("MissingFilesNote", () => {
  it("says nothing on a healthy library", async () => {
    vi.spyOn(client.api, "getLibraryMissingFiles").mockResolvedValue(payload());
    renderNote();
    await waitFor(() => expect(client.api.getLibraryMissingFiles).toHaveBeenCalled());
    expect(screen.queryByTestId("missing-files-note")).not.toBeInTheDocument();
  });

  it("says it once for the whole library and points at the Library", async () => {
    vi.spyOn(client.api, "getLibraryMissingFiles").mockResolvedValue(payload({
      n_missing: 3200,
      n_targets_missing: 11,
      targets: [{ safe: "m42", name: "M 42", n_missing: 900 }],
    }));
    renderNote();
    expect(await screen.findByText("3,200 subs across 11 targets aren't on disk"))
      .toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open your library" }))
      .toHaveAttribute("href", "/library");
  });

  it("links straight at the one target when only one is affected", async () => {
    vi.spyOn(client.api, "getLibraryMissingFiles").mockResolvedValue(payload({
      n_missing: 412,
      n_targets_missing: 1,
      targets: [{ safe: "orion", name: "Orion Nebula", n_missing: 412 }],
    }));
    renderNote();
    expect(await screen.findByText("412 of Orion Nebula's subs aren't on disk"))
      .toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open this target" }))
      .toHaveAttribute("href", "/targets/orion");
  });

  it("stays silent on an older backend that has no such endpoint", async () => {
    vi.spyOn(client.api, "getLibraryMissingFiles")
      .mockRejectedValue(new Error("404 Not Found"));
    renderNote();
    await waitFor(() => expect(client.api.getLibraryMissingFiles).toHaveBeenCalled());
    expect(screen.queryByTestId("missing-files-note")).not.toBeInTheDocument();
    // A missing answer is not a missing drive — and it must not surface as an
    // error the user has to reason about either.
    expect(screen.queryByText(/404/)).not.toBeInTheDocument();
  });
});
