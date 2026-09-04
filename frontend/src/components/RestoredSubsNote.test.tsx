import { MantineProvider } from "@mantine/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { RestoredSubsNote } from "./RestoredSubsNote";
import * as client from "../api/client";
import type { RestoredSubs } from "../api/client";

function back(over: Partial<RestoredSubs> = {}): RestoredSubs {
  return {
    run_id: 4,
    timestamp_utc: "2026-08-30T14:32:05Z",
    n_frames_used: 200,
    n_restored: 12,
    ...over,
  };
}

function renderNote(data: RestoredSubs | null | undefined) {
  return render(
    <MantineProvider>
      <QueryClientProvider client={new QueryClient()}>
        <RestoredSubsNote safe="m_42" back={data} />
      </QueryClientProvider>
    </MantineProvider>,
  );
}

afterEach(() => vi.restoreAllMocks());

describe("RestoredSubsNote", () => {
  it("says what came back, and that the picture was made before it did", () => {
    renderNote(back());
    expect(screen.getByTestId("restored-subs-note")).toBeInTheDocument();
    expect(screen.getByText(/12 subs came back after this picture was made/))
      .toBeInTheDocument();
    // The cost half: re-stacking a deep target is hours, never a blind click.
    expect(screen.getByText(/made from 200 subs/)).toBeInTheDocument();
    // Reassurance — the picture they have is not replaced or lost.
    expect(screen.getByText(/stays in this target's history/)).toBeInTheDocument();
  });

  it("reads naturally for a single sub", () => {
    renderNote(back({ n_restored: 1 }));
    expect(screen.getByText(/1 sub came back after this picture was made/))
      .toBeInTheDocument();
    expect(screen.getByText(/had set a sub aside/)).toBeInTheDocument();
  });

  it("only ever offers — the re-stack starts on the click, never before", async () => {
    const proc = vi.spyOn(client.api, "processTarget")
      .mockResolvedValue({ job_id: "j1" });
    renderNote(back());
    expect(proc).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: /Stack it again/ }));
    await waitFor(() => expect(proc).toHaveBeenCalledWith("m_42"));
  });

  it("says nothing when nothing came back", () => {
    renderNote(null);
    expect(screen.queryByTestId("restored-subs-note")).toBeNull();
  });

  it("stays silent on an older backend or a failed fetch", () => {
    renderNote(undefined);
    expect(screen.queryByTestId("restored-subs-note")).toBeNull();
  });
});
