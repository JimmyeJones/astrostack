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

describe("LogsView row layout", () => {
  it("lets a long message take its own line instead of being crushed", async () => {
    // Found by the dogfood probe's squeeze check, on the phone screenshot: the
    // row was `wrap="nowrap"` with three `flexShrink: 0` prefix chips taking
    // ~220 px of a 420 px screen, which left the message ~10 px — and
    // `wordBreak: break-word` then set a long path one *character* per line,
    // making a single entry 211 lines tall and the page unusable on a phone.
    // jsdom has no layout, so pin the two causes.
    const path = "/tmp/claude/a-very-long-unbroken-path/with/no/spaces/in/it/at/all";
    vi.spyOn(client.api, "getLogs").mockResolvedValue({
      logs: [mkEntry(1, `watchdog observing ${path}`, "webapp.watcher")],
      last_seq: 1,
    } as never);

    renderLogs();

    const msg = await screen.findByText(`watchdog observing ${path}`);
    // Based on its own content, so it fills a wide row but drops to a line of
    // its own before it can be squeezed under its words.
    expect(msg).toHaveStyle({ flex: "1 1 260px" });
    // …and the row it sits in may wrap, which is what gives it that line.
    const row = msg.parentElement as HTMLElement;
    expect(row.style.getPropertyValue("--group-wrap")).not.toBe("nowrap");
  });

  it("keeps the stamp, level and logger together on one line", async () => {
    vi.spyOn(client.api, "getLogs").mockResolvedValue({
      logs: [mkEntry(1, "ingest started", "webapp.watcher")],
      last_seq: 1,
    } as never);

    renderLogs();

    const logger = await screen.findByText("webapp.watcher");
    const prefix = logger.parentElement as HTMLElement;
    expect(prefix.style.getPropertyValue("--group-wrap")).toBe("nowrap");
    expect(prefix).toHaveStyle({ flexShrink: "0" });
    // The stamp and the level badge are its siblings, not the message's.
    expect(prefix.textContent).toContain("00:00:00");
    expect(prefix.textContent).toContain("INFO");
    expect(prefix.textContent).not.toContain("ingest started");
  });
});
