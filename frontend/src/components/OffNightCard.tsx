/**
 * "Was last night off for you?" — a heads-up when the most recent night's stars
 * came out materially fatter than the owner's own usual.
 *
 * The app already trends star size *within* one session (the Target page's
 * "Focus & sharpness" card, early third vs late third), which catches focus
 * drifting away over a night — but a night that was soft from the very first
 * sub reads as perfectly "steady" there. Dew that formed before the first frame,
 * a focus left wrong from last time, or simply a bad-seeing night looks fine
 * until a stack comes out mushy weeks later. This says so the morning after,
 * while there is still something to do about it.
 *
 * Read-only, and it rides on the activity calendar the Dashboard heatmap already
 * fetches and the server already caches — no extra library walk.
 *
 * Self-hiding by design, which is the whole point: the backend answers null on a
 * normal night, on a library without enough history to have a "usual", and on an
 * older backend. A card that congratulated a good night would be noise, and
 * "your best night" already covers the sharp end.
 */
import { Group, Paper, Stack, Text, ThemeIcon } from "@mantine/core";
import { IconEyeglass } from "@tabler/icons-react";
import { useQuery } from "@tanstack/react-query";
import { api, type OffNight } from "../api/client";

/** "4.4 px that night vs 3.0 px across your previous 9 measured nights." */
export function measurementLine(off: OffNight): string {
  const n = off.baseline_nights;
  return `${off.median_fwhm_px.toFixed(1)} px that night vs `
    + `${off.baseline_fwhm_px.toFixed(1)} px across your previous `
    + `${n} measured night${n === 1 ? "" : "s"}.`;
}

export function OffNightCard() {
  const cal = useQuery({
    queryKey: ["activity-calendar"],
    queryFn: () => api.getActivityCalendar(12),
    staleTime: 60_000,
    retry: false,
  });

  const off = cal.data?.off_night;
  if (!off) return null;

  return (
    <Paper withBorder p="sm" radius="md" mt="xs" data-testid="off-night">
      <Group gap="sm" wrap="nowrap" align="flex-start">
        <ThemeIcon size={22} radius="xl" variant="light"
          color={off.level === "much_fatter" ? "orange" : "yellow"}
          style={{ flexShrink: 0, marginTop: 2 }}>
          <IconEyeglass size={14} />
        </ThemeIcon>
        <Stack gap={4} style={{ flex: 1, minWidth: 0 }}>
          <Text size="sm" fw={500}>{off.label}</Text>
          <Text size="xs" c="dimmed">{off.text}</Text>
          {/* The two numbers behind the sentence, so the claim is checkable
              rather than asserted. Star size is in pixels because that is the
              unit every other sharpness readout in the app uses. Built as one
              string rather than interleaved JSX so it stays one text node. */}
          <Text size="xs" c="dimmed">{measurementLine(off)}</Text>
        </Stack>
      </Group>
    </Paper>
  );
}
