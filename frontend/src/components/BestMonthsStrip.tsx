import { Box, Group, Paper, Stack, Text, ThemeIcon, Tooltip } from "@mantine/core";
import { IconCalendarMonth } from "@tabler/icons-react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import { bestMonthsVerdict, monthLabel } from "./bestMonths";

const MONTH_INITIALS = ["J", "F", "M", "A", "M", "J", "J", "A", "S", "O", "N", "D"];

/**
 * "Best time of year to shoot this" — a compact seasonal-observability strip.
 *
 * The plan-ahead companion to the tonight-only "Plan your next night" card:
 * instead of "when's the next dark window in the coming fortnight?", it answers
 * the beginner's most common plan-ahead question about a named object — "when
 * *this year* can I actually get it?" — with a glanceable 12-cell heat strip (one
 * cell per month, shaded by how well-placed the target is) and one plain-language
 * verdict ("Best around Nov–Feb, highest in December").
 *
 * Read-only and self-hiding: it renders nothing until the planner returns twelve
 * months (needs a saved location and a solved position), so it never nags and
 * never duplicates the "set a location" prompt the Tonight page already shows.
 */
export function BestMonthsStrip({ safe }: { safe: string }) {
  const q = useQuery({
    queryKey: ["best-months", safe],
    queryFn: () => api.bestMonths(safe),
    enabled: !!safe,
  });

  const months = q.data?.months ?? [];
  if (months.length !== 12) return null;
  const verdict = bestMonthsVerdict(months);
  if (!verdict) return null;

  return (
    <Paper withBorder p="sm" radius="md" mt="xs">
      <Group gap="sm" wrap="nowrap" align="flex-start">
        <ThemeIcon size={22} radius="xl" variant="light" color="teal"
          style={{ flexShrink: 0, marginTop: 2 }}>
          <IconCalendarMonth size={14} />
        </ThemeIcon>
        <Stack gap={6} style={{ flex: 1, minWidth: 0 }}>
          <Text size="sm" fw={500}>Best time of year to shoot this</Text>
          <Text size="xs" c="dimmed">{verdict.text}</Text>
          <Group gap={3} wrap="nowrap" mt={2}>
            {months.map((m, i) => {
              const shade = verdict.shades[i] ?? 0;
              const isPeak = verdict.peakMonth === m.month;
              const usableH = m.usable_dark_minutes / 60;
              const tip = m.dark_minutes <= 0
                ? `${monthLabel(m.month)}: no darkness (polar day)`
                : m.usable_dark_minutes > 0
                  ? `${monthLabel(m.month)}: up ~${usableH.toFixed(1)} h in the dark, peaks ${Math.round(m.max_transit_alt_deg)}°`
                  : `${monthLabel(m.month)}: doesn't clear the floor (peaks ${Math.round(m.max_transit_alt_deg)}°)`;
              return (
                <Tooltip key={m.month} label={tip} withArrow openDelay={200}>
                  <Box
                    aria-label={tip}
                    style={{
                      flex: 1,
                      minWidth: 0,
                      height: 26,
                      borderRadius: 4,
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                      // Shade from a faint wash to solid teal by observability.
                      backgroundColor: `rgba(45, 158, 137, ${0.12 + shade * 0.78})`,
                      border: isPeak
                        ? "2px solid var(--mantine-color-teal-4)"
                        : "1px solid transparent",
                      color: shade > 0.5 ? "white" : "var(--mantine-color-dimmed)",
                      fontSize: 10,
                      fontWeight: isPeak ? 700 : 500,
                    }}
                  >
                    {MONTH_INITIALS[i]}
                  </Box>
                </Tooltip>
              );
            })}
          </Group>
        </Stack>
      </Group>
    </Paper>
  );
}
