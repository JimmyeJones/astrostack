import { MantineProvider } from "@mantine/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { GlossaryView } from "./Glossary";
import * as client from "../api/client";
import type { Glossary } from "../api/client";

const GLOSSARY: Glossary = {
  intro: "Plain-language explanations of every term used in the interface.",
  terms: [
    { slug: "drizzle", term: "Drizzle",
      body: "Higher resolution from **dithered** frames." },
    { slug: "fwhm", term: "FWHM (full width at half maximum)",
      body: "How sharp a star looks. Smaller is sharper." },
    { slug: "sigma-clipping", term: "Sigma clipping",
      body: "Removes satellite trails from the stack." },
  ],
};

function renderPage(data: Glossary | Error = GLOSSARY) {
  if (data instanceof Error) vi.spyOn(client.api, "getGlossary").mockRejectedValue(data);
  else vi.spyOn(client.api, "getGlossary").mockResolvedValue(data);
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <MantineProvider>
      <QueryClientProvider client={qc}>
        <MemoryRouter><GlossaryView /></MemoryRouter>
      </QueryClientProvider>
    </MantineProvider>,
  );
}

function search(text: string) {
  fireEvent.change(screen.getByTestId("glossary-search"), { target: { value: text } });
}

// Mantine keeps a closed panel mounted and collapses it to `height: 0` with
// `aria-hidden`/`inert`, so "is it open?" is a question about the control's
// `aria-expanded`, never about whether the words are in the DOM. (The zero
// height is exactly what makes the page short, and is pinned on its own below.)
function isOpen(slug: string): boolean {
  return screen.getByTestId(`glossary-control-${slug}`)
    .getAttribute("aria-expanded") === "true";
}

afterEach(() => {
  vi.restoreAllMocks();
  window.location.hash = "";
});

describe("Glossary page", () => {
  it("lists every term, closed, with the intro from the file", async () => {
    // Closed is the measurement, not a preference: rendered open, the real
    // glossary was 8,194 px on a phone — three times the tallest page in the app.
    renderPage();
    expect(await screen.findByText("Drizzle")).toBeTruthy();
    expect(screen.getByText(/Plain-language explanations/)).toBeTruthy();
    expect(screen.getByText("Sigma clipping")).toBeTruthy();
    expect(isOpen("drizzle")).toBe(false);
    expect(isOpen("fwhm")).toBe(false);
  });

  it("costs no height while it is closed, which is the whole point", async () => {
    // The page is short because a closed panel is collapsed to nothing, not
    // because it was left out — the owner's rule is that nothing may be removed.
    renderPage();
    await screen.findByText("Drizzle");
    const panel = screen.getByText(/Higher resolution/).closest("[role=region]")!;
    expect(panel).toHaveAttribute("aria-hidden", "true");
    expect((panel as HTMLElement).style.height).toBe("0px");
  });

  it("opens one term without opening the others", async () => {
    renderPage();
    fireEvent.click(await screen.findByTestId("glossary-control-drizzle"));
    await waitFor(() => expect(isOpen("drizzle")).toBe(true));
    // The body is rendered markdown and all.
    expect(screen.getByText("dithered").tagName).toBe("B");
    expect(isOpen("fwhm")).toBe(false);
  });

  it("reads end to end in one click, so nothing is hidden behind 38 taps", async () => {
    renderPage();
    fireEvent.click(await screen.findByTestId("glossary-open-all"));
    await waitFor(() => expect(isOpen("drizzle")).toBe(true));
    expect(isOpen("fwhm")).toBe(true);
    expect(isOpen("sigma-clipping")).toBe(true);
    // …and closes again from the same control.
    fireEvent.click(screen.getByTestId("glossary-open-all"));
    await waitFor(() => expect(isOpen("drizzle")).toBe(false));
  });

  it("opens and scrolls to a deep link once the terms arrive", async () => {
    // The browser cannot honour `#fwhm` on first paint — the entry does not
    // exist yet, and once it does it is closed — which is why the page does both
    // halves itself.
    window.location.hash = "#fwhm";
    const scroll = vi.fn();
    Element.prototype.scrollIntoView = scroll;
    renderPage();
    await waitFor(() => expect(isOpen("fwhm")).toBe(true));
    expect(scroll).toHaveBeenCalled();
    expect(isOpen("drizzle")).toBe(false);
  });

  it("ignores a hash that names no term, rather than scrolling nowhere", async () => {
    window.location.hash = "#not-a-term";
    const scroll = vi.fn();
    Element.prototype.scrollIntoView = scroll;
    renderPage();
    await screen.findByText("Drizzle");
    expect(scroll).not.toHaveBeenCalled();
  });

  it("searches the explanations, not just the names", async () => {
    renderPage();
    await screen.findByText("Drizzle");
    search("satellite");
    expect(screen.getByText("Sigma clipping")).toBeTruthy();
    expect(screen.queryByText("Drizzle")).toBeNull();
  });

  it("opens the answer when a search lands on exactly one term", async () => {
    renderPage();
    await screen.findByText("Drizzle");
    search("satellite");
    // One match is a question with one answer; making them tap it is a wasted step.
    await waitFor(() => expect(isOpen("sigma-clipping")).toBe(true));
  });

  it("finds an acronym by the words it stands for — they are in the heading", async () => {
    renderPage();
    await screen.findByText("Drizzle");
    search("half maximum");
    expect(screen.getByText("FWHM (full width at half maximum)")).toBeTruthy();
  });

  it("says how many terms matched, so a narrow search is legible", async () => {
    renderPage();
    await screen.findByText("Drizzle");
    expect(screen.getByText(/3 terms/)).toBeTruthy();
    search("satellite");
    expect(screen.getByText("1 of 3 terms")).toBeTruthy();
  });

  it("says so, helpfully, when a search matches nothing", async () => {
    renderPage();
    await screen.findByText("Drizzle");
    search("narrowband");
    expect(screen.getByText(/Nothing here matches/)).toBeTruthy();
    expect(screen.queryByText("Drizzle")).toBeNull();
  });

  it("explains an empty glossary instead of showing a blank page", async () => {
    // A build whose package data went missing: the page must say what happened
    // and that nothing else is affected, not render an empty column.
    renderPage({ intro: "", terms: [] });
    expect(await screen.findByText(/didn’t load/)).toBeTruthy();
  });

  it("offers a retry when the request fails", async () => {
    renderPage(new Error("offline"));
    expect(await screen.findByRole("button", { name: /retry/i })).toBeTruthy();
  });
});
