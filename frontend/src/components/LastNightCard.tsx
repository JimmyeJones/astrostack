import { Badge, Group, Paper, Stack, Text } from "@mantine/core";
import { IconMoonStars } from "@tabler/icons-react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import {
  api, type EarlyStop, type LibrarySessionRecap, type NeedsLook, type NewPicture,
} from "../api/client";
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

/** "AstroStack stacked a new picture of M 42 — 120 subs, deeper than the 78 it
 *  had before." — what the app *did* with the night, for one target.
 *
 *  The "deeper than before" clause is only said when it is true: a re-stack that
 *  used the same subs, or fewer (some were set aside), gets the plain count. A
 *  target's first ever picture says so instead of comparing against nothing.
 *  Pure and offline so it is unit-testable without rendering. */
export function describeNewPicture(p: NewPicture): string {
  const subs = `${p.n_frames} sub${p.n_frames === 1 ? "" : "s"}`;
  const prev = p.previous_frames;
  if (prev == null) return `${p.name} — its first picture, from ${subs}`;
  if (p.n_frames > prev) {
    return `${p.name} — ${subs}, deeper than the ${prev} it had before`;
  }
  return `${p.name} — ${subs}`;
}

/** The opening clause above the per-picture lines: "While you were away,
 *  AstroStack made 3 new pictures." — or null when it made none, so the card
 *  stays exactly as it was on a night nothing was stacked (the owner's live
 *  settings have auto-stack off, and a card that announced "0 new pictures"
 *  every morning would be noise). */
export function describeOvernightWork(pictures: NewPicture[]): string | null {
  if (pictures.length === 0) return null;
  if (pictures.length === 1) return "While you were away, AstroStack made a new picture.";
  return `While you were away, AstroStack made ${pictures.length} new pictures.`;
}

/** "NGC 7000 is waiting — 516 of its subs had no file on disk, so your existing
 *  picture was kept rather than replaced with a thinner one."
 *
 *  The two holds read very differently to a beginner and must not be worded
 *  alike: a *thin* hold is the app being patient and will clear itself on the
 *  next clear night, while *missing files* means something outside the app —
 *  an unplugged drive, a share that dropped — and is the one thing here worth
 *  getting up for (AGENTS.md §1, the walk-away degradation family). Pure and
 *  offline so it is unit-testable without rendering. */
export function describeNeedsLook(h: NeedsLook): string {
  if (h.kind === "missing_files") {
    const missing = `${h.n_other} of its sub${h.n_other === 1 ? "" : "s"}`;
    return `${h.name} is waiting — ${missing} had no file on disk, so your `
      + "existing picture was kept rather than replaced with a thinner one. "
      + "Worth checking the drive with your subs on it is connected.";
  }
  return `${h.name} is waiting — only ${h.n_frames} of its subs are located so `
    + `far, and it needs ${h.n_other} to make a picture worth showing. It will `
    + "stack itself once more subs come in.";
}

/**
 * "Last night" — a small, persistent, plain-language Dashboard card answering
 * the first question a walk-away user has on return: *what did last night give
 * me?*, combined across every target they shot that night. Built entirely from
 * data already on disk (each target's frames table), so it renders only when
 * there's a datable capture night to report and needs no config.
 *
 * It also carries the *other* half of the morning question — what the app
 * **did** with the night: the pictures it stacked while nobody was watching,
 * and any target its scan held back. Those lines live here rather than in a card
 * of their own because they answer the same question on a Dashboard the owner
 * has called busy (AGENTS.md §1 — prefer a consolidation over a new card), and
 * each self-hides when there is nothing to say, so an install with auto-stack
 * off (the owner's live setting) sees exactly what it saw before.
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
  // Both default to empty against an older backend, so every line below is
  // simply absent rather than half-rendered.
  const made = r.new_pictures ?? [];
  const held = r.needs_look ?? [];
  const work = describeOvernightWork(made);
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
          {/* What the app did with the night. One line per picture, because a
              beginner's question is "which of my targets got better?", and a
              single rolled-up count answers it for nobody. */}
          {work && (
            <Stack gap={2} data-testid="last-night-new-pictures">
              <Text size="sm">{work}</Text>
              {made.map((p) => (
                <Text key={`${p.safe}-${p.run_id}`} size="sm" c="dimmed">
                  <Link to={`/targets/${p.safe}/history`} style={{ color: "inherit" }}>
                    {describeNewPicture(p)}
                  </Link>
                </Text>
              ))}
            </Stack>
          )}
          {/* …and what it deliberately did *not* do. Explained where the news
              is, rather than only on the Jobs page a beginner never opens. */}
          {held.map((h) => (
            <Text key={h.safe} size="sm" c={h.kind === "missing_files" ? "yellow" : "dimmed"}
              data-testid={`last-night-needs-look-${h.kind}`}>
              <Link to={`/targets/${h.safe}`} style={{ color: "inherit" }}>
                {describeNeedsLook(h)}
              </Link>
            </Text>
          ))}
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
