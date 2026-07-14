import { MantineProvider } from "@mantine/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { StackHealthCard, noteColor, visibleNotes } from "./StackHealthCard";
import type { HealthNote, StackHealth } from "../api/client";
import * as client from "../api/client";

function note(over: Partial<HealthNote> = {}): HealthNote {
  return { kind: "solid", severity: "good", message: "Looks solid.", action: null, ...over };
}

function renderCard(safe = "M_42") {
  return render(
    <MantineProvider>
      <QueryClientProvider client={new QueryClient()}>
        <StackHealthCard safe={safe} />
      </QueryClientProvider>
    </MantineProvider>,
  );
}

afterEach(() => vi.restoreAllMocks());

describe("visibleNotes", () => {
  it("shows at most the top two notes, best-first (backend already ranked)", () => {
    const notes = [note({ kind: "a" }), note({ kind: "b" }), note({ kind: "c" })];
    expect(visibleNotes(notes).map((n) => n.kind)).toEqual(["a", "b"]);
  });
  it("passes through when there are fewer than two", () => {
    expect(visibleNotes([note({ kind: "a" })]).map((n) => n.kind)).toEqual(["a"]);
  });
});

describe("noteColor", () => {
  it("maps severity to a gentle colour", () => {
    expect(noteColor("good")).toBe("teal");
    expect(noteColor("info")).toBe("blue");
  });
});

describe("StackHealthCard", () => {
  it("renders the top notes for a graded stack", async () => {
    const health: StackHealth = {
      run_id: 7,
      notes: [
        note({ kind: "calibration", severity: "info",
          message: "No darks or flats were applied.", action: "calibration" }),
        note({ kind: "solid", severity: "good", message: "Round stars." }),
      ],
    };
    vi.spyOn(client.api, "stackHealth").mockResolvedValue(health);
    renderCard();
    await waitFor(() =>
      expect(screen.getByText("How's my stack?")).toBeInTheDocument());
    expect(screen.getByText("No darks or flats were applied.")).toBeInTheDocument();
    expect(screen.getByText("Round stars.")).toBeInTheDocument();
  });

  it("renders nothing when there is no stack to grade", async () => {
    vi.spyOn(client.api, "stackHealth").mockResolvedValue(null);
    const { container } = renderCard();
    await waitFor(() => expect(client.api.stackHealth).toHaveBeenCalled());
    expect(container.querySelector(".mantine-Paper-root")).toBeNull();
  });

  it("renders nothing when the note list is empty", async () => {
    vi.spyOn(client.api, "stackHealth").mockResolvedValue({ run_id: 1, notes: [] });
    const { container } = renderCard();
    await waitFor(() => expect(client.api.stackHealth).toHaveBeenCalled());
    expect(container.querySelector(".mantine-Paper-root")).toBeNull();
  });
});
