import { Center, Group, Paper, SimpleGrid, Stack, Text } from "@mantine/core";
import {
  IconActivity, IconClock, IconLayoutGrid, IconPhoto, IconStack2, IconStars,
} from "@tabler/icons-react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api } from "../../api/client";
import type { DashboardStats } from "../../api/client";
import { formatDiskSize, formatIntegration } from "../../format";
import { lifeListLine } from "../lifeListLine";
import { describeSkyCoverage } from "../skyCoverage";

/**
 * One number on the stat row. When the question it answers has an obvious next
 * screen (`to`), the whole tile becomes a link to it — "2 active jobs" should not
 * send a beginner hunting in the sidebar for the Jobs page. Deliberately styled
 * identically either way: this should read as "the number is a link", not as new
 * chrome, and the tiles with no single right destination ("Integration",
 * "Frames") stay plain rather than being given an arbitrary one.
 */
function StatCard({ icon, label, value, sub, to }: {
  icon: React.ReactNode; label: string; value: string; sub?: string; to?: string;
}) {
  const body = (
    <Group gap="sm" wrap="nowrap">
      <Center w={40} h={40} bg="dark.6" style={{ borderRadius: 8, flexShrink: 0 }}>
        {icon}
      </Center>
      <div style={{ minWidth: 0 }}>
        <Text size="xs" c="dimmed">{label}</Text>
        <Text fw={700} size="lg" lh={1.2}>{value}</Text>
        {sub ? <Text size="xs" c="dimmed">{sub}</Text> : null}
      </div>
    </Group>
  );
  if (!to) {
    return <Paper withBorder p="md" radius="md">{body}</Paper>;
  }
  return (
    <Paper
      withBorder p="md" radius="md" component={Link} to={to}
      // An <a> would otherwise take the browser's link colour and underline —
      // the tile must look exactly like its plain siblings.
      style={{ color: "inherit", textDecoration: "none" }}
      aria-label={`${label}: ${value}`}
    >
      {body}
    </Paper>
  );
}

/**
 * "At a glance" — the Dashboard's library numbers: six stat tiles, then the
 * sky-coverage and life-list read-outs as quiet lines under them.
 *
 * Split out of `routes/Dashboard.tsx` for the owner's "recursive organization"
 * ask (2026-11-17): it is one of the page's five top-level groups, and a new
 * library number joins it as a line or a tile rather than becoming a card.
 */
export function AtAGlance({ data }: { data: DashboardStats }) {
  // "How much of the sky have you actually seen?" — a pride stat that lived one
  // nav click and one mode switch away, under My map. It's measured server-side
  // off each run's own WCS and cached against the same "did a picture change?"
  // fingerprint the map uses, so saying it here costs one cheap request and no
  // new machinery. Same key as the map's own query, so the two share a cache —
  // and the same helper, verbatim, so the two sentences can never drift.
  const coverage = useQuery({
    queryKey: ["sky-coverage"], queryFn: () => api.skyCoverage(), staleTime: 60_000,
  });
  // "42 of the 110 Messier objects" — the counts half of the life list, which
  // already exists as a page nothing on the home screen ever points at. The
  // counts-only route so the Dashboard doesn't pull ~160 catalog rows (and the
  // per-target preview stat behind their thumbnails) for one sentence; its own
  // query key for the same reason — sharing the page's would make the page's
  // full fetch the thing that fills this cache.
  const lifeList = useQuery({
    queryKey: ["life-list-counts"], queryFn: () => api.lifeListCounts(),
    staleTime: 60_000,
  });

  const accept = data.acceptance_rate == null ? "—" : `${Math.round(data.acceptance_rate * 100)}%`;
  // Rendered from the raw byte counts so this tile agrees with the Storage
  // page's headroom note; the decimal `*_gb` fields are the fallback for an
  // older backend that doesn't send bytes.
  const free = data.disk.free_bytes != null
    ? formatDiskSize(data.disk.free_bytes)
    : data.disk.free_gb != null ? `${data.disk.free_gb} GB` : "—";
  const total = data.disk.total_bytes != null
    ? formatDiskSize(data.disk.total_bytes)
    : data.disk.total_gb != null ? `${data.disk.total_gb} GB` : null;
  const usedSub = total ? `of ${total}` : undefined;
  const coverageLine = coverage.data
    ? describeSkyCoverage(coverage.data.deg2, coverage.data.sky_fraction,
                          coverage.data.n_pictures, coverage.data.summed_deg2)
    : "";
  const lifeLine = lifeListLine(lifeList.data);

  return (
    <Stack gap="xs" data-dashboard-group="glance">
      <SimpleGrid cols={{ base: 2, sm: 3, lg: 6 }}>
        <StatCard icon={<IconStars size={22} color="var(--mantine-color-violet-4)" />}
          label="Targets" value={String(data.n_targets)}
          sub={`${data.n_targets_with_stacks} stacked`} to="/library" />
        <StatCard icon={<IconClock size={22} color="var(--mantine-color-violet-4)" />}
          label="Integration" value={formatIntegration(data.integration_hours * 3600)} />
        <StatCard icon={<IconPhoto size={22} color="var(--mantine-color-violet-4)" />}
          label="Frames" value={String(data.n_frames)}
          sub={`${data.n_frames_accepted} kept · ${accept}`} />
        <StatCard icon={<IconStack2 size={22} color="var(--mantine-color-violet-4)" />}
          label="Stacks" value={String(data.n_stack_runs)} to="/gallery" />
        <StatCard icon={<IconActivity size={22} color="var(--mantine-color-violet-4)" />}
          label="Active jobs" value={String(data.active_jobs)} to="/jobs" />
        <StatCard icon={<IconLayoutGrid size={22} color="var(--mantine-color-violet-4)" />}
          label="Free disk" value={free} sub={usedSub} to="/storage" />
      </SimpleGrid>

      {/* One quiet line rather than another card: it belongs with the counts
          above it, and the busy-page rule says a new fact joins a grouping
          instead of becoming one more block. Self-hides until a finished
          picture actually carries a position, so a fresh install sees nothing
          and no number is invented. */}
      {coverageLine ? (
        <Text size="sm" c="dimmed" data-testid="sky-coverage-line">
          {coverageLine}{" "}
          <Text component={Link} to="/sky?view=mine" size="sm" c="violet" span>
            See it on My map →
          </Text>
        </Text>
      ) : null}

      {/* The life list's own number, in the same quiet-line grouping as the
          coverage read-out above rather than a seventh stat tile or an eighth
          card — the busy-page rule again. Self-hides until at least one famous
          object is captured, so a fresh install sees nothing and nobody meets a
          0-of-110 scoreboard before they have made a picture. */}
      {lifeLine ? (
        <Text size="sm" c="dimmed" mt={coverageLine ? -4 : 0} data-testid="life-list-line">
          {lifeLine}{" "}
          <Text component={Link} to="/life-list" size="sm" c="violet" span>
            See your life list →
          </Text>
        </Text>
      ) : null}
    </Stack>
  );
}
