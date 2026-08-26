import { MantineProvider } from "@mantine/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AutoStackHoldNote } from "./AutoStackHoldNote";
import * as client from "../api/client";

function renderNote() {
  return render(
    <MantineProvider>
      <QueryClientProvider client={new QueryClient()}>
        <AutoStackHoldNote safe="m_42" />
      </QueryClientProvider>
    </MantineProvider>,
  );
}

afterEach(() => vi.restoreAllMocks());

describe("AutoStackHoldNote", () => {
  it("explains the hold in the same words and numbers the Jobs page uses", async () => {
    vi.spyOn(client.api, "autoStackHold").mockResolvedValue({
      offered: 787, readable: 271, unreadable: 516,
      reason: "that would be a thinner stack than this target already has",
      when_utc: "2026-08-26T02:00:00Z",
    });
    renderNote();

    await waitFor(() =>
      expect(screen.getByTestId("autostack-hold-note")).toBeInTheDocument());
    expect(screen.getByText(
      /516 of 787 subs couldn't be read on the last scan \(271 still readable\)/,
    )).toBeInTheDocument();
    // The reassurance is the point: a beginner must not think data was lost.
    expect(screen.getByText(/nothing has been lost/)).toBeInTheDocument();
  });

  it("says nothing when the newest scan held nothing back", async () => {
    const spy = vi.spyOn(client.api, "autoStackHold").mockResolvedValue(null);
    renderNote();
    await waitFor(() => expect(spy).toHaveBeenCalled());
    expect(screen.queryByTestId("autostack-hold-note")).toBeNull();
  });

  it("stays silent on an older backend or a failed fetch", async () => {
    const spy = vi.spyOn(client.api, "autoStackHold")
      .mockRejectedValue(new Error("404"));
    renderNote();
    await waitFor(() => expect(spy).toHaveBeenCalled());
    expect(screen.queryByTestId("autostack-hold-note")).toBeNull();
  });
});
