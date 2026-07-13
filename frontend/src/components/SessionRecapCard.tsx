import { Badge, Group, Paper, Stack, Text } from "@mantine/core";
import { IconMoonStars } from "@tabler/icons-react";
import { useQuery } from "@tanstack/react-query";
import { api, type SessionQualityDrift, type SessionRecap } from "../api/client";
import { formatIntegration } from "../format";

// Plain-language names for the reject buckets the backend groups into, in the
// order we like to list them. Anything not here (e.g. "set aside by you",
// "other") is shown with its own label verbatim.
const BUCKET_ORDER = ["cloudy", "trailed", "soft", "unreadable"];

/** One friendly line naming why subs were set aside, e.g.
 *  "10 cloudy, 2 trailed" — ordered, plain-language, only the buckets present. */
export function describeRejects(buckets: Record<string, number>): string {
  const entries = Object.entries(buckets).filter(([, n]) => n > 0);
  if (entries.length === 0) return "";
  entries.sort((a, b) => {
    const ia = BUCKET_ORDER.indexOf(a[0]);
    const ib = BUCKET_ORDER.indexOf(b[0]);
    // Known buckets first (in BUCKET_ORDER), then the rest by count desc.
    if (ia !== ib) return (ia < 0 ? 99 : ia) - (ib < 0 ? 99 : ib);
    return b[1] - a[1];
  });
  return entries.map(([label, n]) => `${n} ${label}`).join(", ");
}

/** The recap paragraph a beginner reads on return: what last session added, how
 *  much was kept vs. set aside (and why), and where the target stands now.
 *  Pure and offline so it's unit-testable without rendering. */
export function describeSession(r: SessionRecap): string {
  const subs = r.n_frames === 1 ? "sub" : "subs";
  let out = `Last session added ${r.n_frames} ${subs} (${formatIntegration(r.session_exposure_s)}).`;
  if (r.n_set_aside === 0) {
    out += ` All ${r.n_kept} were kept.`;
  } else {
    const why = describeRejects(r.reject_buckets);
    out += ` ${r.n_kept} kept; ${r.n_set_aside} set aside${why ? ` (${why})` : ""}.`;
  }
  out += ` Total on this target: ${formatIntegration(r.total_kept_exposure_s)}.`;
  return out;
}

/** A gentle, plain-language heads-up when the newest session is materially softer
 *  than the target's best previous one — a whole-session focus/seeing dip that
 *  auto-grade (relative *within* a session) can't catch. Pure and unit-testable. */
export function describeQualityDrift(d: SessionQualityDrift): string {
  const latest = d.latest_fwhm_px.toFixed(1);
  const best = d.baseline_fwhm_px.toFixed(1);
  return (
    `Heads up: last session's stars are softer than your usual best ` +
    `(${latest} px vs ${best} px FWHM) — worth checking focus.`
  );
}

/**
 * "Last session" recap — a small, persistent, plain-language card answering the
 * first question a walk-away user has on return: *what did last night give me?*
 * Built entirely from data already on disk (the frames table), so it renders
 * only when there's something datable to report and needs no config. Safe to
 * drop onto any page that knows the target's safe name.
 */
export function SessionRecapCard({ safe }: { safe: string }) {
  const recap = useQuery({
    queryKey: ["session-recap", safe],
    queryFn: () => api.sessionRecap(safe),
    enabled: !!safe,
  });
  const r = recap.data;
  if (!r || r.n_frames === 0) return null;
  const keptPct = r.n_frames > 0 ? Math.round((r.n_kept / r.n_frames) * 100) : 0;
  return (
    <Paper withBorder p="sm" radius="md" mt="xs">
      <Group gap="sm" wrap="nowrap" align="flex-start">
        <IconMoonStars size={22} style={{ flexShrink: 0, marginTop: 2 }}
          color="var(--mantine-color-violet-5)" />
        <Stack gap={4} style={{ flex: 1, minWidth: 0 }}>
          <Group gap="xs" justify="space-between" wrap="nowrap">
            <Text size="sm" fw={500}>Last session</Text>
            <Badge variant="light" color="violet" size="sm">{keptPct}% kept</Badge>
          </Group>
          <Text size="sm" c="dimmed">{describeSession(r)}</Text>
          {r.quality_drift && (
            <Text size="sm" c="yellow.7">{describeQualityDrift(r.quality_drift)}</Text>
          )}
        </Stack>
      </Group>
    </Paper>
  );
}
