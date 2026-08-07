import { MantineProvider } from "@mantine/core";
import { Notifications } from "@mantine/notifications";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
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
});
