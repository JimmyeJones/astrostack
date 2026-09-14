import { MantineProvider } from "@mantine/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { IncomingLagNote } from "./IncomingLagNote";
import * as client from "../../api/client";
import type {
  ImportWaiting, IncomingLagItem, IncomingLagResponse,
} from "../../api/client";

/** A queued import, as `/api/jobs/queue-health` reports one — i.e. the state in
 * which `StuckImportNote` is speaking directly above this note. */
function queued(overrides: Partial<ImportWaiting> = {}): ImportWaiting {
  return {
    job_id: "j9", queued_utc: "2026-09-03T04:00:00+00:00",
    waiting_hours: 264.0, n_waiting: 1,
    holder_id: "j8", holder_kind: "reprocess_all", holder_target: null,
    holder_hours: 265.0,
    ...overrides,
  };
}

/** The ordinary answer: a healthy queue, nothing waiting on the worker. */
function quietQueue() {
  return vi.spyOn(client.api, "jobQueueHealth").mockResolvedValue({ waiting: null });
}

function item(overrides: Partial<IncomingLagItem> = {}): IncomingLagItem {
  return {
    folder: "IC 360_sub", target_name: "IC 360",
    n_on_disk: 2572, n_imported: 313, n_waiting: 2259,
    newest_utc: "2026-09-03T22:10:00+00:00", still_hours: 264.0,
    ...overrides,
  };
}

function answer(overrides: Partial<IncomingLagResponse> = {}): IncomingLagResponse {
  return {
    n_waiting: 0, n_folders: 0, checked: true,
    checked_utc: "2026-09-14T03:00:00+00:00", items: [],
    ...overrides,
  };
}

function renderNote() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <MantineProvider>
      <QueryClientProvider client={qc}>
        <MemoryRouter><IncomingLagNote /></MemoryRouter>
      </QueryClientProvider>
    </MantineProvider>,
  );
}

beforeEach(() => {
  localStorage.clear();
  // Explicit rather than implicit: every test below that does not care about the
  // queue is asserting the *healthy-queue* branch, and leaving it to a failed
  // fetch would make that a property of jsdom rather than of the note.
  quietQueue();
});
afterEach(() => vi.restoreAllMocks());

describe("IncomingLagNote", () => {
  it("says nothing on a library that has everything", async () => {
    vi.spyOn(client.api, "getIncomingLag").mockResolvedValue(answer());
    renderNote();
    await waitFor(() => expect(client.api.getIncomingLag).toHaveBeenCalled());
    expect(screen.queryByTestId("incoming-lag-note")).not.toBeInTheDocument();
  });

  it("says nothing when nobody has looked, even if it would have counted zero",
    async () => {
      // `checked: false` means there was no listing to judge against — not that
      // the folder is empty. Rendering "all clear" from it would be a claim the
      // app cannot make.
      vi.spyOn(client.api, "getIncomingLag").mockResolvedValue(
        answer({ checked: false, checked_utc: "" }));
      renderNote();
      await waitFor(() => expect(client.api.getIncomingLag).toHaveBeenCalled());
      expect(screen.queryByTestId("incoming-lag-note")).not.toBeInTheDocument();
    });

  it("names how many subs are waiting, how long, and the folders they are in",
    async () => {
      vi.spyOn(client.api, "getIncomingLag").mockResolvedValue(answer({
        n_waiting: 2259, n_folders: 1, items: [item()],
      }));
      renderNote();

      expect(await screen.findByText(
        "2,259 subs in your incoming folder haven't been imported yet"))
        .toBeInTheDocument();
      // The reassurance a beginner needs first: these are their only copy.
      expect(screen.getByText(/your subs are safe exactly where they are/))
        .toBeInTheDocument();
      expect(screen.getByText("IC 360_sub · 2,259 of 2,572 not imported"))
        .toBeInTheDocument();
      expect(screen.getByText(/been there for 11 days/)).toBeInTheDocument();
    });

  it("uses the singular for one file", async () => {
    vi.spyOn(client.api, "getIncomingLag").mockResolvedValue(answer({
      n_waiting: 1, n_folders: 1,
      items: [item({ n_on_disk: 1, n_imported: 0, n_waiting: 1 })],
    }));
    renderNote();
    expect(await screen.findByText(
      "A sub in your incoming folder hasn't been imported yet")).toBeInTheDocument();
  });

  it("names at most three folders and counts the rest", async () => {
    const items = ["a_sub", "b_sub", "c_sub", "d_sub"].map((folder, i) =>
      item({ folder, target_name: folder, n_on_disk: 10, n_imported: 0,
             n_waiting: 10 - i }));
    vi.spyOn(client.api, "getIncomingLag").mockResolvedValue(answer({
      n_waiting: 34, n_folders: 4, items,
    }));
    renderNote();
    await screen.findByTestId("incoming-lag-note");

    expect(screen.getByText(/across 4 folders/)).toBeInTheDocument();
    expect(screen.getByText("a_sub · 10 of 10 not imported")).toBeInTheDocument();
    expect(screen.queryByText(/^d_sub ·/)).not.toBeInTheDocument();
    expect(screen.getByText("and 1 more")).toBeInTheDocument();
  });

  it("offers a scan when nothing is queued — the case where a scan is what helps",
    async () => {
      vi.spyOn(client.api, "getIncomingLag").mockResolvedValue(answer({
        n_waiting: 12, n_folders: 1, items: [item({ n_waiting: 12 })],
      }));
      const scan = vi.spyOn(client.api, "scan").mockResolvedValue({ job_id: "j1" } as never);
      renderNote();

      fireEvent.click(await screen.findByRole("button", { name: "Scan incoming now" }));
      await waitFor(() => expect(scan).toHaveBeenCalled());
      // And it says so, rather than guessing at a queue that is empty.
      expect(screen.getByText(/nothing is queued waiting to run/)).toBeInTheDocument();
    });

  it("stops guessing at a cause the queue can answer, and stops offering a scan "
    + "that would only join the back of it", async () => {
    // The owner's own case: an import queued behind a long job, so
    // `StuckImportNote` is speaking an inch above this one with the same fact.
    vi.spyOn(client.api, "getIncomingLag").mockResolvedValue(answer({
      n_waiting: 2259, n_folders: 1, items: [item()],
    }));
    vi.spyOn(client.api, "jobQueueHealth").mockResolvedValue({ waiting: queued() });
    const scan = vi.spyOn(client.api, "scan").mockResolvedValue({ job_id: "j1" } as never);
    renderNote();
    await screen.findByTestId("incoming-lag-note");

    // The guess is gone, and the fact is quoted from the queue rather than from
    // this note's own reading of the folder.
    expect(screen.queryByText(/usually means/)).not.toBeInTheDocument();
    expect(screen.getByText(/already queued and has been waiting 11 days/))
      .toBeInTheDocument();
    // The action follows the fact: the worker is serial, so a scan cannot help.
    expect(screen.queryByRole("button", { name: "Scan incoming now" }))
      .not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open Jobs" })).toBeInTheDocument();
    expect(scan).not.toHaveBeenCalled();
  });

  it("does not repeat the reassurance the note above it is already giving",
    async () => {
      vi.spyOn(client.api, "getIncomingLag").mockResolvedValue(answer({
        n_waiting: 2259, n_folders: 1, items: [item()],
      }));
      vi.spyOn(client.api, "jobQueueHealth").mockResolvedValue({ waiting: queued() });
      renderNote();
      await screen.findByTestId("incoming-lag-note");

      expect(screen.queryByText(/your subs are safe exactly where they are/))
        .not.toBeInTheDocument();
      // What this note uniquely knows is still all there — that is the half the
      // queue note cannot say.
      expect(screen.getByText("IC 360_sub · 2,259 of 2,572 not imported"))
        .toBeInTheDocument();
      expect(screen.getByText(/been there for 11 days/)).toBeInTheDocument();
    });

  it("keeps today's wording against a backend with no queue-health endpoint",
    async () => {
      vi.spyOn(client.api, "getIncomingLag").mockResolvedValue(answer({
        n_waiting: 12, n_folders: 1, items: [item({ n_waiting: 12 })],
      }));
      vi.spyOn(client.api, "jobQueueHealth").mockRejectedValue(new Error("404"));
      renderNote();
      await screen.findByTestId("incoming-lag-note");

      expect(screen.getByText(/your subs are safe exactly where they are/))
        .toBeInTheDocument();
      expect(screen.getByRole("button", { name: "Scan incoming now" }))
        .toBeInTheDocument();
    });

  it("stays dismissed for the same set, and speaks again when more turn up",
    async () => {
      const get = vi.spyOn(client.api, "getIncomingLag").mockResolvedValue(answer({
        n_waiting: 12, n_folders: 1, items: [item({ n_waiting: 12 })],
      }));
      const first = renderNote();
      fireEvent.click(await screen.findByRole("button", { name: "Not now" }));
      await waitFor(() =>
        expect(screen.queryByTestId("incoming-lag-note")).not.toBeInTheDocument());
      first.unmount();

      renderNote();
      await waitFor(() => expect(get).toHaveBeenCalledTimes(2));
      expect(screen.queryByTestId("incoming-lag-note")).not.toBeInTheDocument();

      get.mockResolvedValue(answer({
        n_waiting: 30, n_folders: 1, items: [item({ n_waiting: 30 })],
      }));
      renderNote();
      expect(await screen.findByTestId("incoming-lag-note")).toBeInTheDocument();
    });

  it("renders nothing against a backend that has no such endpoint", async () => {
    vi.spyOn(client.api, "getIncomingLag").mockRejectedValue(new Error("404"));
    renderNote();
    await waitFor(() => expect(client.api.getIncomingLag).toHaveBeenCalled());
    expect(screen.queryByTestId("incoming-lag-note")).not.toBeInTheDocument();
  });
});
