import { Badge, Group, Paper, Stack, Table, Text, ThemeIcon } from "@mantine/core";
import { IconCalendarStar } from "@tabler/icons-react";
import { useQuery } from "@tanstack/react-query";
import { api, type NightSummary } from "../api/client";
import { formatIntegration } from "../format";

const MONTHS_ABBR = [
  "Jan", "Feb", "Mar", "Apr", "May", "Jun",
  "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
];

/**
 * A friendly night date ("8 Jul 2026") from an ISO-8601 UTC stamp. We read the
 * date parts straight off the string rather than via `Date`, so the night label
 * never shifts across a timezone boundary (mirrors `formatMonthYear`).
 */
export function formatNightDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso);
  if (!m) return "—";
  const monthIdx = parseInt(m[2], 10) - 1;
  if (monthIdx < 0 || monthIdx > 11) return "—";
  return `${parseInt(m[3], 10)} ${MONTHS_ABBR[monthIdx]} ${m[1]}`;
}

/** Colour + label for a night's one-word verdict badge, or null (no badge) when
 *  there's too little measured to judge ("" verdict). Pure/testable. */
export function verdictBadge(verdict: string): { color: string; label: string } | null {
  switch (verdict) {
    case "sharp":
      return { color: "teal", label: "sharp" };
    case "soft":
      return { color: "yellow", label: "soft" };
    case "hazy":
      return { color: "orange", label: "hazy" };
    default:
      return null;
  }
}

function NightRow({ n }: { n: NightSummary }) {
  const badge = verdictBadge(n.verdict);
  const subs = n.n_set_aside > 0 ? `${n.n_kept}/${n.n_frames}` : String(n.n_frames);
  return (
    <Table.Tr>
      <Table.Td>
        <Group gap={6} wrap="nowrap">
          <Text size="sm">{formatNightDate(n.start_utc)}</Text>
          {n.is_best ? (
            <Badge size="xs" variant="light" color="violet">sharpest</Badge>
          ) : null}
        </Group>
      </Table.Td>
      <Table.Td>
        <Text size="sm">{subs}</Text>
      </Table.Td>
      <Table.Td>
        <Text size="sm">{formatIntegration(n.kept_exposure_s)}</Text>
      </Table.Td>
      <Table.Td>
        <Text size="sm" c="dimmed">
          {n.median_fwhm_px != null ? `${n.median_fwhm_px.toFixed(1)} px` : "—"}
        </Text>
      </Table.Td>
      <Table.Td>
        {badge ? (
          <Badge size="sm" variant="light" color={badge.color}>{badge.label}</Badge>
        ) : null}
      </Table.Td>
    </Table.Tr>
  );
}

/**
 * "Nights" — every capture night that went into this target, newest first.
 *
 * The §1 owner shoots one target across many nights (the Seestar writes a new
 * folder per night), and today there's no per-target view of *all* the nights
 * behind a picture — only the single-night "Last session" card. This lists each
 * night's kept-vs-total subs, integration, median FWHM, and a one-word verdict
 * (sharp / soft / hazy) so a soft or clouded-out night is easy to spot. Purely
 * informational and read-only.
 *
 * Renders only when the target spans more than one night — a single night is
 * already covered by the "Last session" card, so this would just duplicate it.
 */
export function NightsCard({ safe }: { safe: string }) {
  const nights = useQuery({
    queryKey: ["nights", safe],
    queryFn: () => api.targetNights(safe),
    enabled: !!safe,
  });
  const rows = nights.data;
  if (!rows || rows.length < 2) return null;
  return (
    <Paper withBorder p="sm" radius="md" mt="xs">
      <Group gap="sm" wrap="nowrap" align="flex-start">
        <ThemeIcon size={22} radius="xl" variant="light" color="violet"
          style={{ flexShrink: 0, marginTop: 2 }}>
          <IconCalendarStar size={14} />
        </ThemeIcon>
        <Stack gap={6} style={{ flex: 1, minWidth: 0 }}>
          <Text size="sm" fw={500}>Nights</Text>
          <Text size="xs" c="dimmed">
            Every night that went into this picture — newest first. A soft or hazy
            night is worth a look; you can set a bad night aside from its frames.
          </Text>
          <Table.ScrollContainer minWidth={340}>
            <Table verticalSpacing={4} horizontalSpacing="sm" fz="sm">
              <Table.Thead>
                <Table.Tr>
                  <Table.Th>Night</Table.Th>
                  <Table.Th>Subs</Table.Th>
                  <Table.Th>Integration</Table.Th>
                  <Table.Th>FWHM</Table.Th>
                  <Table.Th>Verdict</Table.Th>
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {rows.map((n, i) => (
                  <NightRow key={n.start_utc ?? i} n={n} />
                ))}
              </Table.Tbody>
            </Table>
          </Table.ScrollContainer>
        </Stack>
      </Group>
    </Paper>
  );
}
