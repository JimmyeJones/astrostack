import { MantineProvider } from "@mantine/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { UnexportedEditsNote } from "./UnexportedEditsNote";
import * as client from "../../api/client";
import type { UnexportedEditItem } from "../../api/client";

function item(overrides: Partial<UnexportedEditItem> = {}): UnexportedEditItem {
  return {
    safe: "M_31", target_name: "M 31", run_id: 7,
    timestamp_utc: "2026-08-14T21:00:00Z",
    ...overrides,
  };
}

function renderNote() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <MantineProvider>
      <QueryClientProvider client={qc}>
        <MemoryRouter><UnexportedEditsNote /></MemoryRouter>
      </QueryClientProvider>
    </MantineProvider>,
  );
}

beforeEach(() => localStorage.clear());
afterEach(() => vi.restoreAllMocks());

describe("UnexportedEditsNote", () => {
  it("says nothing on a library with no unfinished edits", async () => {
    vi.spyOn(client.api, "getUnexportedEdits").mockResolvedValue({ count: 0, items: [] });
    renderNote();
    await waitFor(() => expect(client.api.getUnexportedEdits).toHaveBeenCalled());
    expect(screen.queryByTestId("unexported-edits-note")).not.toBeInTheDocument();
  });

  it("names the one picture and links straight into its editor", async () => {
    vi.spyOn(client.api, "getUnexportedEdits").mockResolvedValue({
      count: 1, items: [item()],
    });
    renderNote();
    expect(await screen.findByText("You have an edit you never finished")).toBeInTheDocument();
    const btn = screen.getByRole("link", { name: "Finish M 31" });
    expect(btn).toHaveAttribute("href", "/targets/M_31/edit/7");
    // No "see all" link when the note already names everything it counted.
    expect(screen.queryByText(/in the Gallery/)).not.toBeInTheDocument();
  });

  it("counts them all, names the first few, and sends the rest to the Gallery", async () => {
    vi.spyOn(client.api, "getUnexportedEdits").mockResolvedValue({
      count: 5,
      items: [
        item({ safe: "A", target_name: "M 31", run_id: 1 }),
        item({ safe: "B", target_name: "M 42", run_id: 2 }),
        item({ safe: "C", target_name: "NGC 7000", run_id: 3 }),
        item({ safe: "D", target_name: "M 81", run_id: 4 }),
      ],
    });
    renderNote();
    expect(await screen.findByText("You have 5 edits you never finished")).toBeInTheDocument();
    for (const name of ["M 31", "M 42", "NGC 7000"]) {
      expect(screen.getByRole("link", { name })).toBeInTheDocument();
    }
    // The fourth is past the naming cap, so it isn't listed…
    expect(screen.queryByRole("link", { name: "M 81" })).not.toBeInTheDocument();
    // …and the Gallery link carries the true total, not the number shown.
    expect(screen.getByRole("link", { name: "See all 5 in the Gallery →" }))
      .toHaveAttribute("href", "/gallery");
  });

  it("stays dismissed for the same edits, and speaks up again for a new one", async () => {
    const spy = vi.spyOn(client.api, "getUnexportedEdits").mockResolvedValue({
      count: 1, items: [item()],
    });
    const first = renderNote();
    await screen.findByText("You have an edit you never finished");
    fireEvent.click(screen.getByRole("button", { name: "Not now" }));
    expect(screen.queryByTestId("unexported-edits-note")).not.toBeInTheDocument();

    // A fresh mount with the *same* unfinished edits stays quiet.
    first.unmount();
    renderNote();
    await waitFor(() => expect(spy).toHaveBeenCalledTimes(2));
    expect(screen.queryByTestId("unexported-edits-note")).not.toBeInTheDocument();

    // A different edit is a different problem, so it is not covered by the
    // earlier "not now".
    spy.mockResolvedValue({ count: 1, items: [item({ run_id: 9 })] });
    renderNote();
    expect(await screen.findByTestId("unexported-edits-note")).toBeInTheDocument();
  });

  it("survives a backend that can't answer", async () => {
    vi.spyOn(client.api, "getUnexportedEdits").mockRejectedValue(new Error("boom"));
    renderNote();
    await waitFor(() => expect(client.api.getUnexportedEdits).toHaveBeenCalled());
    expect(screen.queryByTestId("unexported-edits-note")).not.toBeInTheDocument();
  });
});
