import { Badge, Button, Group, Paper, Stack, Text } from "@mantine/core";
import { IconWand } from "@tabler/icons-react";
import type { VideoSharpnessProfile } from "../api/client";

// Plot the sharpness curve on a FIXED 0..1 vertical scale — the scores arrive
// already normalised so the best frame is 1.0. This is the one thing the shared
// `Sparkline` must not do here: it rescales to a series' own min..max, which
// would draw a steady capture (every frame within 1% of the best) as a dramatic
// cliff and tell the beginner exactly the opposite of the truth. On a fixed
// axis, flat looks flat and a cliff looks like a cliff.
export function sharpnessCurvePoints(
  curve: number[], width: number, height: number, pad = 2,
): { x: number; y: number }[] {
  if (curve.length === 0) return [];
  const innerH = height - 2 * pad;
  const stepX = curve.length > 1 ? width / (curve.length - 1) : 0;
  return curve.map((v, i) => {
    const frac = Math.min(1, Math.max(0, v));
    return { x: curve.length > 1 ? i * stepX : width / 2, y: pad + (1 - frac) * innerH };
  });
}

const SPREAD_LABEL: Record<VideoSharpnessProfile["spread"], string> = {
  steady: "Steady air",
  mixed: "Mixed seeing",
  variable: "Jumpy seeing",
};

const SPREAD_COLOR: Record<VideoSharpnessProfile["spread"], string> = {
  steady: "teal",
  mixed: "yellow",
  variable: "orange",
};

/** One option's trade-off in the fewest words that stay honest. */
export function optionLine(o: VideoSharpnessProfile["options"][number]): string {
  return (
    `${o.percent.toFixed(0)}% · ${o.n_frames} frames · `
    + `${o.sharpness_vs_typical.toFixed(1)}× sharper · ${o.noise_gain.toFixed(0)}× cleaner`
  );
}

/**
 * "How steady was your capture?" — the sharpness distribution behind the one
 * decision a lucky-imaging stack asks the user to make.
 *
 * Self-hiding: a still stacked before the scores were kept has no profile, and
 * nothing renders. `onUseSuggestion` is optional — without it the card is purely
 * informative.
 */
export function VideoSharpnessCard({
  profile, onUseSuggestion,
}: {
  profile: VideoSharpnessProfile | null | undefined;
  onUseSuggestion?: (percent: number) => void;
}) {
  if (!profile || profile.curve.length === 0) return null;
  const w = 260;
  const h = 54;
  const pts = sharpnessCurvePoints(profile.curve, w, h);
  const path = pts.map((p) => `${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(" ");
  const cutX = Math.min(1, Math.max(0, profile.cut_fraction)) * w;
  const current = profile.options.find((o) => o.percent === profile.suggested_percent);
  const showSuggestion = onUseSuggestion !== undefined
    && !profile.summary.includes("a good choice here");

  return (
    <Paper withBorder radius="md" p="sm">
      <Group justify="space-between" mb={6} wrap="nowrap">
        <Text size="sm" fw={600}>How steady was your capture?</Text>
        <Badge size="sm" variant="light" color={SPREAD_COLOR[profile.spread]}>
          {SPREAD_LABEL[profile.spread]}
        </Badge>
      </Group>

      <svg
        width="100%"
        height={h}
        viewBox={`0 0 ${w} ${h}`}
        preserveAspectRatio="none"
        role="img"
        aria-label="Frame sharpness, sharpest first"
      >
        <polyline
          points={path}
          fill="none"
          stroke="var(--mantine-color-violet-4)"
          strokeWidth={1.5}
          strokeLinejoin="round"
        />
        {profile.cut_fraction > 0 ? (
          <line
            x1={cutX} y1={0} x2={cutX} y2={h}
            stroke="var(--mantine-color-dimmed)"
            strokeWidth={1}
            strokeDasharray="3 3"
          />
        ) : null}
      </svg>
      <Text size="xs" c="dimmed">
        Every frame, sharpest first
        {profile.cut_fraction > 0 ? " — everything left of the dashed line was kept" : ""}.
      </Text>

      <Stack gap={2} mt="xs">
        <Text size="sm">{profile.summary}</Text>
        {profile.options.map((o) => (
          <Text
            key={o.percent}
            size="xs"
            c={o.percent === profile.suggested_percent ? undefined : "dimmed"}
            fw={o.percent === profile.suggested_percent ? 600 : undefined}
          >
            {optionLine(o)}
          </Text>
        ))}
      </Stack>

      {showSuggestion && current ? (
        <Button
          size="xs"
          variant="light"
          mt="xs"
          leftSection={<IconWand size={14} />}
          onClick={() => onUseSuggestion(profile.suggested_percent)}
        >
          Try {profile.suggested_percent.toFixed(0)}% instead
        </Button>
      ) : null}
    </Paper>
  );
}
