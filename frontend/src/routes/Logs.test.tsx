import { MantineProvider } from "@mantine/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { LogsView } from "./Logs";
import * as client from "../api/client";
import type { LogEntry } from "../api/client";

function mkEntry(seq: number, message: string, logger = "webapp"): LogEntry {
  return { seq, ts: "2026-01-01T00:00:00", level: "INFO", levelno: 20, logger, message };
}

function renderLogs() {
  const qc = new QueryClient();
  return render(
    <MantineProvider>
      <QueryClientProvider client={qc}>
        <LogsView />
      </QueryClientProvider>
    </MantineProvider>,
  );
}

afterEach(() => vi.restoreAllMocks());

describe("LogsView", () => {
  it("downloads only the filtered entries, not the full unfiltered log", async () => {
    vi.spyOn(client.api, "getLogs").mockResolvedValue({
      logs: [mkEntry(1, "ingest started"), mkEntry(2, "plate solve failed")],
      last_seq: 2,
    });

    let capturedText = "";
    const OriginalBlob = globalThis.Blob;
    vi.spyOn(globalThis, "Blob").mockImplementation((parts?: BlobPart[], opts?: BlobPropertyBag) => {
      capturedText = (parts ?? []).join("");
      return new OriginalBlob(parts, opts);
    });
    URL.createObjectURL = vi.fn(() => "blob:mock");
    URL.revokeObjectURL = vi.fn();
    HTMLAnchorElement.prototype.click = vi.fn();

    renderLogs();
    await waitFor(() => expect(screen.getByText("ingest started")).toBeInTheDocument());

    fireEvent.change(screen.getByPlaceholderText("Filter messages…"), {
      target: { value: "solve" },
    });
    await waitFor(() => expect(screen.queryByText("ingest started")).not.toBeInTheDocument());

    fireEvent.click(screen.getByRole("button", { name: /download/i }));

    expect(capturedText).toContain("plate solve failed");
    expect(capturedText).not.toContain("ingest started");
  });
});
