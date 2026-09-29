import { MantineProvider } from "@mantine/core";
import { act, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { setStarfieldEnabled } from "../nightsky/prefs";
import { NightSky } from "./NightSky";

function renderAt(path: string) {
  return render(
    <MantineProvider defaultColorScheme="dark">
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="*" element={<NightSky />} />
        </Routes>
      </MemoryRouter>
    </MantineProvider>,
  );
}

/** jsdom has no real visibility; `visibilityState` is a getter on the prototype,
 * so it is stubbed rather than assigned. */
function setVisibility(state: "visible" | "hidden") {
  vi.spyOn(document, "visibilityState", "get").mockReturnValue(state);
  act(() => {
    fireEvent(document, new Event("visibilitychange"));
  });
}

function setReducedMotion(reduce: boolean) {
  window.matchMedia = ((query: string) => ({
    matches: reduce && query.includes("prefers-reduced-motion"),
    media: query,
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  })) as unknown as typeof window.matchMedia;
}

const realMatchMedia = window.matchMedia;

beforeEach(() => {
  localStorage.clear();
});

afterEach(() => {
  localStorage.clear();
  window.matchMedia = realMatchMedia;
  delete document.documentElement.dataset.astroSurround;
  delete document.documentElement.dataset.astroMotion;
  vi.restoreAllMocks();
});

describe("the night sky behind the pages", () => {
  it("draws its three parallax layers on an ordinary page, by default", () => {
    renderAt("/library");
    expect(screen.getByTestId("night-sky")).toBeInTheDocument();
    expect(document.querySelectorAll(".astro-nightsky__layer")).toHaveLength(3);
    expect(document.documentElement.dataset.astroSurround).toBe("sky");
    expect(document.documentElement.dataset.astroMotion).toBe("drifting");
  });

  it("is decorative — it never reaches the accessibility tree or the pointer", () => {
    renderAt("/library");
    const sky = screen.getByTestId("night-sky");
    expect(sky).toHaveAttribute("aria-hidden");
    // `pointer-events: none` lives in the stylesheet (jsdom does not apply it),
    // so what is pinned here is that nothing inside is focusable or clickable
    // content: the layers are empty decoration.
    expect(sky.textContent).toBe("");
    expect(sky.querySelectorAll("a, button, input")).toHaveLength(0);
  });

  it("stands down entirely on the editor — no stars beside a picture being judged", () => {
    renderAt("/targets/M_42/edit/4");
    expect(screen.queryByTestId("night-sky")).toBeNull();
    // ...and the page itself goes back to the plain neutral dark, so the
    // surround is not merely star-free but untinted.
    expect(document.documentElement.dataset.astroSurround).toBe("neutral");
  });

  it("stands down on Compare, and on the two routes that draw their own sky", () => {
    for (const path of ["/compare", "/sky", "/universe"]) {
      const view = renderAt(path);
      expect(screen.queryByTestId("night-sky"), path).toBeNull();
      expect(document.documentElement.dataset.astroSurround, path).toBe("neutral");
      view.unmount();
    }
  });

  it("holds the stars still while the tab is in the background", () => {
    renderAt("/library");
    expect(document.documentElement.dataset.astroMotion).toBe("drifting");
    setVisibility("hidden");
    expect(document.documentElement.dataset.astroMotion).toBe("still");
    setVisibility("visible");
    expect(document.documentElement.dataset.astroMotion).toBe("drifting");
  });

  it("holds the stars still when the system asks for reduced motion", () => {
    setReducedMotion(true);
    renderAt("/library");
    // The layers are still drawn — it is a starfield, not an animation — they
    // simply do not move.
    expect(screen.getByTestId("night-sky")).toBeInTheDocument();
    expect(document.documentElement.dataset.astroMotion).toBe("still");
  });

  it("clears the stars when this device turns them off, without a reload", () => {
    renderAt("/library");
    expect(screen.getByTestId("night-sky")).toBeInTheDocument();
    act(() => setStarfieldEnabled(false));
    expect(screen.queryByTestId("night-sky")).toBeNull();
    // The dark sky stays — the switch takes away the stars, not the colours.
    expect(document.documentElement.dataset.astroSurround).toBe("sky");
    act(() => setStarfieldEnabled(true));
    expect(screen.getByTestId("night-sky")).toBeInTheDocument();
  });

  it("leaves the page exactly as it found it when the shell unmounts", () => {
    const view = renderAt("/library");
    expect(document.documentElement.dataset.astroSurround).toBe("sky");
    view.unmount();
    expect(document.documentElement.dataset.astroSurround).toBeUndefined();
    expect(document.documentElement.dataset.astroMotion).toBeUndefined();
  });

  it("survives a device whose matchMedia throws", () => {
    window.matchMedia = (() => {
      throw new Error("blocked");
    }) as unknown as typeof window.matchMedia;
    // Rendered without `MantineProvider`, which calls `matchMedia` itself: what
    // is pinned here is that *this* component copes, not that Mantine does.
    const renderBare = () => render(
      <MemoryRouter initialEntries={["/library"]}>
        <Routes><Route path="*" element={<NightSky />} /></Routes>
      </MemoryRouter>,
    );
    expect(renderBare).not.toThrow();
    expect(screen.getByTestId("night-sky")).toBeInTheDocument();
    expect(document.documentElement.dataset.astroMotion).toBe("drifting");
  });
});
