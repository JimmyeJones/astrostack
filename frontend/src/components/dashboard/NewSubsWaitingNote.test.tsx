import { MantineProvider } from "@mantine/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { NewSubsWaitingNote } from "./NewSubsWaitingNote";
import * as client from "../../api/client";
import type { NewSubsWaitingItem } from "../../api/client";

function item(overrides: Partial<NewSubsWaitingItem> = {}): NewSubsWaitingItem {
  return {
    safe: "M_31", target_name: "M 31", run_id: 7,
    stacked_utc: "2026-08-14T21:00:00Z", n_frames_used: 120, n_new_subs: 45,
    ...overrides,
  };
}

function renderNote() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <MantineProvider>
      <QueryClientProvider client={qc}>
        <MemoryRouter><NewSubsWaitingNote /></MemoryRouter>
      </QueryClientProvider>
    </MantineProvider>,
  );
}

beforeEach(() => localStorage.clear());
afterEach(() => vi.restoreAllMocks());

describe("NewSubsWaitingNote", () => {
  it("says nothing on a library whose pictures are all up to date", async () => {
    vi.spyOn(client.api, "getNewSubsWaiting").mockResolvedValue({
      count: 0, total_new_subs: 0, items: [],
    });
    renderNote();
    await waitFor(() => expect(client.api.getNewSubsWaiting).toHaveBeenCalled());
    expect(screen.queryByTestId("new-subs-waiting-note")).not.toBeInTheDocument();
  });

  it("names the target, says how many subs are waiting, and links to its Stack form",
    async () => {
      vi.spyOn(client.api, "getNewSubsWaiting").mockResolvedValue({
        count: 1, total_new_subs: 45, items: [item()],
      });
      renderNote();
      expect(await screen.findByText("45 subs you've shot aren't in the picture yet"))
        .toBeInTheDocument();
      const btn = screen.getByRole("link", { name: "M 31 · +45" });
      // Straight to where the estimate and the settings are — the note never stacks.
      expect(btn).toHaveAttribute("href", "/targets/M_31/stack");
      // It reassures that nothing is lost, which is the question a beginner has.
      expect(screen.getByText(/stays in that target's history/)).toBeInTheDocument();
      // Nothing to send elsewhere when the note already names everything.
      expect(screen.queryByText(/in the Library/)).not.toBeInTheDocument();
    });

  it("counts them all, names the first few, and says where the rest are",
    async () => {
      vi.spyOn(client.api, "getNewSubsWaiting").mockResolvedValue({
        count: 5, total_new_subs: 100,
        items: [
          item({ safe: "A", target_name: "M 31", n_new_subs: 40 }),
          item({ safe: "B", target_name: "M 42", n_new_subs: 30 }),
          item({ safe: "C", target_name: "NGC 7000", n_new_subs: 20 }),
          item({ safe: "D", target_name: "M 81", n_new_subs: 10 }),
        ],
      });
      renderNote();
      expect(await screen.findByText("100 subs you've shot aren't in your pictures yet"))
        .toBeInTheDocument();
      for (const name of ["M 31 · +40", "M 42 · +30", "NGC 7000 · +20"]) {
        expect(screen.getByRole("link", { name })).toBeInTheDocument();
      }
      // The fourth is past the naming cap, so it isn't listed…
      expect(screen.queryByRole("link", { name: "M 81 · +10" })).not.toBeInTheDocument();
      // …and the overflow link says where the rest are without claiming the
      // Library singles them out.
      expect(screen.getByRole("link", { name: "2 more in your Library →" }))
        .toHaveAttribute("href", "/library");
    });

  it("says 'sub' rather than 'subs' when exactly one is waiting", async () => {
    vi.spyOn(client.api, "getNewSubsWaiting").mockResolvedValue({
      count: 1, total_new_subs: 1, items: [item({ n_new_subs: 1 })],
    });
    renderNote();
    expect(await screen.findByText("1 sub you've shot isn't in the picture yet"))
      .toBeInTheDocument();
    expect(screen.getByText(/folds it in/)).toBeInTheDocument();
  });

  it("stays dismissed for the same backlog, and speaks again after another night",
    async () => {
      const spy = vi.spyOn(client.api, "getNewSubsWaiting").mockResolvedValue({
        count: 1, total_new_subs: 45, items: [item()],
      });
      const first = renderNote();
      await screen.findByTestId("new-subs-waiting-note");
      fireEvent.click(screen.getByRole("button", { name: "Not now" }));
      expect(screen.queryByTestId("new-subs-waiting-note")).not.toBeInTheDocument();

      // A fresh mount with the same subs waiting stays quiet.
      first.unmount();
      renderNote();
      await waitFor(() => expect(spy).toHaveBeenCalledTimes(2));
      expect(screen.queryByTestId("new-subs-waiting-note")).not.toBeInTheDocument();

      // Shooting more of the same target is new news — the signature carries the
      // count, so "not now" cannot silence next week's subs too.
      spy.mockResolvedValue({
        count: 1, total_new_subs: 60, items: [item({ n_new_subs: 60 })],
      });
      renderNote();
      expect(await screen.findByTestId("new-subs-waiting-note")).toBeInTheDocument();
    });

  it("never offers to stack anything itself", async () => {
    vi.spyOn(client.api, "getNewSubsWaiting").mockResolvedValue({
      count: 3, total_new_subs: 90,
      items: [
        item({ safe: "A", target_name: "M 31", n_new_subs: 40 }),
        item({ safe: "B", target_name: "M 42", n_new_subs: 30 }),
        item({ safe: "C", target_name: "NGC 7000", n_new_subs: 20 }),
      ],
    });
    renderNote();
    await screen.findByTestId("new-subs-waiting-note");
    // Re-stacking is hours of CPU on a NAS: every action here is a link to a
    // form, and the only button is the note's own "Not now".
    const buttons = screen.getAllByRole("button");
    expect(buttons.map((b) => b.getAttribute("aria-label") ?? b.textContent))
      .toEqual(["Not now"]);
  });

  it("survives a backend that can't answer", async () => {
    vi.spyOn(client.api, "getNewSubsWaiting").mockRejectedValue(new Error("boom"));
    renderNote();
    await waitFor(() => expect(client.api.getNewSubsWaiting).toHaveBeenCalled());
    expect(screen.queryByTestId("new-subs-waiting-note")).not.toBeInTheDocument();
  });
});
