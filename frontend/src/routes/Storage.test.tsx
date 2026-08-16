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
});
