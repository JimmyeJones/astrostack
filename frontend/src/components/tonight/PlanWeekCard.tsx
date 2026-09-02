import { useMemo } from "react";
import { Anchor, Badge, Group, Paper, Table, Text, Title } from "@mantine/core";
import { IconCalendarPlus } from "@tabler/icons-react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { api } from "../../api/client";
import {
  otherTargetNights, targetNightPhrase, weekEmptyReason, weekHeadline,
  weekMoonNote, weekNightLabel,
} from "../../planweek";
import { formatClock, formatMinutes } from "../../tonight";

/**
 * "Plan my week" — which of *your own* targets to point at, on which night.
 *
 * The rest of the planner answers narrower questions: the page around this card
 * ranks everything for *tonight*, "Worth more time" ranks your targets by depth,
 * and the Target page's next-session card plans *one* target forward. None of
 * them answers the one a beginner who only gets out on a clear weekend actually
 * has — *"which night should I go out, and what should I point at?"*
 *
 * Read-only and offline, like the rest of the planner. Self-hides completely
 * when the backend is too old to know the endpoint; when it answers but has
 * nothing to place, it says **why** in one line (no location, no solved
 * positions, no darkness, or nothing high enough) rather than showing an empty
 * table — an empty state that names the next step.
 */
export function PlanWeekCard({ minAlt }: { minAlt?: number }) {
  const q = useQuery({
    queryKey: ["plan-week", minAlt ?? null],
    queryFn: () => api.getPlanWeek(minAlt != null ? { minAlt } : undefined),
    staleTime: 300_000,     // the nights ahead don't change minute to minute
    // An older backend 404s this; that's a quiet no-op, not an error to retry.
    retry: false,
  });
  // One `now` per render pass, so every label in the card agrees about which
  // night is "Tonight" even if the clock ticks past midnight mid-render.
  const now = useMemo(() => new Date(), []);

  const plan = q.data;
  if (!plan) return null;

  const headline = weekHeadline(plan, now);
  const empty = weekEmptyReason(plan);
  const placed = plan.nights.filter((n) => n.best !== null);
  const others = otherTargetNights(plan);

  return (
    <Paper withBorder p="md" data-testid="plan-week">
      <Group justify="space-between" align="flex-start" mb="xs" wrap="wrap">
        <Title order={4}>Plan my week</Title>
        <Text size="xs" c="dimmed">
          Next {plan.nights_scanned} nights · your own targets
        </Text>
      </Group>

      {headline ? (
        <Text size="sm" fw={600} mb="sm">{headline}</Text>
      ) : (
        <Text size="sm" c="dimmed">{empty}</Text>
      )}

      {placed.length > 0 ? (
        <Table highlightOnHover>
          <Table.Thead>
            <Table.Tr>
              <Table.Th>Night</Table.Th>
              <Table.Th>Point at</Table.Th>
              <Table.Th>Shoot between</Table.Th>
              <Table.Th>Time up</Table.Th>
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {placed.map((n) => {
              const best = n.best!;
              const moon = weekMoonNote(n);
              return (
                <Table.Tr key={n.date}>
                  <Table.Td>
                    <Text fw={600} size="sm">{weekNightLabel(n.date, now)}</Text>
                    <Text size="xs" c="dimmed">
                      {formatMinutes(n.dark_minutes)} dark
                    </Text>
                  </Table.Td>
                  <Table.Td>
                    <Anchor component={Link} fw={600} size="sm"
                      to={`/targets/${encodeURIComponent(best.safe)}`}>
                      {best.name}
                    </Anchor>
                    {moon ? (
                      <div>
                        <Badge size="xs" variant="light" color="yellow">{moon}</Badge>
                      </div>
                    ) : null}
                  </Table.Td>
                  <Table.Td>
                    <Text size="sm">
                      {formatClock(best.usable_start_utc)} – {formatClock(best.usable_end_utc)}
                    </Text>
                  </Table.Td>
                  <Table.Td>
                    <Text size="sm">{formatMinutes(best.minutes_above_min_alt)}</Text>
                    <Text size="xs" c="dimmed">
                      peaks {Math.round(best.max_altitude_deg)}°
                    </Text>
                  </Table.Td>
                </Table.Tr>
              );
            })}
          </Table.Tbody>
        </Table>
      ) : null}

      {/* The card names the night; this is what stops the user having to
          remember it. One event per night that has a pick, titled with what to
          point at — the same one-tap .ics the Target page's next-session card
          offers, over the whole week. Only shown when there is something to
          add: the endpoint 404s on an empty week, and a download that fails is
          worse than no button (the standing "is this control gated on the same
          data as the emptiness beside it?" rule). */}
      {placed.length > 0 ? (
        <Anchor href={api.planWeekIcsUrl(minAlt != null ? { minAlt } : undefined)}
          download size="xs" fw={500} mt="sm" display="inline-block">
          <Group gap={4} wrap="nowrap">
            <IconCalendarPlus size={13} />
            Add this week to your calendar
          </Group>
        </Anchor>
      ) : null}

      {others.length > 0 ? (
        <Text size="xs" c="dimmed" mt="sm">
          Each target&apos;s own best night:{" "}
          {others.map((t) => targetNightPhrase(t, now)).join(" · ")}
        </Text>
      ) : null}

      {plan.n_targets_considered < plan.n_targets_with_position ? (
        <Text size="xs" c="dimmed" mt="xs">
          Looked at {plan.n_targets_considered} of your {plan.n_targets_with_position}{" "}
          placed targets.
        </Text>
      ) : null}
    </Paper>
  );
}
