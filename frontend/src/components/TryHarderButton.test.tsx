import { MantineProvider } from "@mantine/core";
import { Notifications } from "@mantine/notifications";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { TryHarderButton } from "./TryHarderButton";
import * as client from "../api/client";

function renderButton(safe = "M_42") {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <MantineProvider>
      <Notifications />
      <QueryClientProvider client={qc}>
        <TryHarderButton safe={safe} />
      </QueryClientProvider>
    </MantineProvider>,
  );
}

/** The only field of the reject-summary this component reads. */
function summary(over: Record<string, unknown> = {}) {
  return {
    counts: {}, total: 0, n_missing_files: 0, n_accepted: 10, ...over,
  } as unknown as Awaited<ReturnType<typeof client.api.rejectSummary>>;
}

afterEach(() => vi.restoreAllMocks());

describe("TryHarderButton", () => {
  it("offers the rescue when the server says it would engage", async () => {
    vi.spyOn(client.api, "rejectSummary")
      .mockResolvedValue(summary({ deep_rescue_offered: true }));
    const rescue = vi.spyOn(client.api, "rescueUnsolved")
      .mockResolvedValue({ job_id: "job-9" });

    renderButton();
    const btn = await screen.findByRole("button", { name: "Try harder to locate these" });
    fireEvent.click(btn);
    await waitFor(() => expect(rescue).toHaveBeenCalledWith("M_42"));
  });

  it("renders nothing where the rescue would stand down", async () => {
    // A target with too few un-located subs, or one that has never been
    // plate-solved: the advice above this is still useful, a dead button is not.
    vi.spyOn(client.api, "rejectSummary")
      .mockResolvedValue(summary({ deep_rescue_offered: false }));
    const { container } = renderButton();
    await waitFor(() => expect(client.api.rejectSummary).toHaveBeenCalled());
    expect(container.querySelector("button")).toBeNull();
  });

  it("renders nothing against an older backend that omits the field", async () => {
    vi.spyOn(client.api, "rejectSummary").mockResolvedValue(summary());
    const { container } = renderButton();
    await waitFor(() => expect(client.api.rejectSummary).toHaveBeenCalled());
    expect(container.querySelector("button")).toBeNull();
  });

  it("renders nothing while it is still asking, and nothing if the read fails", async () => {
    vi.spyOn(client.api, "rejectSummary").mockRejectedValue(new Error("boom"));
    const { container } = renderButton();
    expect(container.querySelector("button")).toBeNull();  // still loading
    await waitFor(() => expect(client.api.rejectSummary).toHaveBeenCalled());
    expect(container.querySelector("button")).toBeNull();  // and after it failed
  });

  it("surfaces a failure to start the job rather than swallowing it", async () => {
    vi.spyOn(client.api, "rejectSummary")
      .mockResolvedValue(summary({ deep_rescue_offered: true }));
    vi.spyOn(client.api, "rescueUnsolved")
      .mockRejectedValue(new Error("Storage is read-only"));

    renderButton();
    fireEvent.click(
      await screen.findByRole("button", { name: "Try harder to locate these" }),
    );
    expect(await screen.findByText("Storage is read-only")).toBeInTheDocument();
  });
});
