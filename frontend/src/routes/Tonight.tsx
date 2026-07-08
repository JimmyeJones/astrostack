import { useState } from "react";
import {
  Alert, Anchor, Badge, Card, Center, Group, Loader, Paper, Select, SimpleGrid,
  Stack, Table, Text, Title, Tooltip,
} from "@mantine/core";
import { IconMoon, IconStars, IconTelescope } from "@tabler/icons-react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api, type PlannedTarget } from "../api/client";
import { QueryError } from "../components/QueryError";
import { formatIntegration } from "../format";
import {
  formatClock, formatMinutes, moonPhaseLabel, scoreColor, splitTargets,
} from "../tonight";

const MIN_ALT_OPTIONS = [
  { value: "10", label: "10° (low)" },
  { value: "20", label: "20°" },
  { value: "30", label: "30° (default)" },
  { value: "40", label: "40°" },
  { value: "50", label: "50° (high only)" },
];

function ScoreBadge({ score }: { score: number }) {
  return (
    <Tooltip label="Higher = better placed tonight (altitude, time up, Moon clear)">
      <Badge color={scoreColor(score)} variant="light" size="lg">
        {Math.round(score)}
      </Badge>
    </Tooltip>
  );
}

function TargetRow({ t }: { t: PlannedTarget }) {
  const label = t.name && t.name !== t.id ? `${t.id} — ${t.name}` : t.id;
  return (
    <Table.Tr>
      <Table.Td>
        {t.target_safe ? (
          <Anchor component={Link} to={`/targets/${t.target_safe}`} fw={600}>
            {label}
          </Anchor>
        ) : (
          <Text fw={600}>{label}</Text>
        )}
        <Text size="xs" c="dimmed">
          {[t.type, t.con].filter(Boolean).join(" · ")}
          {t.already_targeted && t.frames_accepted != null
            ? ` · ${t.frames_accepted} subs, ${formatIntegration(t.total_exposure_s ?? 0)}`
            : ""}
        </Text>
      </Table.Td>
      <Table.Td>{t.max_altitude_deg.toFixed(0)}°</Table.Td>
      <Table.Td>{formatClock(t.transit_utc)}</Table.Td>
      <Table.Td>{formatMinutes(t.minutes_above_min_alt)}</Table.Td>
      <Table.Td>{t.moon_separation_deg.toFixed(0)}°</Table.Td>
      <Table.Td><ScoreBadge score={t.score} /></Table.Td>
    </Table.Tr>
  );
}

function TargetTable({ targets }: { targets: PlannedTarget[] }) {
  if (targets.length === 0) {
    return <Text size="sm" c="dimmed">Nothing here clears your minimum altitude tonight.</Text>;
  }
  return (
    <Table.ScrollContainer minWidth={520}>
      <Table striped highlightOnHover>
        <Table.Thead>
          <Table.Tr>
            <Table.Th>Target</Table.Th>
            <Table.Th>Max alt</Table.Th>
            <Table.Th>Transit</Table.Th>
            <Table.Th>Time up</Table.Th>
            <Table.Th>Moon</Table.Th>
            <Table.Th>Score</Table.Th>
          </Table.Tr>
        </Table.Thead>
        <Table.Tbody>
          {targets.map((t) => <TargetRow key={t.id} t={t} />)}
        </Table.Tbody>
      </Table>
    </Table.ScrollContainer>
  );
}

export function TonightView() {
  const [minAlt, setMinAlt] = useState<string>("");
  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: ["tonight", minAlt],
    queryFn: () => api.getTonight(minAlt ? { minAlt: Number(minAlt) } : undefined),
    staleTime: 60_000,
  });

  if (isLoading) {
    return <Center h={300}><Loader /></Center>;
  }
  if (isError || !data) {
    return <QueryError error={error} onRetry={() => refetch()} />;
  }

  const header = (
    <Group justify="space-between" align="flex-end" wrap="wrap">
      <div>
        <Title order={2}>
          <Group gap="xs"><IconStars size={26} /> Tonight</Group>
        </Title>
        <Text c="dimmed" size="sm">
          The best deep-sky targets to point the scope at tonight — ranked, offline.
          {data.horizon_active
            ? " Time-up accounts for your horizon / tree mask."
            : ""}
        </Text>
      </div>
      <Select
        label="Minimum altitude"
        data={MIN_ALT_OPTIONS}
        value={minAlt || String(data.min_altitude_deg)}
        onChange={(v) => setMinAlt(v ?? "")}
        w={180}
        allowDeselect={false}
      />
    </Group>
  );

  if (data.location_source === "none") {
    return (
      <Stack gap="lg">
        {header}
        <Alert color="blue" icon={<IconTelescope size={18} />} title="Set your observing location">
          <Text size="sm">
            The planner needs to know where you're observing from. It reads your
            location automatically from a plate-solved Seestar frame
            (SITELAT/SITELONG) — so once you've solved some subs it'll just work.
            You can also set it manually under{" "}
            <Anchor component={Link} to="/settings">Settings → Observing site</Anchor>.
          </Text>
        </Alert>
      </Stack>
    );
  }

  if (!data.dark_window) {
    return (
      <Stack gap="lg">
        {header}
        <Alert color="yellow" icon={<IconMoon size={18} />} title="No darkness tonight">
          <Text size="sm">
            At your location the Sun doesn't set far enough tonight (polar day or
            the height of summer), so there's no usable dark window to plan around.
          </Text>
        </Alert>
      </Stack>
    );
  }

  const dw = data.dark_window;
  const twilight =
    dw.sun_alt_threshold_deg <= -18 ? "astronomical"
    : dw.sun_alt_threshold_deg <= -12 ? "nautical (short summer night)"
    : "twilight only";
  const { already, fresh } = splitTargets(data.targets);

  return (
    <Stack gap="lg">
      {header}

      <SimpleGrid cols={{ base: 1, sm: 3 }}>
        <Card withBorder padding="sm">
          <Text size="xs" c="dimmed">Dark window ({twilight})</Text>
          <Text fw={600}>{formatClock(dw.start_utc)} – {formatClock(dw.end_utc)}</Text>
          <Text size="xs" c="dimmed">{formatMinutes(dw.duration_minutes)} of darkness</Text>
        </Card>
        <Card withBorder padding="sm">
          <Text size="xs" c="dimmed">Moon</Text>
          <Text fw={600}>{moonPhaseLabel(data.moon_illumination)}</Text>
          <Text size="xs" c="dimmed">Nearer + brighter = worse for faint targets</Text>
        </Card>
        <Card withBorder padding="sm">
          <Text size="xs" c="dimmed">Observing from</Text>
          <Text fw={600}>
            {data.observer ? `${data.observer.lat_deg.toFixed(2)}°, ${data.observer.lon_deg.toFixed(2)}°` : "—"}
          </Text>
          <Text size="xs" c="dimmed">
            {data.location_source === "fits" ? "from your solved frames" : "from Settings"}
          </Text>
        </Card>
      </SimpleGrid>

      <Paper withBorder p="md">
        <Title order={4} mb="xs">Add more to what you're shooting</Title>
        <Text size="sm" c="dimmed" mb="sm">
          Targets already in your library that are well placed tonight — good for
          topping up integration.
        </Text>
        <TargetTable targets={already} />
      </Paper>

      <Paper withBorder p="md">
        <Title order={4} mb="xs">Start something new tonight</Title>
        <Text size="sm" c="dimmed" mb="sm">
          Bundled Messier targets you haven't shot yet, ranked by how well placed
          they are.
        </Text>
        <TargetTable targets={fresh} />
      </Paper>
    </Stack>
  );
}
