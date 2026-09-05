import { MantineProvider } from "@mantine/core";
import { Notifications } from "@mantine/notifications";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { StorageView } from "./Storage";
import * as client from "../api/client";
import type { StorageInfo } from "../api/client";

function mkStorage(overrides: Partial<StorageInfo> = {}): StorageInfo {
  return {
    targets: [],
    total_bytes: 0,
    output_bytes: 0,
    cache_bytes: 0,
    disk: {},
    ...overrides,
  } as StorageInfo;
}

function renderStorage() {
  const qc = new QueryClient();
  return render(
    <MantineProvider>
      <Notifications />
      <QueryClientProvider client={qc}>
        <MemoryRouter><StorageView /></MemoryRouter>
      </QueryClientProvider>
    </MantineProvider>,
  );
}

afterEach(() => vi.restoreAllMocks());

describe("StorageView", () => {
  it("says plainly that clearing space never touches the incoming folder", async () => {
    // The page's whole job is offering to delete things, so it is exactly where a
    // beginner wonders "will this eat my originals?". The answer has to be on it.
    vi.spyOn(client.api, "getStorage").mockResolvedValue(mkStorage());

    renderStorage();
    await waitFor(() => expect(screen.getByText("Storage")).toBeInTheDocument());

    const note = screen.getByText(/Nothing here touches your incoming folder/i);
    expect(note).toBeInTheDocument();
    expect(note.textContent).toMatch(/never moves, deletes or changes a file you dropped in/i);
  });

  it("states the free disk once, in the same unit as the headroom note", async () => {
    // Found by dogfooding: the header read "23 GB free on disk" (the server's
    // decimal free_gb) directly above "21 GB free — not enough imaging history
    // yet" (the same bytes in binary GiB) — one fact, two numbers, one screen.
    const freeBytes = 23.4e9;
    vi.spyOn(client.api, "getStorage").mockResolvedValue(
      mkStorage({ disk: { free_gb: 23.4, total_gb: 500, free_bytes: freeBytes } }),
    );

    renderStorage();
    await waitFor(() => expect(screen.getByText("Storage")).toBeInTheDocument());

    expect(screen.getByText(/free on disk/i).textContent).toContain("22 GB");
    // The header and the headroom note under it quote the same figure.
    expect(screen.getAllByText(/22 GB free/)).toHaveLength(2);
    expect(screen.queryByText(/23\.4 GB/)).not.toBeInTheDocument();
  });

  it("falls back to the older backend's free_gb when bytes aren't served", async () => {
    vi.spyOn(client.api, "getStorage").mockResolvedValue(
      mkStorage({ disk: { free_gb: 23.4, total_gb: 500 } }),
    );
    renderStorage();
    await waitFor(() => expect(screen.getByText("Storage")).toBeInTheDocument());
    expect(screen.getByText(/23\.4 GB free on disk/)).toBeInTheDocument();
  });

  it("offers the editor's preview cache as its own clearable stage", async () => {
    // These sit under cache/ but were in no figure and no clear stage, so an
    // install that pruned runs before the purge fix had no way to reclaim the
    // proxies those deletions orphaned.
    const target = {
      safe: "m_42", name: "M 42", total_bytes: 200, output_bytes: 40,
      cache_bytes: 160, stage1_bytes: 10, stage2_bytes: 20, thumbs_bytes: 30,
      proxies_bytes: 100, n_stack_runs: 1,
    };
    vi.spyOn(client.api, "getStorage").mockResolvedValue(
      mkStorage({ targets: [target], total_bytes: 200, cache_bytes: 160 }),
    );
    const clear = vi.spyOn(client.api, "clearCache")
      .mockResolvedValue({ cleared: ["proxies"] });
    vi.spyOn(window, "confirm").mockReturnValue(true);

    renderStorage();
    await waitFor(() => expect(screen.getByText("M 42")).toBeInTheDocument());

    fireEvent.click(screen.getByRole("button", { name: /clear cache/i }));
    fireEvent.click(await screen.findByText(/Editor previews/i));

    await waitFor(() => expect(clear).toHaveBeenCalledWith("m_42", "proxies"));
  });

  it("shows a zero for an older backend that doesn't report the proxy cache", async () => {
    const target = {
      safe: "m_42", name: "M 42", total_bytes: 100, output_bytes: 40,
      cache_bytes: 60, stage1_bytes: 10, stage2_bytes: 20, thumbs_bytes: 30,
      n_stack_runs: 1,
    };
    vi.spyOn(client.api, "getStorage").mockResolvedValue(
      mkStorage({ targets: [target], total_bytes: 100, cache_bytes: 60 }),
    );
    renderStorage();
    await waitFor(() => expect(screen.getByText("M 42")).toBeInTheDocument());

    fireEvent.click(screen.getByRole("button", { name: /clear cache/i }));
    expect(await screen.findByText(/Editor previews \(0 MB\)/i)).toBeInTheDocument();
  });

  it("names the prepared full-size download and offers the space back", async () => {
    // A season of mosaics at print size is gigabytes. Storage is where a NAS
    // owner asks what is using the disk, so it must be nameable here rather
    // than turning up as usage nothing accounts for.
    vi.spyOn(client.api, "getStorage")
      .mockResolvedValue(mkStorage({ exports_bytes: 3 * 1024 ** 3 }));
    const clear = vi.spyOn(client.api, "clearPicturesArchive")
      .mockResolvedValue({ removed: true, freed_bytes: 3 * 1024 ** 3 });
    renderStorage();

    expect(await screen.findByText(/Prepared download: 3.00 GB/)).toBeInTheDocument();
    expect(screen.getByText(/Safe to delete/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /delete/i }));
    await waitFor(() => expect(clear).toHaveBeenCalled());
  });

  it("says nothing about a prepared download when there isn't one", async () => {
    // Including on an older backend that doesn't report the field at all.
    vi.spyOn(client.api, "getStorage").mockResolvedValue(mkStorage({ exports_bytes: 0 }));
    renderStorage();
    await waitFor(() => expect(screen.getByText(/Library total:/)).toBeInTheDocument());
    expect(screen.queryByText(/Prepared download/)).toBeNull();
  });
});
