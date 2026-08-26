import { Badge, Group, Paper, Stack, Text } from "@mantine/core";
import { IconStars } from "@tabler/icons-react";
import { useQuery } from "@tanstack/react-query";
import { api, type DifficultyHint, type FramingHint, type MosaicPlan } from "../api/client";

/** A plain-language one-liner for the object card, e.g.
 *  "A galaxy in the constellation Andromeda." Constellation is dropped when the
 *  catalog abbreviation is unknown. Uses "an" before a vowel sound. */
export function describeObject(type: string, constellation: string): string {
  const t = (type || "deep-sky object").trim();
  const article = /^[aeiou]/i.test(t) ? "An" : "A";
  const where = constellation ? ` in the constellation ${constellation}` : "";
  return `${article} ${t}${where}.`;
}

/** Full "will it fit?" sentence for the card: the target's display name prefixed
 *  onto the backend's verb phrase — "M 31 is bigger than the Seestar's single
 *  frame …". Returns "" when there's no framing hint. */
export function framingSentence(
  displayName: string,
  framing: FramingHint | null | undefined,
): string {
  if (!framing) return "";
  return `${displayName} ${framing.text}`;
}

/** The "will it fit?" sentence with the panel count appended when we know it —
 *  "M 31 is bigger than the Seestar's single frame … About a 3×2 mosaic
 *  (6 panels) covers all of it." Telling a beginner to "shoot it in mosaic mode"
 *  stops exactly where their next question starts, and a non-expert has no idea
 *  whether that means a 2×2 or a 4×5. Falls back to the bare framing sentence
 *  when the catalog has no vetted size to plan from. */
export function framingWithMosaic(
  displayName: string,
  framing: FramingHint | null | undefined,
  mosaic: MosaicPlan | null | undefined,
): string {
  const base = framingSentence(displayName, framing);
  if (!base || !mosaic?.text) return base;
  return `${base} ${mosaic.text}`;
}

/** Mantine text colour for a framing verdict: a gentle nudge to mosaic mode for
 *  the too-big cases, plain dimmed for the reassuring "fits" case. */
export function framingColor(level: FramingHint["level"]): string {
  if (level === "mosaic") return "orange.6";
  if (level === "tight") return "yellow.7";
  return "dimmed";
}

/** Mantine colour for a difficulty badge: reassuring green for easy, a calm blue
 *  for moderate, and a gentle amber (never alarming red) for challenging — the
 *  point is honest expectation-setting, not warning the user off. */
export function difficultyColor(level: DifficultyHint["level"]): string {
  if (level === "challenging") return "orange";
  if (level === "moderate") return "blue";
  return "green";
}

/**
 * "What am I looking at?" — an offline catalog lookup that turns a bare folder
 * name (or the solved centre) into friendly context. Renders nothing until a
 * confident match resolves, so it's safe to drop onto any page that knows the
 * target's safe name (Target, History, editor). Shares its query key with the
 * Target page's own identify fetch, so react-query dedupes to one request.
 *
 * `hideFraming` drops just the catalog "will it fit?" line, for a page that is
 * already showing the *measured* verdict for a finished picture of this target
 * (`FramingVerdictNote`). The two say the same thing — "M 42 is bigger than the
 * Seestar's single frame, shoot it in mosaic mode" — except the measured one
 * also knows how much of it actually landed, so on a page carrying both, the
 * prediction is the copy to drop. Defaults to showing it, so the editor and any
 * other caller are unchanged.
 */
export function ObjectInfoCard(
  { safe, hideFraming = false }: { safe: string; hideFraming?: boolean },
) {
  const identity = useQuery({
    queryKey: ["identify", safe],
    queryFn: () => api.identifyTarget(safe),
    enabled: !!safe,
  });
  const d = identity.data;
  if (!d) return null;
  return (
    <Paper withBorder p="sm" radius="md" bg="var(--mantine-color-default-hover)">
      <Group gap="sm" wrap="nowrap" align="flex-start">
        <IconStars size={22} style={{ flexShrink: 0, marginTop: 2 }}
          color="var(--mantine-color-indigo-5)" />
        <Stack gap={2} style={{ minWidth: 0 }}>
          <Group gap="xs">
            <Text fw={600}>{d.name || d.id}</Text>
            <Badge variant="light" color="indigo" size="sm">{d.id}</Badge>
          </Group>
          <Text size="sm" c="dimmed">
            {describeObject(d.type, d.constellation)}
            {d.matched_by === "coords"
              ? " Identified from this target's plate-solved position."
              : ""}
          </Text>
          {d.blurb ? (
            <Text size="sm">{d.blurb}</Text>
          ) : null}
          {d.difficulty ? (
            // The badge never shrinks, so on a phone a `nowrap` row squeezed this
            // sentence into a ribbon: measured 194 px of a 336 px row (58 %) and
            // four lines for a sentence that needs two. Wrapping, with a
            // flex-basis wide enough to be worth keeping on one line, means the
            // sentence sits beside the badge on a wide screen exactly as before
            // and drops to its own full-width line when it can't.
            <Group gap="xs" wrap="wrap" align="flex-start">
              <Badge variant="light" color={difficultyColor(d.difficulty.level)}
                size="sm" style={{ flexShrink: 0, marginTop: 2 }}>
                {d.difficulty.label} for a Seestar
              </Badge>
              <Text size="sm" c="dimmed" style={{ flex: "1 1 240px" }}>
                {d.difficulty.text}
              </Text>
            </Group>
          ) : null}
          {d.framing && !hideFraming ? (
            <Text size="sm" c={framingColor(d.framing.level)}>
              {framingWithMosaic(d.name || d.id, d.framing, d.mosaic)}
            </Text>
          ) : null}
          {/* "How far did you see?" — the one line on this card that is pure
              wonder rather than advice, so it sits last and reads in the app's
              accent colour. Self-hiding: an object with no vetted catalog
              distance shows nothing at all. */}
          {d.light_travel ? (
            <Text size="sm" c="indigo.5" fs="italic">
              {d.light_travel.text}
            </Text>
          ) : null}
        </Stack>
      </Group>
    </Paper>
  );
}
