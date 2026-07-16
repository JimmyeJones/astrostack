import { MantineProvider } from "@mantine/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  UploadFits, collectDroppedFiles, filesFromFolderInput, isFitsFilename,
  readEntryFiles, uploadSummary, uploadProgressLabel, uploadProgressPercent,
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

describe("upload progress helpers", () => {
  it("computes a clamped, NaN-safe percentage", () => {
    expect(uploadProgressPercent(0, 100)).toBe(0);
    expect(uploadProgressPercent(25, 100)).toBe(25);
    expect(uploadProgressPercent(100, 100)).toBe(100);
    // Over-reporting or an unknown/zero total never breaks the bar.
    expect(uploadProgressPercent(120, 100)).toBe(100);
    expect(uploadProgressPercent(50, 0)).toBe(0);
  });
  it("formats a plain-language bytes line with friendly units", () => {
    expect(uploadProgressLabel(1024 * 1024, 4 * 1024 * 1024)).toBe("1.0 MB of 4.0 MB (25%)");
    expect(uploadProgressLabel(512, 1024)).toBe("512 B of 1 KB (50%)");
    expect(uploadProgressLabel(1.5 * 1024 ** 3, 3 * 1024 ** 3)).toBe("1.5 GB of 3.0 GB (50%)");
    expect(uploadProgressLabel(0, 0)).toBe("Uploading…");
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

function withRelPath(name: string, rel: string): File {
  const f = new File(["x"], name, { type: "application/octet-stream" });
  Object.defineProperty(f, "webkitRelativePath", { value: rel, configurable: true });
  return f;
}

describe("filesFromFolderInput", () => {
  it("preserves each file's relative subpath (webkitRelativePath) as its name", () => {
    const out = filesFromFolderInput([
      withRelPath("Light_0001.fit", "M31/night1/Light_0001.fit"),
      withRelPath("Light_0001.fit", "M31/night2/Light_0001.fit"),
    ]);
    // Same-basename subs from different session folders stay distinct on upload.
    expect(out.map((f) => f.name)).toEqual([
      "M31/night1/Light_0001.fit",
      "M31/night2/Light_0001.fit",
    ]);
  });

  it("falls back to the bare name when there's no relative path", () => {
    const out = filesFromFolderInput([new File(["x"], "Light_5.fit")]);
    expect(out.map((f) => f.name)).toEqual(["Light_5.fit"]);
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

  it("accepts a folder pick, keeping FITS files with their relative paths", async () => {
    const spy = vi.spyOn(client.api, "uploadFits").mockResolvedValue(result());
    renderUpload();

    // The folder picker is the hidden webkitdirectory input (button-driven).
    const folderInput = document.querySelector(
      'input[webkitdirectory]') as HTMLInputElement;
    expect(folderInput).not.toBeNull();
    const good = withRelPath("Light_0001.fit", "M31/night1/Light_0001.fit");
    const bad = withRelPath("notes.txt", "M31/notes.txt");
    Object.defineProperty(folderInput, "files", { value: [good, bad], configurable: true });
    fireEvent.change(folderInput);

    await waitFor(() => expect(screen.getByText(/1 FITS file ready/)).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: /^Upload/ }));
    await waitFor(() => expect(spy).toHaveBeenCalledTimes(1));
    // Only the FITS file, and its relative subpath is preserved for the server.
    expect(spy.mock.calls[0][0].map((f) => f.name)).toEqual(["M31/night1/Light_0001.fit"]);
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

  it("shows a live progress readout while the upload is in flight", async () => {
    // Report 25% mid-flight, then hold the upload open so the pending state
    // (and its progress bar) is observable before the mutation resolves.
    let finish: (r: UploadResult) => void = () => {};
    vi.spyOn(client.api, "uploadFits").mockImplementation(
      (_files, _target, onProgress) =>
        new Promise<UploadResult>((resolve) => {
          onProgress?.(1024 * 1024, 4 * 1024 * 1024);
          finish = resolve;
        }),
    );

    renderUpload();
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    const good = new File(["x"], "Light_001.fit", { type: "application/octet-stream" });
    Object.defineProperty(input, "files", { value: [good], configurable: true });
    fireEvent.change(input);
    await waitFor(() =>
      expect(screen.getByRole("button", { name: /^Upload/ })).not.toBeDisabled());
    fireEvent.click(screen.getByRole("button", { name: /^Upload/ }));

    // The plain-language progress line reflects the reported 25%.
    await waitFor(() =>
      expect(screen.getByText(/Uploading — 1\.0 MB of 4\.0 MB \(25%\)/)).toBeInTheDocument());

    finish(result());
    await waitFor(() => expect(screen.getByText(/Uploaded 1 sub/)).toBeInTheDocument());
    // The progress readout is gone once it's done (only shown while in flight).
    await waitFor(() =>
      expect(screen.queryByText(/Uploading —/)).not.toBeInTheDocument());
  });
});
