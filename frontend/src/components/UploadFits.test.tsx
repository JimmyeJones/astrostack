import { MantineProvider } from "@mantine/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  UploadFits, collectDroppedFiles, isFitsFilename, readEntryFiles, uploadSummary,
  type FsEntry,
} from "./UploadFits";
import type { UploadResult } from "../api/client";
import * as client from "../api/client";

// --- Fake HTML5 FileSystem entries for the drag-drop folder-walk helpers ---
function fileEntry(name: string, fullPath?: string): FsEntry {
  const f = new File(["x"], name, { type: "application/octet-stream" });
  return { isFile: true, isDirectory: false, fullPath, file: (ok) => ok(f) };
}
function dirEntry(children: FsEntry[]): FsEntry {
  return {
    isFile: false,
    isDirectory: true,
    // A real DirectoryReader hands back entries in batches until an empty one.
    createReader: () => {
      let drained = false;
      return {
        readEntries: (ok: (e: FsEntry[]) => void) => {
          if (drained) { ok([]); return; }
          drained = true;
          ok(children);
        },
      };
    },
  };
}
function dtWithEntries(entries: FsEntry[]): DataTransfer {
  return {
    items: entries.map((entry) => ({ webkitGetAsEntry: () => entry })),
    files: [],
  } as unknown as DataTransfer;
}
function dtWithFiles(files: File[]): DataTransfer {
  return { items: [], files } as unknown as DataTransfer;
}

function result(over: Partial<UploadResult> = {}): UploadResult {
  return {
    target: "M31",
    saved: [{ name: "a.fit", bytes: 10 }],
    skipped: [],
    rejected: [],
    bytes_written: 10,
    job_id: "job-1",
    ...over,
  };
}

function renderUpload() {
  return render(
    <MantineProvider>
      <MemoryRouter>
        <QueryClientProvider client={new QueryClient()}>
          <UploadFits />
        </QueryClientProvider>
      </MemoryRouter>
    </MantineProvider>,
  );
}

afterEach(() => vi.restoreAllMocks());

describe("isFitsFilename", () => {
  it("accepts the scanner's FITS suffixes case-insensitively", () => {
    expect(isFitsFilename("Light_001.fit")).toBe(true);
    expect(isFitsFilename("x.FITS")).toBe(true);
    expect(isFitsFilename("x.fts")).toBe(true);
  });
  it("rejects non-FITS", () => {
    expect(isFitsFilename("notes.txt")).toBe(false);
    expect(isFitsFilename("x.fit.gz")).toBe(false);
    expect(isFitsFilename("x")).toBe(false);
  });
});

describe("uploadSummary", () => {
  it("summarises saved / skipped / rejected in plain language", () => {
    expect(uploadSummary(result())).toBe("Uploaded 1 sub into “M31”.");
    expect(uploadSummary(result({ saved: [{ name: "a.fit", bytes: 1 }, { name: "b.fit", bytes: 1 }] })))
      .toBe("Uploaded 2 subs into “M31”.");
    expect(uploadSummary(result({
      saved: [], skipped: [{ name: "a.fit", bytes: 1 }], target: "",
    }))).toBe("1 already there.");
    expect(uploadSummary(result({
      saved: [], rejected: [{ name: "x.txt", reason: "not a FITS file" }], target: "",
    }))).toBe("1 skipped.");
    expect(uploadSummary(result({ saved: [], skipped: [], rejected: [], target: "" })))
      .toBe("Nothing to upload.");
  });
});

describe("readEntryFiles", () => {
  it("yields a single file for a file entry", async () => {
    const files = await readEntryFiles(fileEntry("Light_001.fit"));
    expect(files.map((f) => f.name)).toEqual(["Light_001.fit"]);
  });
  it("walks a nested folder depth-first", async () => {
    const tree = dirEntry([
      fileEntry("a.fit"),
      dirEntry([fileEntry("b.fits"), fileEntry("readme.txt")]),
    ]);
    const files = await readEntryFiles(tree);
    expect(files.map((f) => f.name).sort()).toEqual(["a.fit", "b.fits", "readme.txt"]);
  });
  it("preserves the folder-relative path so same-named subs stay distinct", async () => {
    // Two different subs share a basename across session folders (Seestar restarts
    // frame numbering per session) — the relative path must survive as the name.
    const [f1] = await readEntryFiles(
      fileEntry("Light_0001.fit", "/M31/night1/Light_0001.fit"));
    const [f2] = await readEntryFiles(
      fileEntry("Light_0001.fit", "/M31/night2/Light_0001.fit"));
    expect(f1.name).toBe("M31/night1/Light_0001.fit");
    expect(f2.name).toBe("M31/night2/Light_0001.fit");
    expect(f1.name).not.toBe(f2.name);
  });
  it("leaves a bare file's name untouched when there is no subfolder", async () => {
    const [f] = await readEntryFiles(fileEntry("Light_0001.fit", "/Light_0001.fit"));
    expect(f.name).toBe("Light_0001.fit");
  });
});

describe("collectDroppedFiles", () => {
  it("flattens dropped folders via the entry API", async () => {
    const dt = dtWithEntries([
      fileEntry("top.fit"),
      dirEntry([fileEntry("nested.fits")]),
    ]);
    const files = await collectDroppedFiles(dt);
    expect(files.map((f) => f.name).sort()).toEqual(["nested.fits", "top.fit"]);
  });
  it("falls back to dataTransfer.files when the entry API is unavailable", async () => {
    const good = new File(["x"], "x.fit");
    const files = await collectDroppedFiles(dtWithFiles([good]));
    expect(files.map((f) => f.name)).toEqual(["x.fit"]);
  });
});

describe("UploadFits", () => {
  it("accepts a drag-drop of files, keeping only the FITS ones", async () => {
    renderUpload();
    const good = new File(["x"], "Light_009.fit", { type: "application/octet-stream" });
    const bad = new File(["x"], "notes.txt", { type: "text/plain" });
    const zone = screen.getByText(/Drag your Seestar FITS files/);
    fireEvent.drop(zone, { dataTransfer: dtWithFiles([good, bad]) });
    await waitFor(() => expect(screen.getByText(/1 FITS file ready/)).toBeInTheDocument());
    expect(screen.getByRole("button", { name: /^Upload/ })).not.toBeDisabled();
  });

  it("filters non-FITS on pick and uploads only the FITS files, then shows a summary", async () => {
    const spy = vi.spyOn(client.api, "uploadFits").mockResolvedValue(result());

    renderUpload();

    // The upload button is disabled until FITS files are chosen.
    const uploadBtn = screen.getByRole("button", { name: /^Upload/ });
    expect(uploadBtn).toBeDisabled();

    // Simulate the hidden file input receiving a mix of FITS + non-FITS.
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    const good = new File(["x"], "Light_001.fit", { type: "application/octet-stream" });
    const bad = new File(["x"], "readme.txt", { type: "text/plain" });
    Object.defineProperty(input, "files", { value: [good, bad], configurable: true });
    fireEvent.change(input);

    // Only the one FITS file is counted as ready.
    await waitFor(() => expect(screen.getByText(/1 FITS file ready/)).toBeInTheDocument());
    const btn = screen.getByRole("button", { name: /^Upload/ });
    expect(btn).not.toBeDisabled();

    fireEvent.click(btn);

    await waitFor(() => expect(spy).toHaveBeenCalledTimes(1));
    // Uploaded exactly the FITS file, not the .txt.
    const [filesArg] = spy.mock.calls[0];
    expect(filesArg.map((f) => f.name)).toEqual(["Light_001.fit"]);
    // Success alert with the scan-progress link appears.
    await waitFor(() => expect(screen.getByText(/Uploaded 1 sub/)).toBeInTheDocument());
    expect(screen.getByText(/Watch progress/)).toBeInTheDocument();
  });
});
