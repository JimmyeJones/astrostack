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
// a 5039ms timeout); 10000ms then still flaked when the heavy Editor.test.tsx
// worker was CPU-starved by the ~46-file parallel run (observed a 10534ms
// waitFor). The settle it waits on (a 250ms debounce + a mocked re-fetch) is
// sub-second when scheduled — the long tails are pure scheduling starvation, so
// generous headroom, not a real slowdown, is the fix. The retry only stops early
// on success, so a larger ceiling never slows a passing test.
// NOTE: this must stay below vitest's per-test `testTimeout` (see vite.config.ts)
// — an async retry inside a shorter test timeout is killed before it can succeed
// ("Test timed out in Nms"), the flake that reddened main's frontend CI.
configure({ asyncUtilTimeout: 20000 });

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
