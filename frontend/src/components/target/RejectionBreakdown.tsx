import { Anchor, Button, Group, Stack, Text } from "@mantine/core";
import { Link } from "react-router-dom";

import type { RejectionSummary } from "../../api/client";
import { bucketAction, verdictAction, type RejectionAction } from "./rejectionActions";

/** "Why were some frames left out?" — a plain-language, grouped breakdown of the
 * frames the stack dropped, with a single reassuring headline verdict.
 *
 * A beginner sees "412 of 500 used" and wonders whether their night went wrong;
 * usually it's healthy (a few satellite trails, some cloud, soft focus). This
 * translates the internal `reject_reason` tally (grouped server-side into a few
 * buckets, each with a friendly note) into words a non-expert reads. The server
 * pre-orders and filters the buckets (non-zero only); this is pure presentation.
 *
 * Where a note names something to do, it is offered as one small control rather
 * than left as a hunt (`rejectionActions`). `onRunPlateSolve` is the page's own
 * Plate Solve action — the one destination that isn't a route, because the
 * control is on the page this renders on; without it that advice stays plain
 * text, so a surface that has no such button degrades to today's behaviour
 * instead of offering a dead one.
 */
const TONE_COLOR: Record<RejectionSummary["verdict"]["tone"], string> = {
  good: "teal",
  ok: "gray",
  warn: "orange",
};

function ActionLink(
  { action, onRunPlateSolve }: {
    action: RejectionAction | null; onRunPlateSolve?: () => void;
  },
) {
  if (!action) return null;
  if (action.kind === "route") {
    return (
      <Anchor component={Link} to={action.to} size="xs" mt={2} display="inline-block">
        {action.label} →
      </Anchor>
    );
  }
  if (!onRunPlateSolve) return null;
  return (
    <Button size="compact-xs" variant="light" mt={4} onClick={onRunPlateSolve}>
      {action.label}
    </Button>
  );
}

/** Identity of an action, so the same one is never offered twice in one card:
 *  the headline verdict is usually *about* one of the buckets below it, and two
 *  identical buttons a few lines apart read as two different things. */
function actionId(action: RejectionAction | null): string | null {
  if (!action) return null;
  return action.kind === "route" ? `route:${action.to}` : action.kind;
}

export function RejectionBreakdown(
  { summary, onRunPlateSolve }: {
    summary: RejectionSummary; onRunPlateSolve?: () => void;
  },
) {
  const { verdict, buckets, used, dropped } = summary;
  const headline = verdictAction(verdict.key);
  // Offered at the top, where the advice that earned it is — so a bucket
  // repeating that advice further down doesn't repeat the control too.
  const shown = new Set([actionId(headline)].filter(Boolean) as string[]);
  return (
    <Stack gap={6}>
      <Text size="sm" fw={600}>Why some frames were left out</Text>
      <Text size="xs" c={TONE_COLOR[verdict.tone]} fw={500}>
        {verdict.text}
      </Text>
      <ActionLink action={headline} onRunPlateSolve={onRunPlateSolve} />
      <Text size="xs" c="dimmed">
        {used} of {used + dropped} frames went into your picture.
      </Text>
      <Stack gap={6} mt={2}>
        {buckets.map((b) => {
          const act = bucketAction(b.key);
          const id = actionId(act);
          const dup = id != null && shown.has(id);
          if (id != null) shown.add(id);
          return (
          <div key={b.key}>
            <Group justify="space-between" gap="xs" wrap="nowrap">
              <Text size="xs" fw={600}>{b.label}</Text>
              <Text size="xs" fw={600}>{b.count}</Text>
            </Group>
            <Text size="xs" c="dimmed">{b.note}</Text>
            <ActionLink action={dup ? null : act} onRunPlateSolve={onRunPlateSolve} />
          </div>
          );
        })}
      </Stack>
    </Stack>
  );
}
