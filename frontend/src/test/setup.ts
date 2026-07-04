import "@testing-library/jest-dom/vitest";
import { configure } from "@testing-library/dom";
import { vi } from "vitest";

// Raise Testing Library's default async timeout (1000ms) so that assertions
// waiting on a genuinely async settle — a debounced recipe re-render, a
// re-fetched suggestion — don't intermittently time out on the slower CI
// runner while passing locally. It does not change any assertion, only how
// long `waitFor`/`findBy*` will keep retrying before giving up. (Fixes the
// flaky "offers 'From your image' points" / "Auto levels" Editor tests, which
// wait for a button to flip to its already-applied disabled+✓ state.)
// 5000ms still flaked by a hair under a fully-saturated parallel run (observed
// a 5039ms timeout), so give it a wider margin — the retry only stops early on
// success, so a larger ceiling never slows a passing test.
configure({ asyncUtilTimeout: 10000 });

// Mantine relies on matchMedia / ResizeObserver, which jsdom doesn't implement.
Object.defineProperty(window, "matchMedia", {
  writable: true,
  value: (query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  }),
});

class ResizeObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
}
window.ResizeObserver = ResizeObserver as unknown as typeof window.ResizeObserver;
