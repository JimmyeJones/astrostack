import { MantineProvider } from "@mantine/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { App } from "./App";
import { NAV_LINKS, NAV_SECTIONS } from "./nav";
import * as client from "./api/client";

// The sidebar exactly as it stood before IA slice (d) grouped it — order and all.
// The owner's hard constraint on the whole IA overhaul is that *nothing may be
// removed*, so this frozen copy is what "nothing removed" is measured against.
// Regrouping (moving a link between sections, or reordering within one) is fine
// and only needs the set to match; losing or renaming a destination is not.
//
// *Adding* a destination is fine too — the owner's brief for the IA overhaul says
// so explicitly ("even if they need to add pages, that is fine"), so this frozen
// list is asserted as a **subset**, not an equality. An equality would have made
// the guard mean "the sidebar may never grow", which is not the constraint it was
// written for and would have to be relaxed by whoever shipped the next page. What
// it must catch — a destination silently dropped or renamed — is caught either
// way, by the per-entry check below.
const FLAT_LINKS_BEFORE_SLICE_D = [
  { to: "/", label: "Dashboard" },
  { to: "/library", label: "Library" },
  { to: "/telescope", label: "Telescope" },
  { to: "/gallery", label: "Gallery" },
  { to: "/best", label: "My best pictures" },
  { to: "/sky-so-far", label: "Your sky, so far" },
  { to: "/tonight", label: "Tonight" },
  { to: "/moon-sun", label: "Moon & Sun" },
  { to: "/sky", label: "Sky Map" },
  { to: "/jobs", label: "Jobs" },
  { to: "/calibration", label: "Calibration" },
  { to: "/combine", label: "Channel combine" },
  { to: "/storage", label: "Storage" },
  { to: "/logs", label: "Logs" },
  { to: "/settings", label: "Settings" },
];

const byTo = (a: { to: string }, b: { to: string }) => a.to.localeCompare(b.to);

describe("NAV_SECTIONS", () => {
  it("still carries every destination the flat list had, exactly once", () => {
    const present = NAV_LINKS.map((l) => ({ to: l.to, label: l.label })).sort(byTo);
    // Every frozen destination is still there under its own label — a drop or a
    // rename fails here, naming the entry that went missing.
    for (const frozen of [...FLAT_LINKS_BEFORE_SLICE_D].sort(byTo)) {
      expect(present).toContainEqual(frozen);
    }
    expect(new Set(NAV_LINKS.map((l) => l.to)).size).toBe(NAV_LINKS.length);
  });

  it("keeps every added destination distinct from the frozen ones", () => {
    // Growth is allowed, but a new page must be a genuinely new destination —
    // not a second route quietly shadowing an existing one under a new label.
    const frozenPaths = new Set(FLAT_LINKS_BEFORE_SLICE_D.map((l) => l.to));
    const frozenLabels = new Set(FLAT_LINKS_BEFORE_SLICE_D.map((l) => l.label));
    for (const added of NAV_LINKS.filter((l) => !frozenPaths.has(l.to))) {
      expect(frozenLabels.has(added.label)).toBe(false);
    }
  });

  it("keeps the Dashboard exact-match only, so it doesn't light up on every route", () => {
    const home = NAV_LINKS.find((l) => l.to === "/");
    expect(home?.end).toBe(true);
    // Every other link matches by path segment, so none of them may claim `end`.
    expect(NAV_LINKS.filter((l) => l.to !== "/" && l.end)).toEqual([]);
  });

  it("groups into a few named sections, with only the lead group unlabelled", () => {
    expect(NAV_SECTIONS.length).toBeLessThanOrEqual(6);
    expect(NAV_SECTIONS[0].title).toBeNull();
    expect(NAV_SECTIONS.slice(1).every((s) => !!s.title)).toBe(true);
    // A heading over one link is noise; every labelled group earns its heading.
    expect(NAV_SECTIONS.slice(1).every((s) => s.links.length >= 2)).toBe(true);
    expect(new Set(NAV_SECTIONS.map((s) => s.title)).size).toBe(NAV_SECTIONS.length);
  });
});

function renderApp(outdated = 0, at = "/") {
  vi.spyOn(client.api, "listJobs").mockResolvedValue([]);
  vi.spyOn(client.api, "getSystem").mockResolvedValue({ version: "9.9.9" } as never);
  vi.spyOn(client.api, "reprocessStatus").mockResolvedValue({ outdated } as never);
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <MantineProvider>
      <QueryClientProvider client={qc}>
        <MemoryRouter initialEntries={[at]}>
          <App />
        </MemoryRouter>
      </QueryClientProvider>
    </MantineProvider>,
  );
}

const FOLDED = new Set(NAV_SECTIONS.filter((s) => s.folded).flatMap((s) => s.links.map((l) => l.to)));

describe("sidebar", () => {
  it("renders every link visibly except the Extras, which are one click away", async () => {
    renderApp();
    const nav = screen.getByRole("navigation");
    for (const l of FLAT_LINKS_BEFORE_SLICE_D.filter((x) => !FOLDED.has(x.to))) {
      const link = within(nav).getByRole("link", { name: new RegExp(`^${l.label}$`) });
      expect(link).toHaveAttribute("href", l.to);
    }
    // The owner's choice (2026-11-28): only "Extras" folds, and one click opens it.
    expect(NAV_SECTIONS.filter((s) => s.folded).map((s) => s.title)).toEqual(["Extras"]);
    fireEvent.click(within(nav).getByRole("button", { name: /Extras/ }));
    for (const to of FOLDED) {
      const l = NAV_LINKS.find((x) => x.to === to)!;
      const link = await within(nav).findByRole("link", { name: new RegExp(`^${l.label}$`) });
      expect(link).toHaveAttribute("href", to);
    }
  });

  it("opens Extras by itself on one of its pages", async () => {
    renderApp(0, "/life-list");
    const nav = screen.getByRole("navigation");
    expect(await within(nav).findByRole("link", { name: /^My life list$/ }))
      .toHaveAttribute("href", "/life-list");
  });

  it("shows a heading for each named group, and each group holds its own links", () => {
    renderApp();
    const nav = screen.getByRole("navigation");
    for (const section of NAV_SECTIONS) {
      if (!section.title) continue;
      const group = within(nav).getByRole("group", { name: section.title });
      if (section.folded) fireEvent.click(within(group).getByRole("button", { name: section.title }));
      for (const l of section.links) {
        expect(within(group).getByRole("link", { name: new RegExp(`^${l.label}$`) })).toBeTruthy();
      }
    }
  });

  it("reads one out-of-date target as '1 target', not '1 targets'", async () => {
    renderApp(1);
    expect(await screen.findByLabelText("1 target out of date")).toBeInTheDocument();
    expect(screen.queryByLabelText("1 targets out of date")).toBeNull();
  });

  it("keeps the plural for several", async () => {
    renderApp(3);
    expect(await screen.findByLabelText("3 targets out of date")).toBeInTheDocument();
  });
});
