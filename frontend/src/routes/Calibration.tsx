import {
  ActionIcon, Alert, Badge, Button, Center, Group, Loader, Paper, Select,
  Stack, Table, Text, TextInput, Title, Tooltip,
} from "@mantine/core";
import {
  IconFlask, IconInfoCircle, IconPlus, IconTrash,
} from "@tabler/icons-react";
import { notifications } from "@mantine/notifications";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api, type CalibrationMaster } from "../api/client";
import {
  masterCoverageLine, masterMissesTooltip, uncoveredTargetsNote,
} from "../components/calibrationCoverage";
import { IncomingCalibrationCard } from "../components/IncomingCalibrationCard";
import { HintAnchor } from "../components/HintAnchor";

const KIND_COLORS: Record<string, string> = { dark: "indigo", flat: "teal", bias: "grape" };

const NUM = (v: number | null, suffix = "") =>
  v === null || v === undefined ? "—" : `${v}${suffix}`;

function BuildForm({ onDone }: { onDone: () => void }) {
  const [kind, setKind] = useState("dark");
  const [sourceDir, setSourceDir] = useState("");
  const [name, setName] = useState("");
  const [method, setMethod] = useState("median");

  const build = useMutation({
    mutationFn: () =>
      api.buildCalibrationMaster({ kind, source_dir: sourceDir.trim(), name: name.trim(), method }),
    onSuccess: () => {
      notifications.show({ message: "Building master — watch the Jobs page", color: "violet" });
      setSourceDir("");
      setName("");
      onDone();
    },
    onError: (e: Error) => notifications.show({ message: e.message, color: "red" }),
  });

  return (
    <Paper withBorder p="md">
      <Group gap={6} mb="sm">
        <IconPlus size={16} />
        <Text fw={600}>Build a master</Text>
      </Group>
      <Group align="flex-end" gap="sm" wrap="wrap">
        <Select label="Type" w={120} value={kind} allowDeselect={false}
          onChange={(v) => setKind(v ?? "dark")}
          data={[
            { value: "dark", label: "Dark" },
            { value: "flat", label: "Flat" },
            { value: "bias", label: "Bias" },
          ]} />
        <Select label="Combine" w={140} value={method} allowDeselect={false}
          onChange={(v) => setMethod(v ?? "median")}
          data={[
            { value: "median", label: "Median" },
            { value: "sigma_mean", label: "Sigma-clip mean" },
            { value: "mean", label: "Mean" },
          ]} />
        <TextInput label="Source folder" placeholder="/data/incoming/darks"
          style={{ flex: 1, minWidth: 220 }} value={sourceDir}
          onChange={(e) => setSourceDir(e.currentTarget.value)} />
        <TextInput label="Name (optional)" placeholder="e.g. 30s gain80 −5°C" w={200}
          value={name} onChange={(e) => setName(e.currentTarget.value)} />
        <Button leftSection={<IconFlask size={16} />} loading={build.isPending}
          disabled={!sourceDir.trim()} onClick={() => build.mutate()}>
          Build
        </Button>
      </Group>
      <Text size="xs" c="dimmed" mt="xs">
        Point at a server-side folder of raw dark/flat FITS frames (e.g. a Seestar
        "Dark" folder on your NAS). The master is combined once and reused across targets.
      </Text>
    </Paper>
  );
}

export function CalibrationView() {
  const qc = useQueryClient();
  const masters = useQuery({
    queryKey: ["calibration-masters"],
    queryFn: api.listCalibrationMasters,
    refetchInterval: 4000,  // pick up newly-built masters from the job worker
  });

  const del = useMutation({
    mutationFn: (id: number) => api.deleteCalibrationMaster(id),
    onSuccess: () => {
      notifications.show({ message: "Master deleted", color: "teal" });
      qc.invalidateQueries({ queryKey: ["calibration-masters"] });
    },
    onError: (e: Error) => notifications.show({ message: e.message, color: "red" }),
  });

  // "Do my masters actually cover my targets?" — read-only, and deliberately its
  // own query so a slow walk over every target's frames never holds up the master
  // list. It walks project SQLite, so it's polled far more gently than the list.
  const coverage = useQuery({
    queryKey: ["calibration-coverage"],
    queryFn: api.calibrationCoverage,
    refetchInterval: 60_000,
  });

  // "Does my camera have broken pixels?" — a census of each dark/bias master's
  // hot and stuck-dark photosites. Its own query for the same reason as
  // coverage: it opens every pedestal master's FITS, so a slow read must not
  // hold up the list. The server caches per file, so the poll is cheap after the
  // first answer; a master file never changes once written.
  const defects = useQuery({
    queryKey: ["calibration-defects"],
    queryFn: api.calibrationDefects,
    refetchInterval: 60_000,
  });

  const refresh = () => {
    qc.invalidateQueries({ queryKey: ["calibration-masters"] });
    qc.invalidateQueries({ queryKey: ["calibration-coverage"] });
    qc.invalidateQueries({ queryKey: ["calibration-defects"] });
  };

  const list = masters.data ?? [];
  const nTargets = coverage.data?.n_targets ?? 0;
  const coverageById = new Map(
    (coverage.data?.masters ?? []).map((m) => [m.id, m]),
  );
  const defectsById = new Map(
    (defects.data?.masters ?? []).map((m) => [m.id, m]),
  );
  const uncovered = coverage.data ? uncoveredTargetsNote(coverage.data) : null;
  const repair = defects.data?.repair ?? null;

  // The census's own button. It writes the Stack form's "Repair hot/dead pixels
  // from the dark" switch into the *global* stack defaults, so it reaches the
  // hands-off chain too — the path that has no form to tick. The server does the
  // read-modify-write, so this can't clobber another default.
  const setRepair = useMutation({
    mutationFn: (enabled: boolean) => api.setDefectRepair(enabled),
    onSuccess: (r) => {
      notifications.show({
        color: r.enabled ? "teal" : "gray",
        message: r.enabled
          ? "Broken pixels will be repaired on every stack from now on. "
            + "Re-stack a target to apply it to a finished picture."
          : "Broken-pixel repair turned off for future stacks.",
      });
      qc.invalidateQueries({ queryKey: ["calibration-defects"] });
    },
    onError: (e: Error) => notifications.show({ message: e.message, color: "red" }),
  });

  return (
    <Stack>
      <Title order={2}>Calibration</Title>
      <Alert icon={<IconInfoCircle size={16} />} color="violet" variant="light">
        Master <b>darks</b> remove thermal noise and hot pixels; master <b>flats</b> even
        out vignetting and dust shadows. Build them here, then pick them in the Stack form.
        Masters must match the frames' sensor size (no binning change).
      </Alert>

      {/* The gap that actually costs picture quality: a target no master reaches.
          Self-hiding — nothing is said when everything is covered. */}
      {uncovered ? (
        <Alert icon={<IconInfoCircle size={16} />} color="yellow" variant="light">
          {uncovered}
        </Alert>
      ) : null}

      {/* "You already have darks" — calibration frames the app found in
          incoming/, offered before the form that asks you to type a path.
          Self-hiding: renders nothing unless the frames themselves declared a
          calibration kind and no master covers them yet. */}
      <IncomingCalibrationCard onBuilt={refresh} />

      <BuildForm onDone={refresh} />

      <Paper withBorder>
        {masters.isLoading ? (
          <Center h={120}><Loader /></Center>
        ) : list.length === 0 ? (
          <Center h={120}>
            <Text c="dimmed" size="sm">No masters yet — build one above.</Text>
          </Center>
        ) : (
          <>
            {/* The action beside the measurement. The rows below say how many
                photosites are broken; without this the only way to act on that
                is to find a named checkbox inside the Stack form's advanced
                group — once per stack, and never at all on the hands-off path.
                Self-hiding: absent unless some master reports defects a repair
                could actually fix, so a clean sensor and a refused map both
                show nothing. Inside the masters card rather than as another
                page-level banner (AGENTS.md §1, the standing IA rule). */}
            {repair ? (
              <Group justify="space-between" gap="sm" wrap="nowrap" p="sm">
                <HintAnchor label={repair.detail} multiline w={320}>
                  <Text size="sm" c={repair.state === "on" ? "teal.7" : undefined}>
                    {repair.message}
                  </Text>
                </HintAnchor>
                <Button size="xs" variant={repair.state === "on" ? "subtle" : "light"}
                  color={repair.state === "on" ? "gray" : "teal"}
                  loading={setRepair.isPending}
                  onClick={() => setRepair.mutate(repair.state !== "on")}>
                  {repair.action}
                </Button>
              </Group>
            ) : null}
            <Table.ScrollContainer minWidth={680}>
            <Table highlightOnHover>
              <Table.Thead>
                <Table.Tr>
                  <Table.Th>Name</Table.Th>
                  <Table.Th>Type</Table.Th>
                  <Table.Th>Frames</Table.Th>
                  <Table.Th>Exp</Table.Th>
                  <Table.Th>Gain</Table.Th>
                  <Table.Th>Temp</Table.Th>
                  <Table.Th>Size</Table.Th>
                  <Table.Th w={50}></Table.Th>
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {list.map((m: CalibrationMaster) => (
                  <Table.Tr key={m.id} opacity={m.exists ? 1 : 0.5}>
                    <Table.Td>
                      <Text size="sm">{m.name}</Text>
                      {!m.exists ? (
                        <Badge size="xs" color="red" variant="light">file missing</Badge>
                      ) : null}
                      {/* Do these frames say they're the kind of frame this
                          master claims to be? The build takes a folder path and
                          a dropdown, and nothing else checks the two agree — so
                          a folder of subs silently becomes a "master dark".
                          Self-hiding: null when no frame carried an IMAGETYP we
                          recognise, and on every master built before v0.356.0. */}
                      {m.header_note ? (
                        <Text size="xs"
                          c={m.header_note.severity === "warn" ? "yellow.7" : "dimmed"}>
                          {m.header_note.message}
                        </Text>
                      ) : null}
                      {/* Which of the user's targets this master can actually be
                          applied to — the question the page otherwise makes them
                          answer one target at a time. */}
                      {(() => {
                        const row = coverageById.get(m.id);
                        if (!row) return null;
                        const line = masterCoverageLine(row, nTargets);
                        if (!line) return null;
                        const misses = masterMissesTooltip(row, nTargets);
                        const text = (
                          <Text size="xs" c={row.n_covered === 0 ? "yellow.7" : "dimmed"}>
                            {line}
                          </Text>
                        );
                        return misses ? (
                          // `pre-line` so the per-target reasons stay one to a
                          // line instead of running together into a paragraph.
                          <Tooltip label={misses} multiline w={300}
                            styles={{ tooltip: { whiteSpace: "pre-line" } }}>
                            {text}
                          </Tooltip>
                        ) : text;
                      })()}
                      {/* What this master says about the *sensor*: how many
                          photosites are hot or stuck dark, and the one switch
                          that repairs exactly those. Self-hiding three ways —
                          only pedestal masters (dark/bias) are censused at all,
                          a master that couldn't be read has no row, and a clean
                          sensor gets no note (there is nothing to act on). */}
                      {(() => {
                        const note = defectsById.get(m.id)?.note;
                        if (!note) return null;
                        return (
                          <HintAnchor label={note.detail} multiline w={320}>
                            <Text size="xs"
                              c={note.severity === "warn" ? "yellow.7" : "dimmed"}>
                              {note.message}
                            </Text>
                          </HintAnchor>
                        );
                      })()}
                    </Table.Td>
                    <Table.Td>
                      <Badge color={KIND_COLORS[m.kind] ?? "gray"} variant="light">{m.kind}</Badge>
                    </Table.Td>
                    <Table.Td>{m.n_frames}</Table.Td>
                    <Table.Td>{NUM(m.exposure_s, "s")}</Table.Td>
                    <Table.Td>{NUM(m.gain)}</Table.Td>
                    <Table.Td>{NUM(m.sensor_temp_c, "°C")}</Table.Td>
                    <Table.Td>{m.width_px}×{m.height_px}</Table.Td>
                    <Table.Td>
                      <Tooltip label="Delete master">
                        <ActionIcon color="red" variant="subtle" loading={del.isPending}
                          aria-label={`Delete master ${m.name}`}
                          onClick={() => {
                            if (window.confirm(`Delete master "${m.name}"?`)) del.mutate(m.id);
                          }}>
                          <IconTrash size={16} />
                        </ActionIcon>
                      </Tooltip>
                    </Table.Td>
                  </Table.Tr>
                ))}
              </Table.Tbody>
            </Table>
            </Table.ScrollContainer>
          </>
        )}
      </Paper>
    </Stack>
  );
}
