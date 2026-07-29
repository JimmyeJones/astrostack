import { Alert, Group, Text } from "@mantine/core";

import type { SkyBrightnessRead } from "../../api/client";

const TONE: Record<SkyBrightnessRead["level"], { color: string; icon: string }> = {
  darker: { color: "teal", icon: "🌌" },
  typical: { color: "gray", icon: "🌙" },
  brighter: { color: "yellow", icon: "🌗" },
  much_brighter: { color: "orange", icon: "🌕" },
};

/**
 * "Was last night's sky bright?" — one calm line on the Target page.
 *
 * A Seestar owner has no sky-quality meter, so when a night's picture comes out
 * washed out with a strong gradient they have no way to tell whether the sky was
 * to blame or they did something wrong. The backend answers that from the sky
 * level QC already measures on every sub, comparing the latest night against
 * this target's own other nights — never an absolute Bortle-style claim, which
 * would need calibration we don't have.
 *
 * Renders nothing when there's no trustworthy read (`read` null: too few nights,
 * too few measured subs, no exposure recorded), so it's safe to drop in
 * unconditionally. A "typical" night is deliberately still shown — "nothing
 * unusual here" is the reassurance a beginner is looking for.
 */
export function SkyBrightnessNote({ read }: { read?: SkyBrightnessRead | null }) {
  if (!read) return null;
  const tone = TONE[read.level] ?? TONE.typical;
  return (
    <Alert
      color={tone.color}
      variant="light"
      title={
        <Group gap={6} wrap="nowrap">
          <span aria-hidden>{tone.icon}</span>
          <span>{`Your sky on the night of ${read.night}: ${read.label.toLowerCase()}`}</span>
        </Group>
      }
    >
      <Text size="sm">{read.text}</Text>
      <Text size="xs" c="dimmed" mt={4}>
        Measured from your own subs and compared with your other {read.nights} nights
        on this target — not an absolute sky rating.
      </Text>
    </Alert>
  );
}
