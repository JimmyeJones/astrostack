import { MantineProvider } from "@mantine/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { OverTrimmedTargetNote } from "./OverTrimmedTargetNote";
import * as client from "../../api/client";
import type { CropHealth } from "../../api/client";

function health(overrides: Partial<CropHealth> = {}): CropHealth {
  return {
    // The 2026-09-10 audit's own numbers, from the owner's v0.277.0 recipe.
    stale: true,
    stored_keep_fraction: 0.034,
    suggested_keep_fraction: 0.924,
    suggested_crop: { x0: 0.02, y0: 0.02, x1: 0.98, y1: 0.98 },
    ...overrides,
  };
}

function renderNote(safe = "M_31", runId = 7) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <MantineProvider>
      <QueryClientProvider client={qc}>
        <MemoryRouter>
          <OverTrimmedTargetNote safe={safe} runId={runId} />
        </MemoryRouter>
      </QueryClientProvider>
    </MantineProvider>,
  );
}

afterEach(() => vi.restoreAllMocks());

describe("OverTrimmedTargetNote", () => {
  it("says nothing about a correctly-trimmed picture", async () => {
    vi.spyOn(client.api, "cropHealth").mockResolvedValue(health({ stale: false }));
    renderNote();
    await waitFor(() => expect(client.api.cropHealth).toHaveBeenCalled());
    expect(screen.queryByTestId("over-trimmed-target-note")).not.toBeInTheDocument();
  });

  it("names both numbers and reassures that the stack is untouched", async () => {
    vi.spyOn(client.api, "cropHealth").mockResolvedValue(health());
    renderNote();
    expect(await screen.findByTestId("over-trimmed-target-note")).toBeInTheDocument();
    expect(screen.getByText(/showing about 3% of the frame/i)).toBeInTheDocument();
    expect(screen.getByText(/about 92% of it is well covered/i)).toBeInTheDocument();
    // "My picture is wrong" is the frightening reading; say the stack is safe.
    expect(screen.getByText(/stack itself was never changed/i)).toBeInTheDocument();
  });

  it("sends the user to this run's editor, where the one click lives", async () => {
    vi.spyOn(client.api, "cropHealth").mockResolvedValue(health());
    renderNote("NGC_6888", 12);
    const link = await screen.findByRole("link", { name: /open the editor/i });
    expect(link).toHaveAttribute("href", "/targets/NGC_6888/edit/12");
  });

  it("renders nothing when the endpoint is unavailable", async () => {
    // An older backend, or a failed fetch: best-effort, never an error screen.
    vi.spyOn(client.api, "cropHealth").mockRejectedValue(new Error("404"));
    renderNote();
    await waitFor(() => expect(client.api.cropHealth).toHaveBeenCalled());
    expect(screen.queryByTestId("over-trimmed-target-note")).not.toBeInTheDocument();
  });
});
