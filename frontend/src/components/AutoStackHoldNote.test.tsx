import { MantineProvider } from "@mantine/core";
import { Notifications } from "@mantine/notifications";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AutoStackHoldNote } from "./AutoStackHoldNote";
import * as client from "../api/client";

function renderNote() {
  return render(
    <MantineProvider>
      <Notifications />
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

describe("AutoStackHoldNote — \"those subs are gone\"", () => {
  // A8. The hold is right while the files are coming back and a dead end when
  // the owner deleted them himself: the rows stay, `unreadable` never drops, and
  // every scan for the rest of time reports the same hold. He was told, and
  // offered nothing to do. This is the one thing to do.
  function held() {
    vi.spyOn(client.api, "autoStackHold").mockResolvedValue({
      offered: 13, readable: 9, unreadable: 4,
      reason: "that would be a thinner stack than this target already has",
      when_utc: "2026-09-02T02:00:00Z",
    });
  }

  it("offers the action, and says it is records-only and self-undoing", async () => {
    held();
    renderNote();
    await screen.findByTestId("autostack-hold-note");
    expect(screen.getByTestId("set-missing-aside")).toBeInTheDocument();
    expect(screen.getByText(/your files are never touched/)).toBeInTheDocument();
    expect(screen.getByText(/put back automatically/)).toBeInTheDocument();
  });

  it("sets the missing subs aside and then offers an undo", async () => {
    held();
    const aside = vi.spyOn(client.api, "setMissingAside")
      .mockResolvedValue({ changed: 4, changed_ids: [1, 2, 3, 4] });
    const bulk = vi.spyOn(client.api, "bulkFrames")
      .mockResolvedValue({ changed: 4, changed_ids: [1, 2, 3, 4] });
    renderNote();

    fireEvent.click(await screen.findByTestId("set-missing-aside"));
    await waitFor(() => expect(aside).toHaveBeenCalledWith("m_42"));

    // The undo is the existing bulk accept of exactly the ids it touched — no
    // second undo path to keep in step with the first.
    fireEvent.click(await screen.findByTestId("undo-missing-aside"));
    await waitFor(() => expect(bulk).toHaveBeenCalledWith(
      "m_42", { action: "accept", ids: [1, 2, 3, 4] }));
    await waitFor(() =>
      expect(screen.queryByTestId("undo-missing-aside")).toBeNull());
  });

  it("offers no undo when there was nothing to set aside", async () => {
    held();
    vi.spyOn(client.api, "setMissingAside")
      .mockResolvedValue({ changed: 0, changed_ids: [] });
    renderNote();
    fireEvent.click(await screen.findByTestId("set-missing-aside"));
    await waitFor(() =>
      expect(screen.getByText(/every sub is readable again/)).toBeInTheDocument());
    expect(screen.queryByTestId("undo-missing-aside")).toBeNull();
  });
});
