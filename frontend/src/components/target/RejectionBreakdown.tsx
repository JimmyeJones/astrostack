import { Group, Stack, Text } from "@mantine/core";

import type { RejectionSummary } from "../../api/client";

/** "Why were some frames left out?" — a plain-language, grouped breakdown of the
 * frames the stack dropped, with a single reassuring headline verdict.
 *
 * A beginner sees "412 of 500 used" and wonders whether their night went wrong;
 * usually it's healthy (a few satellite trails, some cloud, soft focus). This
 * translates the internal `reject_reason` tally (grouped server-side into a few
 * buckets, each with a friendly note) into words a non-expert reads. The server
 * pre-orders and filters the buckets (non-zero only); this is pure presentation.
 */
const TONE_COLOR: Record<RejectionSummary["verdict"]["tone"], string> = {
  good: "teal",
  ok: "gray",
  warn: "orange",
};

export function RejectionBreakdown({ summary }: { summary: RejectionSummary }) {
  const { verdict, buckets, used, dropped } = summary;
  return (
    <Stack gap={6}>
      <Text size="sm" fw={600}>Why some frames were left out</Text>
      <Text size="xs" c={TONE_COLOR[verdict.tone]} fw={500}>
        {verdict.text}
      </Text>
      <Text size="xs" c="dimmed">
        {used} of {used + dropped} frames went into your picture.
      </Text>
      <Stack gap={6} mt={2}>
        {buckets.map((b) => (
          <div key={b.key}>
            <Group justify="space-between" gap="xs" wrap="nowrap">
              <Text size="xs" fw={600}>{b.label}</Text>
              <Text size="xs" fw={600}>{b.count}</Text>
            </Group>
            <Text size="xs" c="dimmed">{b.note}</Text>
          </div>
        ))}
      </Stack>
    </Stack>
  );
}
