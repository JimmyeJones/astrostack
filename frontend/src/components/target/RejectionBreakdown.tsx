import { useState } from "react";
import { Anchor, Button, Group, Image, Stack, Text } from "@mantine/core";
import { Link } from "react-router-dom";

import { api, type RejectionSummary } from "../../api/client";
import { bucketAction, verdictAction, type RejectionAction } from "./rejectionActions";
import {
  exampleLead, hasRenderableExamples, type RejectExamples,
} from "./rejectExamples";

/** "Why were some frames left out?" — a plain-language, grouped breakdown of the
 * frames the stack dropped, with a single reassuring headline verdict.
 *
 * A beginner sees "412 of 500 used" and wonders whether their night went wrong;
 * usually it's healthy (a few satellite trails, some cloud, soft focus). This
 * translates the internal `reject_reason` tally (grouped server-side into a few
 * buckets, each with a friendly note) into words a non-expert reads. The server
 * pre-orders and filters the buckets (non-zero only); this is pure presentation.
 *
 * Where the cause is something you can *see*, it can also be looked at: with a
 * `safe` key and the server's `examples`, each such bucket offers up to three
 * thumbnails of its own rejected subs behind one shared "show me" toggle — so a
 * beginner learns to recognise a satellite streak or a soft frame instead of
 * taking the count on trust. Collapsed by default, which is what keeps it to one
 * line of page height and stops the card fetching thumbnails nobody asked for
 * (the same bargain the reel cards make). Without either prop it renders exactly
 * as it always has, which is how the hover-card copy of this breakdown stays a
 * quick read rather than an image gallery.
 *
 * Where a note names something to do, it is offered as one small control rather
 * than left as a hunt (`rejectionActions`). `onRunPlateSolve` is the page's own
 * Plate Solve action — the one destination that isn't a route, because the
 * control is on the page this renders on; without it that advice stays plain
 * text, so a surface that has no such button degrades to today's behaviour
 * instead of offering a dead one. `onTryHarder` (the deep-image rescue) is the
 * same shape and degrades the same way, and is only ever *reached* when the
 * server says the rescue would engage (`deepRescueOffered`).
 */
const TONE_COLOR: Record<RejectionSummary["verdict"]["tone"], string> = {
  good: "teal",
  ok: "gray",
  warn: "orange",
};

function ActionLink(
  { action, onRunPlateSolve, onTryHarder }: {
    action: RejectionAction | null;
    onRunPlateSolve?: () => void;
    onTryHarder?: () => void;
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
  const onClick = action.kind === "deepRescue" ? onTryHarder : onRunPlateSolve;
  if (!onClick) return null;
  return (
    <Button size="compact-xs" variant="light" mt={4} onClick={onClick}>
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
  { summary, onRunPlateSolve, onTryHarder, deepRescueOffered = false,
    safe, examples }: {
    summary: RejectionSummary;
    onRunPlateSolve?: () => void;
    onTryHarder?: () => void;
    deepRescueOffered?: boolean;
    /** The target, for the thumbnail URLs. Without it, no examples render. */
    safe?: string;
    /** `reject-summary.examples` — a few frames per *visible* cause. */
    examples?: RejectExamples;
  },
) {
  const [showExamples, setShowExamples] = useState(false);
  const canShowExamples = !!safe && hasRenderableExamples(examples);
  const { verdict, buckets, used, dropped } = summary;
  const headline = verdictAction(verdict.key, deepRescueOffered);
  // Offered at the top, where the advice that earned it is — so a bucket
  // repeating that advice further down doesn't repeat the control too.
  const shown = new Set([actionId(headline)].filter(Boolean) as string[]);
  return (
    <Stack gap={6}>
      <Text size="sm" fw={600}>Why some frames were left out</Text>
      <Text size="xs" c={TONE_COLOR[verdict.tone]} fw={500}>
        {verdict.text}
      </Text>
      <ActionLink action={headline} onRunPlateSolve={onRunPlateSolve}
        onTryHarder={onTryHarder} />
      <Text size="xs" c="dimmed">
        {used} of {used + dropped} frames went into your picture.
      </Text>
      <Stack gap={6} mt={2}>
        {buckets.map((b) => {
          const act = bucketAction(b.key, deepRescueOffered);
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
            {showExamples && safe ? (
              <ExampleStrip safe={safe} bucketKey={b.key} examples={examples} />
            ) : null}
            <ActionLink action={dup ? null : act} onRunPlateSolve={onRunPlateSolve}
              onTryHarder={onTryHarder} />
          </div>
          );
        })}
      </Stack>
      {canShowExamples ? (
        <Button size="compact-xs" variant="subtle" mt={2}
          style={{ alignSelf: "flex-start" }}
          onClick={() => setShowExamples((v) => !v)}>
          {showExamples ? "Hide the examples" : "Show me what they looked like"}
        </Button>
      ) : null}
    </Stack>
  );
}

/** Up to three of one bucket's own rejected subs, with a line saying what to
 *  look for. Renders nothing for a bucket the server sent no examples for (most
 *  of them) or that has no copy — see `rejectExamples`. */
function ExampleStrip(
  { safe, bucketKey, examples }: {
    safe: string; bucketKey: string; examples?: RejectExamples;
  },
) {
  const list = examples?.[bucketKey] ?? [];
  const lead = exampleLead(bucketKey, list.length);
  if (!lead) return null;
  return (
    <Stack gap={4} mt={4}>
      <Text size="xs" c="dimmed">{lead}</Text>
      <Group gap="xs">
        {list.map((ex) => (
          <Image key={ex.frame_id} w={88} h={88} radius="sm" fit="cover"
            loading="lazy" fallbackSrc=""
            src={api.framePreviewUrl(safe, ex.frame_id, 160)}
            alt={`A sub we set aside: ${ex.name}`} />
        ))}
      </Group>
    </Stack>
  );
}
