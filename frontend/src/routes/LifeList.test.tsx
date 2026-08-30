import { MantineProvider } from "@mantine/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { LifeListView } from "./LifeList";
import * as client from "../api/client";
import type { LifeList, LifeListItem } from "../api/client";

function obj(over: Partial<LifeListItem>): LifeListItem {
  return {
    catalog_id: "M1", name: "", type: "galaxy", con: "And", blurb: "",
    size_arcmin: null, captured: false, safe_name: null, target_name: null,
    sep_deg: null, thumbnail_url: null, ...over,
  };
}

function list(over: Partial<LifeList> = {}): LifeList {
  return {
    messier: [
      obj({
        catalog_id: "M31", name: "Andromeda Galaxy", captured: true,
        safe_name: "M_31", target_name: "M 31", sep_deg: 0.01,
        thumbnail_url: "/api/targets/M_31/thumbnail",
      }),
      obj({ catalog_id: "M42", name: "Orion Nebula", type: "nebula", con: "Ori",
            blurb: "The closest big star factory to us." }),
    ],
    other: [obj({ catalog_id: "NGC 7000", name: "North America Nebula", con: "Cyg" })],
    counts: {
      messier_captured: 1, messier_total: 110,
      other_captured: 0, other_total: 47,
    },
    ...over,
  };
}

function renderList() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <MantineProvider>
      <QueryClientProvider client={qc}>
        <MemoryRouter><LifeListView /></MemoryRouter>
      </QueryClientProvider>
    </MantineProvider>,
  );
}

afterEach(() => vi.restoreAllMocks());

describe("LifeListView", () => {
  it("leads with the count a beginner is actually counting", async () => {
    vi.spyOn(client.api, "getLifeList").mockResolvedValue(list());
    renderList();

    await waitFor(() => expect(
      screen.getByText("You've captured 1 of 110 Messier objects — 109 to go."),
    ).toBeInTheDocument());
  });

  it("says the whole list is ahead of you when nothing is captured yet", async () => {
    vi.spyOn(client.api, "getLifeList").mockResolvedValue(list({
      messier: [obj({ catalog_id: "M31" })],
      counts: { messier_captured: 0, messier_total: 110, other_captured: 0, other_total: 47 },
    }));
    renderList();

    await waitFor(() => expect(
      screen.getByText(/All 110 Messier objects are still ahead of you/),
    ).toBeInTheDocument());
  });

  it("congratulates a finished list rather than saying '0 to go'", async () => {
    vi.spyOn(client.api, "getLifeList").mockResolvedValue(list({
      counts: { messier_captured: 110, messier_total: 110, other_captured: 5, other_total: 47 },
    }));
    renderList();

    await waitFor(() => expect(
      screen.getByText(/captured all 110 Messier objects/),
    ).toBeInTheDocument());
  });

  it("shows captured and uncaptured objects together, labelled in plain words", async () => {
    vi.spyOn(client.api, "getLifeList").mockResolvedValue(list());
    renderList();

    await waitFor(() => expect(
      screen.getByText("M31 · Andromeda Galaxy"),
    ).toBeInTheDocument());
    // The bucket list is the point — an object you haven't got is still listed.
    expect(screen.getByText("M42 · Orion Nebula")).toBeInTheDocument();
    expect(screen.getByText("NGC 7000 · North America Nebula")).toBeInTheDocument();
    // ...each with a plain-language identity rather than a bare catalog row.
    expect(screen.getByText("Nebula in Ori")).toBeInTheDocument();
    expect(screen.getByText("Galaxy in And")).toBeInTheDocument();
  });

  it("links a captured object straight to its target", async () => {
    vi.spyOn(client.api, "getLifeList").mockResolvedValue(list());
    renderList();

    await waitFor(() => expect(screen.getByText("M31 · Andromeda Galaxy")).toBeInTheDocument());
    const link = screen.getByText("M31 · Andromeda Galaxy").closest("a");
    expect(link).toHaveAttribute("href", "/targets/M_31");
    // An object with no capture has nowhere to go, so it must not be a link.
    expect(screen.getByText("M42 · Orion Nebula").closest("a")).toBeNull();
  });

  it("marks what you already have", async () => {
    vi.spyOn(client.api, "getLifeList").mockResolvedValue(list());
    renderList();

    await waitFor(() => expect(screen.getByText("Got it")).toBeInTheDocument());
    // Exactly one of the three objects is captured.
    expect(screen.getAllByText("Got it")).toHaveLength(1);
  });

  it("filters down to just what's left to shoot", async () => {
    vi.spyOn(client.api, "getLifeList").mockResolvedValue(list());
    renderList();
    await waitFor(() => expect(screen.getByText("M31 · Andromeda Galaxy")).toBeInTheDocument());

    fireEvent.click(screen.getByText("Still to shoot"));

    expect(screen.queryByText("M31 · Andromeda Galaxy")).not.toBeInTheDocument();
    expect(screen.getByText("M42 · Orion Nebula")).toBeInTheDocument();
  });

  it("filters down to the collection", async () => {
    vi.spyOn(client.api, "getLifeList").mockResolvedValue(list());
    renderList();
    await waitFor(() => expect(screen.getByText("M42 · Orion Nebula")).toBeInTheDocument());

    fireEvent.click(screen.getByText("Captured"));

    expect(screen.getByText("M31 · Andromeda Galaxy")).toBeInTheDocument();
    expect(screen.queryByText("M42 · Orion Nebula")).not.toBeInTheDocument();
    // The empty half says something encouraging rather than nothing at all.
    expect(
      screen.getByText(/None of these yet — every one of them is still ahead of you./),
    ).toBeInTheDocument();
  });

  it("tells the user why an object might still look grey", async () => {
    vi.spyOn(client.api, "getLifeList").mockResolvedValue(list());
    renderList();

    await waitFor(() => expect(
      screen.getByText(/stays greyed out until it's solved/),
    ).toBeInTheDocument());
  });

  // The page rendered every catalog tile eagerly, which made it the tallest
  // screen in the app by nearly 3× (14,584 px on a 420 px phone) — and all of
  // that height was objects the owner hasn't shot yet, scrolled past to reach
  // the ones they have. Nothing may be removed, so the tail collapses behind a
  // count instead.
  const many = (n: number, captured: boolean) =>
    Array.from({ length: n }, (_, i) =>
      obj({ catalog_id: `M${i + 1}`, name: `Object ${i + 1}`, captured,
            safe_name: captured ? `M_${i + 1}` : null }));

  it("collapses the not-yet-shot tail behind a count, and opens it on request", async () => {
    vi.spyOn(client.api, "getLifeList").mockResolvedValue(list({
      messier: many(30, false), other: [],
      counts: { messier_captured: 0, messier_total: 30, other_captured: 0, other_total: 0 },
    }));
    renderList();

    await waitFor(() => expect(screen.getByText("M1 · Object 1")).toBeInTheDocument());
    // Only the first dozen are drawn...
    expect(screen.getByText("M12 · Object 12")).toBeInTheDocument();
    expect(screen.queryByText("M13 · Object 13")).not.toBeInTheDocument();
    expect(screen.queryByText("M30 · Object 30")).not.toBeInTheDocument();

    // ...and the rest are one tap away, never gone.
    fireEvent.click(screen.getByText("Show all 30 still to shoot"));
    expect(screen.getByText("M13 · Object 13")).toBeInTheDocument();
    expect(screen.getByText("M30 · Object 30")).toBeInTheDocument();

    fireEvent.click(screen.getByText("Show fewer"));
    expect(screen.queryByText("M30 · Object 30")).not.toBeInTheDocument();
  });

  it("puts what you've already got above what's still ahead of you", async () => {
    vi.spyOn(client.api, "getLifeList").mockResolvedValue(list({
      messier: [
        obj({ catalog_id: "M1", name: "Crab" }),
        ...many(3, true).map((o, i) => obj({ ...o, catalog_id: `M${i + 40}`,
                                            name: `Got ${i + 1}` })),
      ],
      other: [],
      counts: { messier_captured: 3, messier_total: 110, other_captured: 0, other_total: 0 },
    }));
    renderList();

    await waitFor(() => expect(screen.getByText("Got it · 3")).toBeInTheDocument());
    expect(screen.getByText("Still to shoot · 1")).toBeInTheDocument();
    const titles = screen.getAllByText(/^M\d+ · (Crab|Got \d)$/).map((e) => e.textContent);
    expect(titles).toEqual(["M40 · Got 1", "M41 · Got 2", "M42 · Got 3", "M1 · Crab"]);
  });

  it("never shortens the list the user explicitly asked for", async () => {
    vi.spyOn(client.api, "getLifeList").mockResolvedValue(list({
      messier: many(30, false), other: [],
      counts: { messier_captured: 0, messier_total: 30, other_captured: 0, other_total: 0 },
    }));
    renderList();
    await waitFor(() => expect(screen.getByText("M1 · Object 1")).toBeInTheDocument());

    fireEvent.click(screen.getByText("Still to shoot"));

    expect(screen.getByText("M30 · Object 30")).toBeInTheDocument();
    expect(screen.queryByText(/Show all 30/)).not.toBeInTheDocument();
  });

  it("shows a fetch failure instead of spinning forever", async () => {
    vi.spyOn(client.api, "getLifeList").mockRejectedValue(new Error("boom"));
    renderList();

    await waitFor(() => expect(screen.getByText("boom")).toBeInTheDocument());
  });
});
