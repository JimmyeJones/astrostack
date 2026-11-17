import { ContinueTonightCard } from "../ContinueTonightCard";
import { ImagingCalendarCard } from "../ImagingCalendarCard";
import { InsightTabs } from "../InsightTabs";
import { LastNightCard } from "../LastNightCard";
import { LibraryProgressCard } from "../LibraryProgressCard";
import { OffNightCard } from "../OffNightCard";
import { SuggestTargetsCard } from "../SuggestTargetsCard";
import { VideoCapturesCard } from "../VideoCapturesCard";
import { FirstLookStrip } from "./FirstLookStrip";
import { PointHereTonightCard } from "./PointHereTonightCard";

/**
 * Everything on the Dashboard that *describes* the library rather than showing
 * it — tonight's suggestions, the recap of the last night, long-run progress —
 * as one tabbed group (IA slice (e), reusing the Target page's `InsightTabs`).
 * Only one group is on screen at a time, and a group whose cards have nothing to
 * say gets no tab at all.
 *
 * Split out of `routes/Dashboard.tsx` for the owner's "recursive organization"
 * ask (2026-11-17): it is the last of the page's five top-level groups. A later
 * Dashboard analysis card joins a tab here; it never goes onto the page alone.
 */
export function DashboardInsights() {
  return (
    <div data-dashboard-group="insights" style={{ display: "contents" }}>
      <InsightTabs
        data-testid="dashboard-insights"
        groups={[
          { key: "tonight", label: "Tonight", node: (
            <>
              {/* "Point here right now": of the targets already started, which is
                  best-placed at this moment *and* would gain most from another
                  hour. Self-hides when there's nothing to recommend. */}
              <PointHereTonightCard />
              <ContinueTonightCard />
              <SuggestTargetsCard />
            </>
          ) },
          { key: "recent", label: "Recent", node: (
            <>
              {/* Before the recap of what came in: what it *looks* like. The
                  sharpest sub of the target that has subs but no picture yet —
                  the "did tonight work?" glance, which until now only the
                  Target hub answered. Self-hides once every target has a
                  picture, so a settled library sees nothing. */}
              <FirstLookStrip />
              {/* "Was last night off for you?" — the morning-after heads-up when
                  the newest night's stars came out fatter than this owner's own
                  usual (dew, focus, or just seeing). Sits beside the recap of
                  what came in, because that is the same glance; self-hides on a
                  normal night and on a library with no "usual" yet. */}
              <OffNightCard />
              <LastNightCard />
              <VideoCapturesCard />
            </>
          ) },
          { key: "progress", label: "Progress", node: (
            <>
              <LibraryProgressCard />
              <ImagingCalendarCard />
            </>
          ) },
        ]}
      />
    </div>
  );
}
