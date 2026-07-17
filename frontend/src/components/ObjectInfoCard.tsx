import { Badge, Group, Paper, Stack, Text } from "@mantine/core";
import { IconStars } from "@tabler/icons-react";
import { useQuery } from "@tanstack/react-query";
import { api, type FramingHint } from "../api/client";

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

/** Mantine text colour for a framing verdict: a gentle nudge to mosaic mode for
 *  the too-big cases, plain dimmed for the reassuring "fits" case. */
export function framingColor(level: FramingHint["level"]): string {
  if (level === "mosaic") return "orange.6";
  if (level === "tight") return "yellow.7";
  return "dimmed";
}

/**
 * "What am I looking at?" — an offline catalog lookup that turns a bare folder
 * name (or the solved centre) into friendly context. Renders nothing until a
 * confident match resolves, so it's safe to drop onto any page that knows the
 * target's safe name (Target, History, editor). Shares its query key with the
 * Target page's own identify fetch, so react-query dedupes to one request.
 */
export function ObjectInfoCard({ safe }: { safe: string }) {
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
          {d.framing ? (
            <Text size="sm" c={framingColor(d.framing.level)}>
              {framingSentence(d.name || d.id, d.framing)}
            </Text>
          ) : null}
        </Stack>
      </Group>
    </Paper>
  );
}
