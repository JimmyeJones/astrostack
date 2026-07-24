import { useMemo } from "react";
import { Alert, Text } from "@mantine/core";
import { IconSparkles } from "@tabler/icons-react";
import type { StackRun } from "../../api/client";
import { sharpestYet } from "./sharpestYet";

/**
 * "✨ Your sharpest yet" — a small celebratory callout shown on the target's
 * latest result when that stack came out sharper than any of the target's
 * previous stacks. Motivation, not a gate: it rewards the consistency (adding
 * subs, catching steadier nights) that leads to better pictures, and quietly
 * teaches a beginner what "better" looks like on their own data.
 *
 * Self-hiding: renders nothing on a target's first run, when the newest run
 * didn't beat its prior best, or when FWHM couldn't be measured — so it's safe
 * to drop in unconditionally next to the finished picture. `runs` must be
 * newest-first (as `listStackRuns` returns).
 */
export function SharpestYetBadge(
  { name, runs }: { name: string; runs: StackRun[] | undefined },
) {
  const beat = useMemo(() => sharpestYet(runs), [runs]);
  if (!beat) return null;

  const date = new Date(beat.priorBestDate).toLocaleDateString();
  return (
    <Alert
      color="grape"
      variant="light"
      icon={<IconSparkles size={18} />}
      title={`✨ Your sharpest ${name} yet`}
    >
      <Text size="sm">
        This stack resolved tighter stars than any of your previous {name} stacks
        {" — "}
        {beat.currentFwhmPx.toFixed(1)} px, beating your{" "}
        {beat.priorBestFwhmPx.toFixed(1)} px from {date}. Smaller is sharper;
        adding subs on steady, well-focused nights keeps pushing it down.
      </Text>
    </Alert>
  );
}
