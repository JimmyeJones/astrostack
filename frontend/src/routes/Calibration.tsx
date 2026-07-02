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

  const refresh = () => qc.invalidateQueries({ queryKey: ["calibration-masters"] });

  const list = masters.data ?? [];

  return (
    <Stack>
      <Title order={2}>Calibration</Title>
      <Alert icon={<IconInfoCircle size={16} />} color="violet" variant="light">
        Master <b>darks</b> remove thermal noise and hot pixels; master <b>flats</b> even
        out vignetting and dust shadows. Build them here, then pick them in the Stack form.
        Masters must match the frames' sensor size (no binning change).
      </Alert>

      <BuildForm onDone={refresh} />

      <Paper withBorder>
        {masters.isLoading ? (
          <Center h={120}><Loader /></Center>
        ) : list.length === 0 ? (
          <Center h={120}>
            <Text c="dimmed" size="sm">No masters yet — build one above.</Text>
          </Center>
        ) : (
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
        )}
      </Paper>
    </Stack>
  );
}
