import { Badge, Group, Paper, Stack, Text } from "@mantine/core";
import { IconMoonStars } from "@tabler/icons-react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api, type LibrarySessionRecap } from "../api/client";
import { formatIntegration } from "../format";
import { describeRejects } from "./SessionRecapCard";

/** The Dashboard recap paragraph: what the whole library's last night brought in
 *  across every target, how much was kept vs. set aside (and why). Pure and
 *  offline so it's unit-testable without rendering. */
export function describeLibraryNight(r: LibrarySessionRecap): string {
  const subs = r.n_frames === 1 ? "sub" : "subs";
  const where =
    r.n_targets === 1
      ? `on ${r.targets[0]?.name ?? "one target"}`
      : `across ${r.n_targets} targets`;
  let out = `Last night you captured ${r.n_frames} ${subs} ${where} (${formatIntegration(
    r.session_exposure_s,
  )}).`;
  if (r.n_set_aside === 0) {
    out += ` All ${r.n_kept} were kept.`;
  } else {
    const why = describeRejects(r.reject_buckets);
    out += ` ${r.n_kept} kept; ${r.n_set_aside} set aside${why ? ` (${why})` : ""}.`;
  }
  return out;
}

/**
 * "Last night" — a small, persistent, plain-language Dashboard card answering
 * the first question a walk-away user has on return: *what did last night give
 * me?*, combined across every target they shot that night. Built entirely from
 * data already on disk (each target's frames table), so it renders only when
 * there's a datable capture night to report and needs no config.
 */
export function LastNightCard() {
  // Last night's capture rarely changes between polls, so a plain staleTime is
  // enough — no aggressive refetch (the endpoint opens every project).
  const q = useQuery({
    queryKey: ["last-night"],
    queryFn: api.getLastNight,
    staleTime: 60_000,
  });
  const r = q.data;
  if (!r || r.n_frames === 0) return null;
  const keptPct = r.n_frames > 0 ? Math.round((r.n_kept / r.n_frames) * 100) : 0;
  // Label the night by when it *began*, not when the last sub landed: an
  // observing session that runs past UTC midnight (routine anywhere east of the
  // Atlantic) has an `end_utc` on the following morning's date, so `end_utc`
  // would tag "Last night" with tomorrow. The session's start date is the "night
  // of" a person means. (Still UTC-based — the true local date needs the
  // observer's longitude, which we don't reliably have here.)
  const night = r.start_utc ? r.start_utc.slice(0, 10) : r.end_utc ? r.end_utc.slice(0, 10) : null;
  return (
    <Paper withBorder p="sm" radius="md">
      <Group gap="sm" wrap="nowrap" align="flex-start">
        <IconMoonStars size={22} style={{ flexShrink: 0, marginTop: 2 }}
          color="var(--mantine-color-violet-5)" />
        <Stack gap={6} style={{ flex: 1, minWidth: 0 }}>
          <Group gap="xs" justify="space-between" wrap="nowrap">
            <Text size="sm" fw={500}>Last night{night ? ` · ${night}` : ""}</Text>
            <Badge variant="light" color="violet" size="sm">{keptPct}% kept</Badge>
          </Group>
          <Text size="sm" c="dimmed">{describeLibraryNight(r)}</Text>
          {r.targets.length > 1 && (
            <Group gap="xs">
              {r.targets.map((t) => (
                <Badge key={t.safe} variant="light" color="gray" size="sm"
                  component={Link} to={`/targets/${t.safe}`}
                  style={{ cursor: "pointer" }}>
                  {t.name} · {t.n_frames} sub{t.n_frames === 1 ? "" : "s"}
                </Badge>
              ))}
            </Group>
          )}
        </Stack>
      </Group>
    </Paper>
  );
}
