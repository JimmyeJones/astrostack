import { useMemo, useState } from "react";
import {
  Alert, Anchor, Badge, Button, Card, Center, Group, Loader, Paper, Select,
  SegmentedControl, SimpleGrid, Stack, Table, Text, TextInput, Title, Tooltip,
} from "@mantine/core";
import { IconMoon, IconStars, IconTelescope } from "@tabler/icons-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api, type PlannedTarget } from "../api/client";
import { QueryError } from "../components/QueryError";
import { formatIntegration } from "../format";
import { readinessRowHint } from "../readiness";
import {
  filterByTypeBucket, formatClock, formatMinutes, framingRowBadge, minAltOptions,
  moonCueForTarget, moonPhaseLabel, moonWindowNote, notUpTonightNote,
  partitionByUpTonight, planDateBounds, planNightLabel, scoreColor, splitTargets,
  typeFilterOptions, usableWindowNote,
} from "../tonight";

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
  // For a target already in the library, nudge toward starting something new
  // once it's close to / past its suggested integration goal ("Is it enough
  // yet?"); silent while it's still worth topping up.
  const readyHint = t.already_targeted
    ? readinessRowHint(t.total_exposure_s ?? 0, t.type)
    : null;
  // Pre-capture "will it fit?" nudge for a catalog candidate that's bigger than
  // (or as wide as) a single Seestar frame — so a beginner reaches for mosaic
  // mode before pointing. Only the too-big cases badge; "fits" stays silent.
  const framingBadge = framingRowBadge(t.framing);
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
        {readyHint ? (
          <Badge mt={4} size="xs" variant="light" color={readyHint.color}>
            {readyHint.label}
          </Badge>
        ) : null}
        {framingBadge ? (
          <Tooltip label={framingBadge.tooltip} multiline w={240} withArrow>
            <Badge mt={4} ml={readyHint ? 4 : 0} size="xs" variant="light"
              color={framingBadge.color}>
              {framingBadge.label}
            </Badge>
          </Tooltip>
        ) : null}
      </Table.Td>
      <Table.Td>{t.max_altitude_deg.toFixed(0)}°</Table.Td>
      <Table.Td>{formatClock(t.transit_utc)}</Table.Td>
      <Table.Td>
        {formatMinutes(t.minutes_above_min_alt)}
        {usableWindowNote(t.usable_start_utc, t.usable_end_utc) ? (
          <Text size="xs" c="dimmed">{usableWindowNote(t.usable_start_utc, t.usable_end_utc)}</Text>
        ) : null}
      </Table.Td>
      <Table.Td>
        {t.moon_separation_deg.toFixed(0)}°
        {moonCueForTarget(t.moon_up_fraction) ? (
          <Text size="xs" c="dimmed">{moonCueForTarget(t.moon_up_fraction)}</Text>
        ) : null}
      </Table.Td>
      <Table.Td><ScoreBadge score={t.score} /></Table.Td>
    </Table.Tr>
  );
}

// When the planner resolved the observing site from a solved frame's FITS header
// (SITELAT/SITELONG) rather than Settings, offer to save it so planning is
// instant next time and any other page that wants a site can reuse it. Purely
// additive: the auto-detect keeps working if dismissed, and we only ever offer
// when Settings has no site (location_source === "fits"), so this never
// overwrites a location the user set themselves.
function SaveLocationNudge({ lat, lon }: { lat: number; lon: number }) {
  const qc = useQueryClient();
  const [dismissed, setDismissed] = useState(false);
  const save = useMutation({
    mutationFn: () => api.putSettings({ site_lat: lat, site_lon: lon }),
    // Re-plan once saved: the next fetch resolves the site from Settings, so this
    // nudge disappears on its own (location_source flips to "settings").
    onSuccess: () => qc.invalidateQueries({ queryKey: ["tonight"] }),
  });
  if (dismissed) return null;
  return (
    <Alert
      color="blue"
      icon={<IconTelescope size={18} />}
      title="We found your observing location"
      withCloseButton
      onClose={() => setDismissed(true)}
    >
      <Text size="sm" mb="sm">
        Read from your Seestar's frames: <b>{lat.toFixed(2)}°, {lon.toFixed(2)}°</b>.
        Save it to Settings so planning is instant and other pages know where you
        observe from — the app won't have to re-read your frames each time.
      </Text>
      <Group gap="sm">
        <Button size="xs" loading={save.isPending} onClick={() => save.mutate()}>
          Save this location
        </Button>
        {save.isError ? (
          <Text size="xs" c="red">
            Couldn't save — set it under{" "}
            <Anchor component={Link} to="/settings">Settings</Anchor> instead.
          </Text>
        ) : null}
      </Group>
    </Alert>
  );
}

function TargetTable({ targets, empty }: { targets: PlannedTarget[]; empty: string }) {
  if (targets.length === 0) {
    return <Text size="sm" c="dimmed">{empty}</Text>;
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
  const [date, setDate] = useState<string>("");
  const [typeFilter, setTypeFilter] = useState<string>("All");
  const now = useMemo(() => new Date(), []);
  const bounds = useMemo(() => planDateBounds(now), [now]);
  const nightLabel = planNightLabel(date, now);
  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: ["tonight", minAlt, date],
    queryFn: () => api.getTonight({
      ...(minAlt ? { minAlt: Number(minAlt) } : {}),
      ...(date ? { date } : {}),
    }),
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
          The best deep-sky targets to point the scope at
          {nightLabel ? ` on ${nightLabel}` : " tonight"} — ranked, offline.
          {data.horizon_active
            ? " Time-up accounts for your horizon / tree mask."
            : ""}
        </Text>
      </div>
      <Group align="flex-end" gap="sm" wrap="wrap">
        <TextInput
          type="date"
          label="Night"
          value={date}
          min={bounds.min}
          max={bounds.max}
          onChange={(e) => setDate(e.currentTarget.value)}
          rightSection={date
            ? <Button variant="subtle" size="compact-xs" onClick={() => setDate("")}>Tonight</Button>
            : undefined}
          rightSectionWidth={date ? 72 : undefined}
          w={200}
        />
        <Select
          label="Minimum altitude"
          data={minAltOptions(minAlt ? Number(minAlt) : data.min_altitude_deg)}
          value={minAlt || String(data.min_altitude_deg)}
          onChange={(v) => setMinAlt(v ?? "")}
          w={180}
          allowDeselect={false}
        />
      </Group>
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
  const whenWord = nightLabel ? `on ${nightLabel}` : "tonight";
  // Show only targets actually up tonight; the rest (roughly half the catalog on
  // a typical night) collapse into a dimmed count so the ranking stays readable.
  const { up: alreadyUp, notUp: alreadyNotUp } = partitionByUpTonight(already);
  const { up: freshUp, notUp: freshNotUp } = partitionByUpTonight(fresh);
  const typeOptions = typeFilterOptions(freshUp);
  // A previously-chosen bucket may no longer be present after the data changes
  // (a different night, a min-altitude change). Fall back to "All" for *both* the
  // control's displayed value and the filtered list, so they never disagree — a
  // valid-but-absent bucket (e.g. "Nebula" with no nebulae up) would otherwise
  // filter to an empty table while the control read "All".
  const effectiveTypeFilter = typeOptions.includes(typeFilter) ? typeFilter : "All";
  const freshShown = filterByTypeBucket(freshUp, effectiveTypeFilter);
  const alreadyNote = alreadyUp.length > 0 ? notUpTonightNote(alreadyNotUp.length, whenWord) : null;
  const freshNote = freshUp.length > 0 ? notUpTonightNote(freshNotUp.length, whenWord) : null;

  return (
    <Stack gap="lg">
      {header}

      {data.location_source === "fits" && data.observer ? (
        <SaveLocationNudge lat={data.observer.lat_deg} lon={data.observer.lon_deg} />
      ) : null}

      <SimpleGrid cols={{ base: 1, sm: 3 }}>
        <Card withBorder padding="sm">
          <Text size="xs" c="dimmed">Dark window ({twilight})</Text>
          <Text fw={600}>{formatClock(dw.start_utc)} – {formatClock(dw.end_utc)}</Text>
          <Text size="xs" c="dimmed">{formatMinutes(dw.duration_minutes)} of darkness</Text>
        </Card>
        <Card withBorder padding="sm">
          <Text size="xs" c="dimmed">Moon</Text>
          <Text fw={600}>{moonPhaseLabel(data.moon_illumination, data.moon_waxing)}</Text>
          {moonWindowNote(data.moon_window) ? (
            <Text size="xs" c="dimmed">{moonWindowNote(data.moon_window)}</Text>
          ) : (
            <Text size="xs" c="dimmed">Nearer + brighter = worse for faint targets</Text>
          )}
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
          Targets already in your library that are well placed {whenWord} — good for
          topping up integration.
        </Text>
        <TargetTable
          targets={alreadyUp}
          empty={already.length === 0
            ? "You haven't shot any targets with a known position yet — start something new below."
            : `None of your targets are up ${whenWord} — lower the minimum altitude to include them.`} />
        {alreadyNote ? <Text size="xs" c="dimmed" mt="xs">{alreadyNote}</Text> : null}
      </Paper>

      <Paper withBorder p="md">
        <Group justify="space-between" align="flex-start" mb="xs" wrap="wrap">
          <Title order={4}>Start something new {whenWord}</Title>
          {typeOptions.length > 1 ? (
            <SegmentedControl
              size="xs"
              data={typeOptions}
              value={effectiveTypeFilter}
              onChange={setTypeFilter}
            />
          ) : null}
        </Group>
        <Text size="sm" c="dimmed" mb="sm">
          Popular deep-sky targets (Messier plus well-known NGC/IC objects) you
          haven't shot yet, ranked by how well placed they are.
        </Text>
        <TargetTable
          targets={freshShown}
          empty={freshShown.length === 0 && freshUp.length > 0
            ? "No targets of that type clear your minimum altitude — try another type or lower the floor."
            : `Nothing in the catalog clears your minimum altitude ${whenWord} — try lowering it above.`} />
        {freshNote ? <Text size="xs" c="dimmed" mt="xs">{freshNote}</Text> : null}
      </Paper>
    </Stack>
  );
}
