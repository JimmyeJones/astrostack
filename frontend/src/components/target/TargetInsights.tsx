import { Text } from "@mantine/core";
import { type ComponentProps } from "react";
import type { StackRun } from "../../api/client";
import { InsightTabs } from "../InsightTabs";
import { ObjectInfoCard } from "../ObjectInfoCard";
import { SessionRecapCard } from "../SessionRecapCard";
import { NightsCard } from "../NightsCard";
import { FocusTrendCard } from "../FocusTrendCard";
import { TransparencyTrendCard } from "../TransparencyTrendCard";
import { StackHealthCard } from "../StackHealthCard";
import { NextSessionCard } from "../NextSessionCard";
import { BestMonthsStrip } from "../BestMonthsStrip";
import { MoonInterferenceCard } from "../MoonInterferenceCard";
import { CompareWithLastCard } from "../CompareWithLastCard";
import { DeepeningReelCard } from "../DeepeningReelCard";
import { MosaicMapCard } from "./MosaicMapCard";
import { RejectionBreakdownCard } from "./RejectionBreakdownCard";

/**
 * Everything on the Target page that *describes* the target, in one tabbed
 * group: what the object is, how its nights went, its quality trends, when to
 * shoot it next and how it has grown.
 *
 * Split out of `routes/Target.tsx` for the owner's "recursive organization" ask
 * (2026-11-17): the page shows at most five things at the top level and this is
 * one of them. The catalog card ("what am I looking at") used to sit on its own
 * between the frames table and these tabs; it now leads the Overview group, the
 * tab that opens first, so it is on screen exactly where it was — one group fewer
 * at the top of the page, nothing removed. A later analysis card joins a group
 * here; it never goes back onto the page on its own.
 */
export function TargetInsights({
  safe,
  name,
  showObjectInfo,
  hideFraming,
  rejection,
  onRunPlateSolve,
  onTryHarder,
  nextSession,
  runs,
  planning = "eager",
}: {
  safe: string;
  name?: string;
  /** The target matched the offline catalog, so the object card has something to say. */
  showObjectInfo: boolean;
  /** The run's own measured framing verdict is on the page, so the card's
   *  catalog-size guess stays quiet (see `ObjectInfoCard`). */
  hideFraming: boolean;
  rejection: Pick<ComponentProps<typeof RejectionBreakdownCard>,
    "summary" | "deepRescueOffered" | "examples">;
  /** How the Planning cards load — they fetch the slowest data on the page
   *  (7.2 s + 3.7 s, audit 2026-11-26). ``lazy``: only once their tab is opened
   *  (there is a location to plan from). ``eager``: rendered hidden like the
   *  other groups, so they can self-hide (no location: they answer at once).
   *  ``hidden``: not yet known (settings loading) — nothing fetched. */
  planning?: "lazy" | "eager" | "hidden";
  onRunPlateSolve: () => void;
  onTryHarder: () => void;
  /** The readiness gap, when there is one — null hides "your next session". */
  nextSession: ComponentProps<typeof NextSessionCard> | null;
  runs?: StackRun[] | null;
}) {
  return (
    <InsightTabs
      data-testid="target-insights"
      groups={[
        { key: "overview", label: "Overview", node: (
          <>
            {/* "What am I looking at?" — first, because it is what a beginner
                reads before any of the numbers. Self-hides without a catalog match. */}
            {showObjectInfo ? (
              <ObjectInfoCard safe={safe} hideFraming={hideFraming} allowRename />
            ) : null}
            <SessionRecapCard safe={safe} />
            <NightsCard safe={safe} />
          </>
        ) },
        { key: "quality", label: "Quality", node: (
          <>
            {/* The same "why were some frames left out?" breakdown the badge
                above shows on hover — here in a form a phone can reach, and
                with the one-tap fixes its advice names. Self-hides when
                nothing was left out. */}
            <RejectionBreakdownCard
              summary={rejection.summary}
              onRunPlateSolve={onRunPlateSolve}
              onTryHarder={onTryHarder}
              deepRescueOffered={rejection.deepRescueOffered}
              safe={safe}
              examples={rejection.examples} />
            <FocusTrendCard safe={safe} />
            <TransparencyTrendCard safe={safe} />
            <StackHealthCard safe={safe} />
          </>
        ) },
        { key: "planning", label: "Planning", lazy: planning === "lazy",
          lazyEmpty: (
            <Text size="sm" c="dimmed">
              Nothing to plan for this target yet — planning needs your location
              (Settings) and the target's position in the sky.
            </Text>
          ),
          node: planning === "hidden" ? null : (
          <>
            {/* Forward-looking companion to "Is it enough yet?" (which stays
                beside the picture — it answers the question the beginner came
                with): when there's still a goal gap, join it with the night
                planner's next dark window(s) for this object. Self-hides when
                the goal's met or no window can be computed. */}
            {nextSession ? <NextSessionCard {...nextSession} /> : null}
            {/* Which months of the year this object is actually up. Self-hides
                without a location/position. */}
            <BestMonthsStrip safe={safe} />
            {/* "Your mosaic, panel by panel" — where a mosaic is thin, so the
                next clear night goes where it actually helps. Self-hides on
                anything that isn't a mosaic. */}
            <MosaicMapCard safe={safe} />
            {/* "Is the Moon going to wash this out tonight?" Self-hides without
                a location/position. */}
            <MoonInterferenceCard safe={safe} />
          </>
        ) },
        { key: "story", label: "Story", node: (
          <>
            {/* "Did it get better?" — links into the run-vs-run compare page:
                the newest picture against the one before it and, from three
                pictures on, against the first ever. Self-hides with fewer than
                two comparable pictures. */}
            <CompareWithLastCard safe={safe} runs={runs} />
            {/* "Night after night" — the same target getting deeper across
                re-stacks; on a target stacked once across several nights it
                offers the night-by-night clip instead (`webapp/reeloffer.py`). */}
            <DeepeningReelCard safe={safe} name={name} />
          </>
        ) },
      ]}
    />
  );
}
