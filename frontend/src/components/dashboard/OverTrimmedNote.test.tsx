import { MantineProvider } from "@mantine/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { OverTrimmedNote } from "./OverTrimmedNote";
import * as client from "../../api/client";
import type { OverTrimmedItem } from "../../api/client";

function item(overrides: Partial<OverTrimmedItem> = {}): OverTrimmedItem {
  return {
    safe: "M_31", target_name: "M 31", run_id: 7,
    // The 2026-09-10 audit's own numbers: 3.4 % kept where 92 % is good.
    stored_keep_fraction: 0.034, suggested_keep_fraction: 0.924,
    ...overrides,
  };
}

function renderNote() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <MantineProvider>
      <QueryClientProvider client={qc}>
        <MemoryRouter><OverTrimmedNote /></MemoryRouter>
      </QueryClientProvider>
    </MantineProvider>,
  );
}

beforeEach(() => localStorage.clear());
afterEach(() => vi.restoreAllMocks());

describe("OverTrimmedNote", () => {
  it("says nothing on a library with no over-trimmed pictures", async () => {
    vi.spyOn(client.api, "getOverTrimmedPictures").mockResolvedValue({
      count: 0, items: [],
    });
    renderNote();
    await waitFor(() => expect(client.api.getOverTrimmedPictures).toHaveBeenCalled());
    expect(screen.queryByTestId("over-trimmed-note")).not.toBeInTheDocument();
  });

  it("names the affected picture and what it is showing", async () => {
    vi.spyOn(client.api, "getOverTrimmedPictures").mockResolvedValue({
      count: 1, items: [item()],
    });
    renderNote();
    expect(await screen.findByTestId("over-trimmed-note")).toBeInTheDocument();
    expect(screen.getByText(/trimmed too far by an older version/i)).toBeInTheDocument();
    // The two numbers a beginner needs: what they have, and what they should have.
    expect(screen.getByText(/showing about 3% of the frame/i)).toBeInTheDocument();
    expect(screen.getByText(/about 92% is good/i)).toBeInTheDocument();
  });

  it("links each named target into its own editor, where the fix is", async () => {
    vi.spyOn(client.api, "getOverTrimmedPictures").mockResolvedValue({
      count: 1, items: [item({ safe: "NGC_6888", target_name: "NGC 6888", run_id: 12 })],
    });
    renderNote();
    const link = await screen.findByRole("link", { name: /NGC 6888/i });
    expect(link).toHaveAttribute("href", "/targets/NGC_6888/edit/12");
  });

  it("names at most three and points at the Library for the rest", async () => {
    vi.spyOn(client.api, "getOverTrimmedPictures").mockResolvedValue({
      count: 5,
      items: [1, 2, 3, 4, 5].map((n) =>
        item({ safe: `T_${n}`, target_name: `T ${n}`, run_id: n })),
    });
    renderNote();
    await screen.findByTestId("over-trimmed-note");
    expect(screen.getByText(/5 pictures were trimmed too far/i)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /T 3/ })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /T 4/ })).not.toBeInTheDocument();
    expect(screen.getByText(/2 more in your Library/)).toBeInTheDocument();
  });

  it("stays dismissed for the same set, and speaks again for a different one",
    async () => {
      const spy = vi.spyOn(client.api, "getOverTrimmedPictures").mockResolvedValue({
        count: 1, items: [item()],
      });
      const first = renderNote();
      await screen.findByTestId("over-trimmed-note");
      fireEvent.click(screen.getByLabelText("Not now"));
      await waitFor(() =>
        expect(screen.queryByTestId("over-trimmed-note")).not.toBeInTheDocument());
      first.unmount();

      // Same set → still quiet.
      renderNote();
      await waitFor(() => expect(spy).toHaveBeenCalledTimes(2));
      expect(screen.queryByTestId("over-trimmed-note")).not.toBeInTheDocument();
    });

  it("speaks again when a different picture turns up", async () => {
    vi.spyOn(client.api, "getOverTrimmedPictures").mockResolvedValue({
      count: 1, items: [item()],
    });
    const first = renderNote();
    await screen.findByTestId("over-trimmed-note");
    fireEvent.click(screen.getByLabelText("Not now"));
    first.unmount();

    vi.spyOn(client.api, "getOverTrimmedPictures").mockResolvedValue({
      count: 1, items: [item({ safe: "M_42", target_name: "M 42", run_id: 3 })],
    });
    renderNote();
    // Dismissing one backlog must not silence a genuinely different one — the
    // signature carries which pictures, not just how many.
    expect(await screen.findByTestId("over-trimmed-note")).toBeInTheDocument();
  });

  it("survives an item with no measurements rather than printing NaN", async () => {
    vi.spyOn(client.api, "getOverTrimmedPictures").mockResolvedValue({
      count: 1,
      items: [item({ stored_keep_fraction: null, suggested_keep_fraction: null })],
    });
    renderNote();
    await screen.findByTestId("over-trimmed-note");
    expect(screen.queryByText(/NaN/)).not.toBeInTheDocument();
  });
});
