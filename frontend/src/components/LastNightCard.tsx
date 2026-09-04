import { Badge, Group, Paper, Stack, Text } from "@mantine/core";
import { IconMoonStars } from "@tabler/icons-react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api, type EarlyStop, type LibrarySessionRecap } from "../api/client";
import {
  formatIntegration, formatNightDate, formatNightDayMonth, isRecentNight,
} from "../format";
import { describeRejects } from "./SessionRecapCard";

/** The Dashboard recap paragraph: what the whole library's last night brought in
 *  across every target, how much was kept vs. set aside (and why). Pure and
 *  offline so it's unit-testable without rendering.
 *
 *  The card is *not* time-boxed — it shows the most recent night whenever that
 *  was — so after a fortnight of cloud the opening clause has to stop saying
 *  "Last night you captured…", which is simply untrue and reads as though the
 *  app has lost track of the date. Beyond the night just gone it names the night
 *  instead ("On 8 Jul you captured…"). `now` is injectable so the wording is
 *  deterministic under test. */
export function describeLibraryNight(
  r: LibrarySessionRecap,
  now: Date = new Date(),
): string {
  const subs = r.n_frames === 1 ? "sub" : "subs";
  const where =
    r.n_targets === 1
      ? `on ${r.targets[0]?.name ?? "one target"}`
      : `across ${r.n_targets} targets`;
  const night = r.night_date ?? r.start_utc;
  const day = formatNightDayMonth(night, now);
  const lead =
    isRecentNight(night, now) || !day ? "Last night you" : `On ${day} you`;
  let out = `${lead} captured ${r.n_frames} ${subs} ${where} (${formatIntegration(
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

/** The night this card is recapping, as a friendly "8 Jul 2026", or `null` when
 *  there is nothing datable to show.
 *
 *  It reads the server's **observing-night** date — the same noon-to-noon local
 *  bucket the imaging calendar, the per-target Nights card and the "Last
 *  session" recap use. The card used to slice the date out of `end_utc`, which
 *  is wrong twice over for an observer west of UTC: a session that runs past
 *  local midnight *ends* on the following UTC day, so the label named tomorrow
 *  and disagreed with the calendar squares right beside it. Falling back to
 *  `start_utc` (not `end_utc`) keeps an older backend at least labelling from
 *  the night's beginning. Pure and unit-testable. */
export function lastNightLabel(
  r: Pick<LibrarySessionRecap, "night_date" | "start_utc">,
): string | null {
  const label = formatNightDate(r.night_date ?? r.start_utc);
  return label === "—" ? null : label;
}

/** "About 40 minutes" / "about 3 h" / "about 2.5 h" — a rounded gap, worded so a
 *  beginner reads it as an estimate, which it is (a median over a handful of
 *  nights). Rounded to the quarter-hour below two hours and the half-hour above,
 *  because the underlying number is never precise enough to earn more digits. */
export function roughDuration(minutes: number): string {
  if (minutes < 120) {
    const m = Math.max(15, Math.round(minutes / 15) * 15);
    return `${m} minutes`;
  }
  const h = Math.round(minutes / 30) / 2;
  return `${h % 1 === 0 ? h.toFixed(0) : h.toFixed(1)} h`;
}

/** "M 42 stopped getting subs at 23:40 — about 3 h earlier than its last 4
 *  nights." — the one line an owner who was asleep cannot get anywhere else.
 *
 *  The live "capture seems to have gone quiet" note (the Target page) covers
 *  someone standing outside, and self-hides once the silence outlasts the 6 h
 *  session gap — by breakfast it is gone. This is the same fact in the past
 *  tense, judged against the target's *own* recent stop times rather than a
 *  clock, so a night ended deliberately at the usual hour never trips it (see
 *  `seestack.session_recap.early_stop`).
 *
 *  Deliberately not an alarm. It reports what happened and names the innocent
 *  explanation in the same breath, because most early stops *are* deliberate and
 *  a Dashboard that cries wolf over bedtime is worse than one that says nothing.
 *  The clock is rendered in the reader's own timezone — the stamp is UTC, and
 *  "23:40" only means anything to someone in the hour they were shooting.
 *  Pure and offline so it is unit-testable without rendering. */
export function describeEarlyStop(e: EarlyStop): string {
  return `${e.name} ${earlyStopClause(e)}. `
    + "Worth a look if you didn't stop on purpose.";
}

/** The name-free half of the sentence above — "stopped getting subs at 23:40 —
 *  about 3 h earlier than its last 4 nights".
 *
 *  Split out so the Target page's Nights card can annotate the row for that
 *  night with the *same* words, without repeating a target name the reader is
 *  already looking at. Two surfaces reporting one measurement must not be able
 *  to phrase it differently, so there is one clause and both read it. */
export function earlyStopClause(
  e: Pick<EarlyStop, "stopped_utc" | "minutes_earlier" | "n_nights_compared">,
): string {
  const clock = new Date(e.stopped_utc).toLocaleTimeString(undefined, {
    hour: "2-digit", minute: "2-digit",
  });
  return `stopped getting subs at ${clock} — about `
    + `${roughDuration(e.minutes_earlier)} earlier than `
    + `its last ${e.n_nights_compared} nights`;
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
  const night = lastNightLabel(r);
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
          {r.early_stop && (
            <Text size="sm" c="dimmed" data-testid="last-night-early-stop">
              <Link to={`/targets/${r.early_stop.safe}`}
                style={{ color: "inherit" }}>
                {describeEarlyStop(r.early_stop)}
              </Link>
            </Text>
          )}
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
