import { MantineProvider } from "@mantine/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { applyFilter, LifeListView } from "./LifeList";
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

  it("gives up a still-to-shoot object's blurb to a tap, not only to a hover", async () => {
    // The "still to shoot" half of this page is where a beginner decides what
    // to point at next, and the blurb is the only sentence saying what the
    // object *is*. An uncaptured tile has nothing to click, so before
    // `HintAnchor` a tap did nothing and — on the device this app is mostly
    // read on — the sentence was not written anywhere.
    vi.spyOn(client.api, "getLifeList").mockResolvedValue(list());
    renderList();
    const tile = await screen.findByText("M42 · Orion Nebula");
    expect(screen.queryByText("The closest big star factory to us.")).toBeNull();
    fireEvent.click(tile);
    expect(await screen.findByText("The closest big star factory to us."))
      .toBeInTheDocument();
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

  it("says nothing about a wishlist until something is on it", async () => {
    // The standing IA rule: a new feature must not become one more always-on
    // block. A fresh install (and an older backend, which 404s) sees exactly
    // today's page.
    vi.spyOn(client.api, "getLifeList").mockResolvedValue(list());
    vi.spyOn(client.api, "getWishlist")
      .mockResolvedValue({ items: [], counts: { saved: 0, captured: 0 } });
    renderList();

    await waitFor(() => expect(screen.getByText(/M31 · Andromeda Galaxy/))
      .toBeInTheDocument());
    expect(screen.queryByText("My wishlist")).not.toBeInTheDocument();
  });

  it("leads with your own shortlist once you've starred something", async () => {
    vi.spyOn(client.api, "getLifeList").mockResolvedValue(list());
    vi.spyOn(client.api, "getWishlist").mockResolvedValue({
      items: [{
        catalog_id: "M42", name: "Orion Nebula", type: "nebula", con: "Ori",
        blurb: "", size_arcmin: null, added_utc: "2026-09-07T00:00:00Z",
        captured: false, safe_name: null, target_name: null, thumbnail_url: null,
      }],
      counts: { saved: 1, captured: 0 },
    });
    renderList();

    await waitFor(() => expect(screen.getByText("My wishlist")).toBeInTheDocument());
    expect(screen.getByText(/One object you said you want to shoot/))
      .toBeInTheDocument();
    // And every tile carries the toggle that put it there.
    expect(screen.getAllByTestId("wishlist-star-M42").length).toBeGreaterThan(0);
  });

  it("offers the grid as one shareable picture once you've captured something", async () => {
    vi.spyOn(client.api, "getLifeList").mockResolvedValue(list());
    renderList();

    const link = await screen.findByRole("link", { name: /Share my grid/ });
    expect(link).toHaveAttribute("href", "/api/life-list/grid.jpg");
    expect(link).toHaveAttribute("download");
    expect(screen.getByText(/All 110 squares as one picture/)).toBeInTheDocument();
  });

  // "Up tonight" — the other half of this page's own headline. The list invites
  // a beginner to "pick one and point the scope at it tonight" and then shows
  // them M1…M12, an order chosen in the 1770s with no relationship to what is
  // above the horizon this evening.
  const upTonight = (ids: string[], over: Partial<client.LifeListTonight> = {}) => ({
    ids, location_source: "settings", min_altitude_deg: 30, ...over,
  });

  it("offers no 'Up tonight' chip when the sky can't answer", async () => {
    // No observing location set, an older backend (the route 404s), or a night
    // on which nothing clears the floor: the page is exactly the page it was,
    // minus one chip — never an error and never an empty view.
    vi.spyOn(client.api, "getLifeList").mockResolvedValue(list());
    vi.spyOn(client.api, "lifeListTonight")
      .mockResolvedValue(upTonight([], { location_source: "none" }));
    renderList();

    await waitFor(() => expect(screen.getByText("M42 · Orion Nebula")).toBeInTheDocument());
    expect(screen.queryByText("Up tonight")).not.toBeInTheDocument();
  });

  it("keeps the page whole when the tonight route isn't there at all", async () => {
    vi.spyOn(client.api, "getLifeList").mockResolvedValue(list());
    vi.spyOn(client.api, "lifeListTonight").mockRejectedValue(new Error("404"));
    renderList();

    await waitFor(() => expect(screen.getByText("M42 · Orion Nebula")).toBeInTheDocument());
    expect(screen.queryByText("Up tonight")).not.toBeInTheDocument();
    // A filter that can't be offered must not become the page's error card.
    expect(screen.queryByText("404")).not.toBeInTheDocument();
  });

  it("narrows the list to what is actually shootable tonight", async () => {
    vi.spyOn(client.api, "getLifeList").mockResolvedValue(list());
    vi.spyOn(client.api, "lifeListTonight").mockResolvedValue(upTonight(["M42"]));
    renderList();

    await waitFor(() => expect(screen.getByText("Up tonight")).toBeInTheDocument());
    fireEvent.click(screen.getByText("Up tonight"));

    expect(screen.getByText("M42 · Orion Nebula")).toBeInTheDocument();
    // M31 is captured and NGC 7000 is not — neither is up, so neither shows.
    expect(screen.queryByText("M31 · Andromeda Galaxy")).not.toBeInTheDocument();
    expect(screen.queryByText("NGC 7000 · North America Nebula")).not.toBeInTheDocument();
    // The count and the altitude floor both come off the answer, not the
    // browser — and one object is "One object … climbs", not "1 objects".
    expect(screen.getByText(/One object on this list climbs above 30°/))
      .toBeInTheDocument();
  });

  it("orders tonight's view by the planner's answer, not by catalog number", async () => {
    // This is the one view where catalog order says nothing: "which of these
    // should I point at this evening?" has a best answer, and the server ranks
    // it. M42 is second in the catalog half below and first in the sky.
    vi.spyOn(client.api, "getLifeList").mockResolvedValue(list({
      messier: [
        obj({ catalog_id: "M1", name: "Crab Nebula" }),
        obj({ catalog_id: "M42", name: "Orion Nebula" }),
        obj({ catalog_id: "M45", name: "Pleiades" }),
      ],
      other: [],
      counts: { messier_captured: 0, messier_total: 110, other_captured: 0, other_total: 47 },
    }));
    vi.spyOn(client.api, "lifeListTonight")
      .mockResolvedValue(upTonight(["M45", "M42", "M1"]));
    renderList();

    await waitFor(() => expect(screen.getByText("Up tonight")).toBeInTheDocument());
    fireEvent.click(screen.getByText("Up tonight"));

    const titles = screen.getAllByText(/^M\d+ · /).map((e) => e.textContent);
    expect(titles).toEqual(["M45 · Pleiades", "M42 · Orion Nebula", "M1 · Crab Nebula"]);
    // ...and the plural branch of the same sentence.
    expect(screen.getByText(/3 objects on this list climb above 30°/))
      .toBeInTheDocument();
  });

  it("never shortens tonight's list either — the sky already narrowed it", async () => {
    vi.spyOn(client.api, "getLifeList").mockResolvedValue(list({
      messier: many(30, false), other: [],
      counts: { messier_captured: 0, messier_total: 30, other_captured: 0, other_total: 0 },
    }));
    vi.spyOn(client.api, "lifeListTonight").mockResolvedValue(
      upTonight(Array.from({ length: 30 }, (_, i) => `M${i + 1}`)));
    renderList();

    await waitFor(() => expect(screen.getByText("Up tonight")).toBeInTheDocument());
    fireEvent.click(screen.getByText("Up tonight"));

    expect(screen.getByText("M30 · Object 30")).toBeInTheDocument();
    expect(screen.queryByText(/Show all 30/)).not.toBeInTheDocument();
  });

  it("says why a half is empty tonight instead of claiming you've got them all", async () => {
    vi.spyOn(client.api, "getLifeList").mockResolvedValue(list());
    // Only a Messier object is up, so the "Also worth getting" half has none —
    // and its usual empty line ("You've got every one of these") would be a lie.
    vi.spyOn(client.api, "lifeListTonight").mockResolvedValue(upTonight(["M42"]));
    renderList();

    await waitFor(() => expect(screen.getByText("Up tonight")).toBeInTheDocument());
    fireEvent.click(screen.getByText("Up tonight"));

    expect(screen.getByText(/they're a different season's sky/)).toBeInTheDocument();
    expect(screen.queryByText(/You've got every one of these/)).not.toBeInTheDocument();
  });

  it("hides the share offer on a fresh install", async () => {
    // A grid of grey squares is a picture of Messier's catalogue, not of your
    // sky — and the endpoint 404s there, so the button must not be offered.
    vi.spyOn(client.api, "getLifeList").mockResolvedValue(list({
      messier: [obj({ catalog_id: "M31", name: "Andromeda Galaxy" })],
      counts: {
        messier_captured: 0, messier_total: 110,
        other_captured: 0, other_total: 47,
      },
    }));
    renderList();

    await waitFor(() => expect(screen.getByText(/All 110 Messier objects are still ahead/))
      .toBeInTheDocument());
    expect(screen.queryByRole("link", { name: /Share my grid/ })).not.toBeInTheDocument();
  });
});

describe("applyFilter", () => {
  const items = [
    obj({ catalog_id: "M1", captured: false }),
    obj({ catalog_id: "M31", captured: true }),
    obj({ catalog_id: "M42", captured: false }),
  ];
  const ids = (xs: typeof items) => xs.map((i) => i.catalog_id);

  it("leaves catalog order alone for every view except tonight's", () => {
    expect(ids(applyFilter(items, "all", null))).toEqual(["M1", "M31", "M42"]);
    expect(ids(applyFilter(items, "captured", null))).toEqual(["M31"]);
    expect(ids(applyFilter(items, "todo", null))).toEqual(["M1", "M42"]);
    // A rank map must not reorder a view that isn't tonight's.
    const rank = new Map([["M42", 0], ["M1", 1], ["M31", 2]]);
    expect(ids(applyFilter(items, "all", rank))).toEqual(["M1", "M31", "M42"]);
  });

  it("keeps only what is ranked, in the planner's order", () => {
    const rank = new Map([["M42", 0], ["M1", 1]]);
    expect(ids(applyFilter(items, "tonight", rank))).toEqual(["M42", "M1"]);
  });

  it("keeps a captured object that is up — the filter is about sky, not collection", () => {
    expect(ids(applyFilter(items, "tonight", new Map([["M31", 0]])))).toEqual(["M31"]);
  });

  it("shows nothing rather than everything when there is no answer to filter by", () => {
    // `effectiveFilter` in the view should never let this happen; if it ever
    // did, an unfiltered, unordered "tonight" list would be a claim about the
    // sky that nothing measured.
    expect(applyFilter(items, "tonight", null)).toEqual([]);
  });
});
