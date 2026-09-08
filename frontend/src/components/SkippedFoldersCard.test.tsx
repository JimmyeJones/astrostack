import { MantineProvider } from "@mantine/core";
import { Notifications } from "@mantine/notifications";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  SkippedFoldersCard, skippedFoldersLead, undismissedFolders,
} from "./SkippedFoldersCard";
import type { SkippedIncomingFolder } from "../api/client";
import * as client from "../api/client";

function folder(over: Partial<SkippedIncomingFolder> = {}): SkippedIncomingFolder {
  return {
    name: "NGC 6888",
    path: "/data/incoming/NGC 6888",
    n_files: 4815,
    n_unrecognised: 4815,
    ...over,
  };
}

function renderCard() {
  return render(
    <MantineProvider>
      <Notifications />
      <QueryClientProvider client={new QueryClient()}>
        <SkippedFoldersCard />
      </QueryClientProvider>
    </MantineProvider>,
  );
}

beforeEach(() => localStorage.clear());
afterEach(() => vi.restoreAllMocks());

describe("skippedFoldersLead", () => {
  it("counts the files, not the folders, and reads as one sentence", () => {
    expect(skippedFoldersLead([folder()])).toBe(
      "A folder in your incoming folder holds 4,815 files that aren't reaching "
      + "a picture.",
    );
  });

  it("pluralises the folder half independently of the file half", () => {
    expect(skippedFoldersLead([
      folder({ path: "/i/a", n_unrecognised: 2 }),
      folder({ path: "/i/b", n_unrecognised: 1 }),
    ])).toBe(
      "2 folders in your incoming folder hold 3 files that aren't reaching "
      + "your pictures.",
    );
    expect(skippedFoldersLead([folder({ n_unrecognised: 1 })])).toContain(
      "holds 1 file that",
    );
  });
});

describe("undismissedFolders", () => {
  it("hides only the folder that was dismissed", () => {
    const a = folder({ path: "/i/a" });
    const b = folder({ path: "/i/b" });
    expect(undismissedFolders([a, b], ["/i/a"])).toEqual([b]);
  });

  it("lets a folder that goes missing later speak, even after a dismissal", () => {
    const later = folder({ path: "/i/new", name: "M 13" });
    expect(undismissedFolders([later], ["/i/a"])).toEqual([later]);
  });
});

describe("SkippedFoldersCard", () => {
  it("renders nothing at all on a healthy library", async () => {
    vi.spyOn(client.api, "skippedFolders").mockResolvedValue([]);
    renderCard();
    await waitFor(() => expect(client.api.skippedFolders).toHaveBeenCalled());
    expect(screen.queryByText(/may not be reaching a picture/)).toBeNull();
  });

  it("names the folder, counts what is missing, and offers to bring it in",
    async () => {
      vi.spyOn(client.api, "skippedFolders").mockResolvedValue([folder()]);
      const scan = vi.spyOn(client.api, "scan")
        .mockResolvedValue({ job_id: "j1" });
      renderCard();

      await screen.findByText(/Some of your subs may not be reaching a picture/);
      expect(screen.getByText(/4,815 files that aren't reaching a picture/))
        .toBeTruthy();
      expect(screen.getByText(/4,815 of them not recognised/)).toBeTruthy();

      fireEvent.click(screen.getByRole("button", { name: /Bring "NGC 6888" in/ }));
      // Scoped to that one folder — the app reads `incoming/`, never writes it.
      await waitFor(() => expect(scan).toHaveBeenCalledWith("/data/incoming/NGC 6888"));
    });

  it("says plainly that nothing on disk is touched", async () => {
    vi.spyOn(client.api, "skippedFolders").mockResolvedValue([folder()]);
    renderCard();
    await screen.findByText(/Nothing on your disk is deleted, moved or renamed/);
  });

  it("stays hidden for a folder the owner chose to leave out, and remembers",
    async () => {
      vi.spyOn(client.api, "skippedFolders").mockResolvedValue([folder()]);
      const { unmount } = renderCard();
      await screen.findByText(/Some of your subs may not be reaching a picture/);

      fireEvent.click(screen.getByRole("button", { name: "Leave it out" }));
      await waitFor(() =>
        expect(screen.queryByText(/may not be reaching a picture/)).toBeNull());

      unmount();
      renderCard();
      await waitFor(() => expect(client.api.skippedFolders).toHaveBeenCalledTimes(2));
      expect(screen.queryByText(/may not be reaching a picture/)).toBeNull();
    });

  it("a dismissal does not silence a different folder found later", async () => {
    localStorage.setItem(
      "astrostack.skippedFolders.dismissed", JSON.stringify(["/i/old"]));
    vi.spyOn(client.api, "skippedFolders")
      .mockResolvedValue([folder({ path: "/i/new", name: "M 13" })]);
    renderCard();
    await screen.findByText(/M 13:/);
  });

  it("names another program's working folder for what it is", async () => {
    // The card's whole sentence was about a folder named like a "_sub" sibling.
    // Since v0.393.0 a scan also skips another stacking program's scratch
    // directory by name, and describing that as "the finished picture your
    // Seestar made on the scope" would be a plain untruth. Fails before.
    vi.spyOn(client.api, "skippedFolders").mockResolvedValue([folder({
      name: "batch_stack_tmp", path: "/data/incoming/batch_stack_tmp",
      n_files: 137, n_unrecognised: 137, reason: "temp_folder",
    })]);
    renderCard();
    await screen.findByText(/A folder in your incoming folder was skipped/);
    expect(screen.getByText(
      /batch_stack_tmp: 137 files skipped — another stacking program's working folder/,
    )).toBeInTheDocument();
    expect(screen.queryByText(/finished picture your Seestar made/)).toBeNull();
    // Recoverable, which is the owner's condition on saying yes to the skip.
    expect(screen.getByRole(
      "button", { name: 'Bring "batch_stack_tmp" in anyway' })).toBeInTheDocument();
  });

  it("keeps the subs-may-be-missing framing when a real one is in the list",
    async () => {
      // Two reasons in one scan: the question the card exists to answer is
      // still "are some of my subs missing?", so that title wins and both
      // sentences are shown rather than one standing in for the other.
      vi.spyOn(client.api, "skippedFolders").mockResolvedValue([
        folder(),
        folder({ name: "batch_stack_tmp", path: "/i/batch_stack_tmp",
                 n_files: 9, n_unrecognised: 9, reason: "temp_folder" }),
      ]);
      renderCard();
      await screen.findByText(/Some of your subs may not be reaching a picture/);
      expect(screen.getByText(/finished picture your Seestar made/)).toBeInTheDocument();
      expect(screen.getByText(/another stacking program leaves behind/))
        .toBeInTheDocument();
    });

  it("survives a broken localStorage rather than blanking the Library", async () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("storage disabled");
    });
    vi.spyOn(client.api, "skippedFolders").mockResolvedValue([folder()]);
    renderCard();
    await screen.findByText(/Some of your subs may not be reaching a picture/);
  });
});
