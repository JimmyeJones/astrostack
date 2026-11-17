import { SampleImageCard } from "../SampleImageCard";
import { FirstImageCard } from "./FirstImageCard";

/**
 * "Getting started" — the Dashboard's first-run group: the four-step map from a
 * folder of subs to a finished picture, and the one-tap sample image to try the
 * whole journey on before the first clear night.
 *
 * Split out of `routes/Dashboard.tsx` for the owner's "recursive organization"
 * ask (2026-11-17): the two used to be separate top-level blocks; they answer
 * the same question ("how do I begin?") so they are one group now. Both cards
 * self-hide on an established install (the sample card keeps a small "remove
 * the sample" offer while the sample is loaded), so this group usually renders
 * nothing. `display: contents` keeps an empty group from adding a gap to the
 * page's own spacing, and leaves both cards exactly where they were.
 */
export function GettingStarted() {
  return (
    <div data-dashboard-group="getting-started" style={{ display: "contents" }}>
      {/* The positive first-run map: four plain steps from a folder of subs to a
          finished picture, each ticking itself off. Self-hides on an established
          install (every step already done on first render) and once dismissed.
          Kept above the fold on purpose: it is what orients a brand-new library. */}
      <FirstImageCard />
      <SampleImageCard />
    </div>
  );
}
