import { Alert, Badge, Button, Group, Paper, Stack, Table, Text, ThemeIcon } from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { IconCalendarStar } from "@tabler/icons-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
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

function NightRow({
  n,
  onSetAside,
  busy,
}: {
  n: NightSummary;
  onSetAside: (n: NightSummary) => void;
  busy: boolean;
}) {
  const badge = verdictBadge(n.verdict);
  const subs = n.n_set_aside > 0 ? `${n.n_kept}/${n.n_frames}` : String(n.n_frames);
  // Only offer "Set aside" when the night still has kept subs to drop and its
  // bounds are known (a night with no datable frames can't be targeted).
  const canSetAside = n.n_kept > 0 && !!n.start_utc && !!n.end_utc;
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
      <Table.Td>
        {canSetAside ? (
          <Button
            size="compact-xs"
            variant="subtle"
            color="gray"
            loading={busy}
            onClick={() => onSetAside(n)}
          >
            Set aside
          </Button>
        ) : n.n_kept === 0 && n.n_frames > 0 ? (
          <Text size="xs" c="dimmed">set aside</Text>
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
 * (sharp / soft / hazy) so a soft or clouded-out night is easy to spot.
 *
 * Each night also has an opt-in **"Set aside"** action: it rejects that night's
 * accepted subs (reversible — the same `user` reject a manual reject uses, never
 * a delete) so a beginner can drop a whole clouded-out or soft night in one click
 * and re-stack a cleaner picture. Undo re-accepts exactly the subs it touched.
 *
 * Renders only when the target spans more than one night — a single night is
 * already covered by the "Last session" card, so this would just duplicate it.
 */
export function NightsCard({ safe }: { safe: string }) {
  const qc = useQueryClient();
  const [undo, setUndo] = useState<{ label: string; ids: number[] } | null>(null);
  const nights = useQuery({
    queryKey: ["nights", safe],
    queryFn: () => api.targetNights(safe),
    enabled: !!safe,
  });

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ["nights", safe] });
    qc.invalidateQueries({ queryKey: ["frames", safe] });
    qc.invalidateQueries({ queryKey: ["target", safe] });  // accepted-count badge
    qc.invalidateQueries({ queryKey: ["reject-summary", safe] });
  };

  const setAside = useMutation({
    mutationFn: (n: NightSummary) =>
      api.setAsideNight(safe, n.start_utc as string, n.end_utc as string),
    onSuccess: (r, n) => {
      const label = formatNightDate(n.start_utc);
      const ids = r.changed_ids ?? [];
      notifications.show({
        message: `Set aside ${r.changed} sub${r.changed === 1 ? "" : "s"} from ${label}. Re-stack (Process target) to see the cleaner picture.`,
        color: "violet",
      });
      setUndo(ids.length ? { label, ids } : null);
      invalidate();
    },
    onError: (e: Error) => notifications.show({ message: e.message, color: "red" }),
  });

  const undoSetAside = useMutation({
    mutationFn: (ids: number[]) => api.bulkFrames(safe, { action: "accept", ids }),
    onSuccess: () => {
      notifications.show({ message: "Restored the night's subs", color: "violet" });
      setUndo(null);
      invalidate();
    },
    onError: (e: Error) => notifications.show({ message: e.message, color: "red" }),
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
            Every night that went into this picture — newest first. Spotted a soft
            or hazy night? Set it aside, then re-stack for a cleaner picture — you
            can undo it if you change your mind.
          </Text>
          <Table.ScrollContainer minWidth={420}>
            <Table verticalSpacing={4} horizontalSpacing="sm" fz="sm">
              <Table.Thead>
                <Table.Tr>
                  <Table.Th>Night</Table.Th>
                  <Table.Th>Subs</Table.Th>
                  <Table.Th>Integration</Table.Th>
                  <Table.Th>FWHM</Table.Th>
                  <Table.Th>Verdict</Table.Th>
                  <Table.Th />
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {rows.map((n, i) => (
                  <NightRow
                    key={n.start_utc ?? i}
                    n={n}
                    onSetAside={setAside.mutate}
                    busy={setAside.isPending && setAside.variables?.start_utc === n.start_utc}
                  />
                ))}
              </Table.Tbody>
            </Table>
          </Table.ScrollContainer>
          {undo ? (
            <Alert color="violet" variant="light" p="xs">
              <Group justify="space-between" wrap="nowrap" gap="sm">
                <Text size="xs">
                  Set aside {undo.ids.length} sub{undo.ids.length === 1 ? "" : "s"} from {undo.label}.
                </Text>
                <Button
                  size="compact-xs"
                  variant="light"
                  color="violet"
                  loading={undoSetAside.isPending}
                  onClick={() => undoSetAside.mutate(undo.ids)}
                >
                  Undo
                </Button>
              </Group>
            </Alert>
          ) : null}
        </Stack>
      </Group>
    </Paper>
  );
}
