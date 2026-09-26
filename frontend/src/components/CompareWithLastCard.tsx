import { Button, Group, Paper, Stack, Text, ThemeIcon } from "@mantine/core";
import { IconGitCompare, IconTrendingUp } from "@tabler/icons-react";
import { Link } from "react-router-dom";
import type { StackRun } from "../api/client";
import {
  pickCompareWithLast, pickFirstVsNow, sameTargetCompareHref,
} from "../compareWithLast";
import { pictureDateLabel } from "../format";
import { NoiseDeltaStrip } from "./NoiseDeltaStrip";

/**
 * "Is my new picture actually better than last week's?" — the one affordance
 * that was missing from the run-vs-run comparison the app already had.
 *
 * `/compare` is a full, bookmarkable A/B route with a drag-the-divider split
 * slider, per-side provenance and plain-language verdicts on noise, mosaic panel
 * flatness and how many nights each side is made of. The Gallery links into it
 * from any two selected pictures, and History offers "this run vs the one before
 * it" per row. **But a beginner who never opens History never discovers any of
 * it** — and "did another two nights actually help?" is the single most
 * motivating question in the hobby, asked from the Target page, not from a
 * version list.
 *
 * So: one link, not a second comparison view. It lives in the Target page's
 * existing **Story** group (beside the deepening reel, which answers the same
 * question as an animation and self-hides on the same condition), so the page
 * gains no always-on control — the owner's standing "the pages are extremely
 * busy" priority.
 *
 * **A second link, for the other question** (`pickFirstVsNow`): *"How far you've
 * come"* pairs the **first-ever** picture of this object with the latest. "Did
 * another two nights help?" is an increment and answers itself in small steps;
 * *"look how much better you've got at this"* is the one a beginner is actually
 * moved by, and it is invisible from a version list — the first picture is at the
 * bottom of History. It is a **link in this card**, not a card of its own, and it
 * appears only when it is a genuinely different pair: with exactly two pictures
 * the first one *is* the previous one, and two buttons pointing at one URL is
 * clutter rather than a feature. Both links put "now" on the same side of the
 * divider (`a` is always the newest run), so the two comparisons read the same
 * way round.
 *
 * **And it can now show the difference rather than only asserting it**
 * (`NoiseDeltaStrip`, owner-requested 2026-09-25): one patch of sky from each of
 * the two stacks, at full resolution and under one shared stretch. A card-sized
 * A/B of the whole canvas cannot carry that — both previews are shrunk 5–10× and
 * decimation averages the grain away — so the strip is a *crop*, behind a button,
 * and self-hides when there is no honest patch to show.
 *
 * Renders **nothing** on a target with fewer than two comparable pictures, which
 * is every freshly-stacked target; see `pickCompareWithLast` for what counts.
 */
export function CompareWithLastCard(
  { safe, runs }: { safe: string; runs?: StackRun[] | null },
) {
  const pair = pickCompareWithLast(runs);
  if (!pair) return null;
  // "How far you've come" — the same machinery asked the *other* question. It is
  // offered only when it is genuinely a different pair: on a target with exactly
  // two pictures the first one **is** the previous one, and two buttons pointing
  // at one URL is clutter, not a second feature (the owner's standing "the pages
  // are extremely busy" priority).
  const firstPair = pickFirstVsNow(runs);
  const firstVsNow = firstPair && firstPair.first.id !== pair.previous.id
    ? firstPair : null;

  // Date each side the way every other surface does — by when the subs were
  // *shot*, falling back to a labelled processing stamp. On a re-stack of a back
  // catalogue those are years apart, and the whole point of the line is to say
  // which two nights' work you are about to put side by side.
  const dateOf = (r: StackRun) => pictureDateLabel(
    r.capture_night_start, r.capture_night_end, r.timestamp_utc, r.capture_nights);
  const newest = dateOf(pair.newest);
  const previous = dateOf(pair.previous);

  return (
    <Paper withBorder p="sm" radius="md" mt="xs" data-testid="compare-with-last">
      <Group gap="sm" wrap="nowrap" align="flex-start">
        <ThemeIcon size={22} radius="xl" variant="light" color="grape"
          style={{ flexShrink: 0, marginTop: 2 }}>
          <IconGitCompare size={14} />
        </ThemeIcon>
        <Stack gap={4} style={{ flex: 1, minWidth: 0 }}>
          <Text size="sm" fw={500}>Did it get better?</Text>
          <Text size="xs" c="dimmed">
            Put your newest picture beside the one before it and drag a divider
            across — the page also says which is cleaner, and how many nights went
            into each.
            {newest && previous ? ` Comparing ${newest} with ${previous}.` : ""}
          </Text>
          {firstVsNow ? (
            <Text size="xs" c="dimmed" data-testid="first-vs-now-hint">
              Or go all the way back: your first picture of this
              {dateOf(firstVsNow.first) ? ` (${dateOf(firstVsNow.first)})` : ""}
              {" "}beside where it is now.
            </Text>
          ) : null}
          {/* See the difference, don't just read about it. Behind a button: the
              two crops cost a pass over both masters to place, and the Target
              page must not spend that on every view (as the deepening reel's
              "Play"). */}
          <NoiseDeltaStrip safe={safe} newestId={pair.newest.id}
            previousId={pair.previous.id}
            newestLabel={newest} previousLabel={previous} />
          <Group gap="xs">
            <Button
              size="xs" variant="light" color="grape"
              leftSection={<IconGitCompare size={14} />}
              component={Link}
              to={sameTargetCompareHref(safe, pair.newest.id, pair.previous.id)}
            >
              Compare with my last one
            </Button>
            {firstVsNow ? (
              <Button
                size="xs" variant="subtle" color="grape"
                leftSection={<IconTrendingUp size={14} />}
                component={Link}
                data-testid="first-vs-now"
                to={sameTargetCompareHref(
                  safe, firstVsNow.newest.id, firstVsNow.first.id)}
              >
                How far you&apos;ve come
              </Button>
            ) : null}
          </Group>
        </Stack>
      </Group>
    </Paper>
  );
}
