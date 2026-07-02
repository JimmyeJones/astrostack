import { MantineProvider } from "@mantine/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { BackupRestore } from "./Settings";
import * as client from "../api/client";

function renderView() {
  const qc = new QueryClient();
  return render(
    <MantineProvider>
      <QueryClientProvider client={qc}>
        <BackupRestore />
      </QueryClientProvider>
    </MantineProvider>,
  );
}

afterEach(() => vi.restoreAllMocks());

describe("BackupRestore", () => {
  it("exports settings and triggers a JSON download", async () => {
    const exp = vi.spyOn(client.api, "exportSettings")
      .mockResolvedValue({ astrostack_settings: true, settings: { auto_qc: true } });
    // jsdom lacks these; stub so the download path doesn't throw.
    const createUrl = vi.fn(() => "blob:x");
    URL.createObjectURL = createUrl;
    URL.revokeObjectURL = vi.fn();
    const clickSpy = vi
      .spyOn(HTMLAnchorElement.prototype, "click")
      .mockImplementation(() => {});

    renderView();
    fireEvent.click(screen.getByRole("button", { name: /Export settings/ }));

    await waitFor(() => expect(exp).toHaveBeenCalled());
    await waitFor(() => expect(createUrl).toHaveBeenCalled());
    expect(clickSpy).toHaveBeenCalled();
  });

  it("imports a chosen JSON file's contents", async () => {
    const imp = vi.spyOn(client.api, "importSettings")
      .mockResolvedValue({ auto_ingest: false } as never);
    const { container } = renderView();

    const input = container.querySelector('input[type="file"]') as HTMLInputElement;
    const file = new File(
      [JSON.stringify({ settings: { auto_ingest: false } })],
      "backup.json",
      { type: "application/json" },
    );
    fireEvent.change(input, { target: { files: [file] } });

    await waitFor(() =>
      expect(imp).toHaveBeenCalledWith({ settings: { auto_ingest: false } }));
  });
});
