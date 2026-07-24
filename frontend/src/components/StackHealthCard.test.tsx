import { MantineProvider } from "@mantine/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { StackHealthCard, noteAction, noteColor, visibleNotes } from "./StackHealthCard";
import type { HealthNote, StackHealth } from "../api/client";
import * as client from "../api/client";

function note(over: Partial<HealthNote> = {}): HealthNote {
  return { kind: "solid", severity: "good", message: "Looks solid.", action: null, ...over };
}

function renderCard(safe = "M_42", inEditor = false) {
  return render(
    <MantineProvider>
      <QueryClientProvider client={new QueryClient()}>
        <MemoryRouter>
          <StackHealthCard safe={safe} inEditor={inEditor} />
        </MemoryRouter>
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

describe("noteAction", () => {
  it("wires trim_border to the editor for this run", () => {
    expect(noteAction("trim_border", "M_42", 7)).toEqual({
      label: "Open the editor to trim the border →",
      href: "/targets/M_42/edit/7",
    });
  });
  it("wires calibration to the Calibration page", () => {
    expect(noteAction("calibration", "M_42", 7)?.href).toBe("/calibration");
  });
  it("wires solve_help to the Settings page (star-database status)", () => {
    expect(noteAction("solve_help", "M_42", 7)?.href).toBe("/settings");
    // Still linked inside the editor — it's an off-page action.
    expect(noteAction("solve_help", "M_42", 7, true)?.href).toBe("/settings");
  });
  it("returns null for a note with no wired action", () => {
    expect(noteAction(null, "M_42", 7)).toBeNull();
    expect(noteAction("something_else", "M_42", 7)).toBeNull();
  });
  it("drops the redundant trim_border self-link inside the editor, keeps calibration", () => {
    // In the editor the Trim border button is already on the page, so the
    // trim_border note shouldn't link back to the same page…
    expect(noteAction("trim_border", "M_42", 7, true)).toBeNull();
    // …but an off-page action (calibration) is still worth linking.
    expect(noteAction("calibration", "M_42", 7, true)?.href).toBe("/calibration");
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
    // The actionable note surfaces a one-click link to the wired page.
    const link = screen.getByRole("link", { name: /set up master darks/i });
    expect(link).toHaveAttribute("href", "/calibration");
  });

  it("offers the 'How to add darks' guide beside an uncalibrated note", async () => {
    const health: StackHealth = {
      run_id: 7,
      notes: [
        note({ kind: "calibration", severity: "info",
          message: "No darks or flats were applied.", action: "calibration" }),
      ],
      dark_spec: { exposure_s: 10, gain: 80 },
    };
    vi.spyOn(client.api, "stackHealth").mockResolvedValue(health);
    renderCard();
    // The disclosure appears; expanding it shows the target's own numbers.
    const toggle = await screen.findByText("How to add darks →");
    toggle.click();
    await waitFor(() =>
      expect(screen.getByText(/10 s at gain 80/)).toBeInTheDocument());
  });

  it("does not show the darks guide for a non-calibration note", async () => {
    vi.spyOn(client.api, "stackHealth").mockResolvedValue({
      run_id: 7,
      notes: [note({ kind: "solid", severity: "good", message: "Round stars." })],
      dark_spec: { exposure_s: 10, gain: 80 },
    });
    renderCard();
    await waitFor(() => expect(screen.getByText("Round stars.")).toBeInTheDocument());
    expect(screen.queryByText("How to add darks →")).toBeNull();
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

  it("in the editor, shows a trim_border note's text but not the redundant self-link", async () => {
    vi.spyOn(client.api, "stackHealth").mockResolvedValue({
      run_id: 7,
      notes: [note({ kind: "trim_border", severity: "info",
        message: "Ragged low-coverage border — Trim border to clean it up.",
        action: "trim_border" })],
    });
    renderCard("M_42", true);
    await waitFor(() =>
      expect(screen.getByText(/Ragged low-coverage border/)).toBeInTheDocument());
    // The note is still shown, but with no link back to the page we're already on.
    expect(screen.queryByRole("link", { name: /trim the border/i })).toBeNull();
  });
});
