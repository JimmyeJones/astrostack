import { MantineProvider } from "@mantine/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { LibraryProgressCard } from "./LibraryProgressCard";
import type { TargetProgress } from "../api/client";
import * as client from "../api/client";

function row(over: Partial<TargetProgress> & { safe: string }): TargetProgress {
  return {
    safe: over.safe,
    name: over.name ?? over.safe,
    total_exposure_s: over.total_exposure_s ?? 0,
    object_type: over.object_type ?? null,
    goal_s: over.goal_s ?? null,
  };
}

function renderCard() {
  return render(
    <MantineProvider>
      <MemoryRouter>
        <QueryClientProvider client={new QueryClient()}>
          <LibraryProgressCard />
        </QueryClientProvider>
      </MemoryRouter>
    </MantineProvider>,
  );
}

afterEach(() => vi.restoreAllMocks());

describe("LibraryProgressCard", () => {
  it("summarises and lists targets, nearest-to-goal first", async () => {
    vi.spyOn(client.api, "getLibraryProgress").mockResolvedValue([
      row({ safe: "M_31", name: "M 31", object_type: "galaxy", total_exposure_s: 1 * 3600 }),
      row({ safe: "M_51", name: "M 51", object_type: "galaxy", total_exposure_s: 5 * 3600 }),
      row({ safe: "M_45", name: "M 45", object_type: "cluster", total_exposure_s: 3 * 3600 }),
    ]);
    renderCard();
    await waitFor(() => expect(screen.getByText("Target progress")).toBeInTheDocument());
    expect(
      screen.getByText("2 targets could use more time; 1 has plenty for a clean image."),
    ).toBeInTheDocument();
    // The nearly-there galaxy leads; the finished cluster is last.
    const names = screen.getAllByText(/^M \d+$/).map((n) => n.textContent);
    expect(names).toEqual(["M 51", "M 31", "M 45"]);
    // The finished target carries the "plenty" badge.
    expect(screen.getByText("plenty")).toBeInTheDocument();
  });

  it("labels each row with its object type, and omits it for an unknown type", async () => {
    vi.spyOn(client.api, "getLibraryProgress").mockResolvedValue([
      row({ safe: "M_31", name: "M 31", object_type: "galaxy", total_exposure_s: 1 * 3600 }),
      row({ safe: "Unsorted", name: "Unsorted", object_type: null, total_exposure_s: 1 * 3600 }),
    ]);
    renderCard();
    await waitFor(() => expect(screen.getByText("Target progress")).toBeInTheDocument());
    // The recognised galaxy shows its type next to the goal figure.
    expect(screen.getByText(/galaxy · .* of ~6h/)).toBeInTheDocument();
    // The unknown target shows only the goal, with no "other"/type prefix.
    expect(screen.queryByText(/other ·/)).toBeNull();
  });

  it("renders nothing when no target has collected light", async () => {
    vi.spyOn(client.api, "getLibraryProgress").mockResolvedValue([]);
    const { container } = renderCard();
    await waitFor(() => expect(client.api.getLibraryProgress).toHaveBeenCalled());
    expect(container.querySelector(".mantine-Paper-root")).toBeNull();
  });

  it("caps the list and points to the Library for the rest", async () => {
    vi.spyOn(client.api, "getLibraryProgress").mockResolvedValue(
      Array.from({ length: 8 }, (_, i) =>
        row({ safe: `T_${i}`, name: `T ${i}`, object_type: "galaxy", total_exposure_s: (i + 1) * 600 }),
      ),
    );
    renderCard();
    await waitFor(() => expect(screen.getByText("Target progress")).toBeInTheDocument());
    expect(screen.getByText("+2 more targets in your Library.")).toBeInTheDocument();
  });
});
