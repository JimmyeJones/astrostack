import {
  ActionIcon, Badge, Box, Button, Center, Grid, Group, Image, Loader, NumberFormatter,
  Paper, Select, Stack, Table, Text, Title, Tooltip,
} from "@mantine/core";
import {
  IconCheck, IconHistory, IconPhoto, IconStack2, IconTelescope, IconX,
} from "@tabler/icons-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { notifications } from "@mantine/notifications";
import { api, type Frame } from "../api/client";

const NUM = (v: number | null, digits = 2) =>
  v === null || v === undefined ? "—" : v.toFixed(digits);

type SortKey = "id" | "timestamp_utc" | "fwhm_px" | "star_count" | "eccentricity_median" | "sky_adu_median";

export function TargetView() {
  const { safe = "" } = useParams();
  const qc = useQueryClient();
  const [sort, setSort] = useState<SortKey>("id");
  const [order, setOrder] = useState<"asc" | "desc">("asc");
  const [selected, setSelected] = useState<number | null>(null);
  const [bayer, setBayer] = useState<string | undefined>(undefined);

  const target = useQuery({ queryKey: ["target", safe], queryFn: () => api.getTarget(safe) });
  const frames = useQuery({
    queryKey: ["frames", safe, sort, order],
    queryFn: () => api.listFrames(safe, sort, order),
  });

  const patch = useMutation({
    mutationFn: ({ id, body }: { id: number; body: Record<string, unknown> }) =>
      api.patchFrame(safe, id, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["frames", safe] });
      qc.invalidateQueries({ queryKey: ["target", safe] });
    },
  });

  const bulk = useMutation({
    mutationFn: (body: Record<string, unknown>) => api.bulkFrames(safe, body),
    onSuccess: (r) => {
      notifications.show({ message: `Updated ${r.changed} frames`, color: "violet" });
      qc.invalidateQueries({ queryKey: ["frames", safe] });
    },
  });

  const qcSolve = useMutation({
    mutationFn: () => api.qcSolve(safe),
    onSuccess: () => {
      notifications.show({ message: "QC + solve started", color: "violet" });
      qc.invalidateQueries({ queryKey: ["jobs"] });
    },
  });

  const list = frames.data ?? [];
  const selectedFrame = useMemo(
    () => list.find((f) => f.id === selected) ?? list[0],
    [list, selected],
  );

  const setSortCol = (key: SortKey) => {
    if (sort === key) setOrder(order === "asc" ? "desc" : "asc");
    else {
      setSort(key);
      setOrder("asc");
    }
  };

  if (target.isLoading) {
    return (
      <Center h={300}>
        <Loader />
      </Center>
    );
  }

  const cols: { key: SortKey; label: string }[] = [
    { key: "timestamp_utc", label: "Time (UTC)" },
    { key: "fwhm_px", label: "FWHM" },
    { key: "star_count", label: "Stars" },
    { key: "eccentricity_median", label: "Ecc." },
    { key: "sky_adu_median", label: "Sky" },
  ];

  return (
    <Stack>
      <Group justify="space-between" gap="xs">
        <Group gap="xs" style={{ minWidth: 0 }}>
          <Title order={2} style={{ wordBreak: "break-word" }}>{target.data?.name}</Title>
          <Badge variant="light" color="violet">
            {target.data?.n_frames_accepted}/{target.data?.n_frames} accepted
          </Badge>
        </Group>
        <Group gap="xs">
          <Button
            variant="default"
            leftSection={<IconTelescope size={16} />}
            onClick={() => qcSolve.mutate()}
            loading={qcSolve.isPending}
            aria-label="Re-run QC and Solve"
          >
            <Box visibleFrom="sm">Re-run QC + Solve</Box>
          </Button>
          <Button component={Link} to={`/targets/${safe}/history`} variant="default"
            leftSection={<IconHistory size={16} />} aria-label="History">
            <Box visibleFrom="sm">History</Box>
          </Button>
          <Button component={Link} to={`/targets/${safe}/stack`}
            leftSection={<IconStack2 size={16} />} aria-label="Stack">
            <Box visibleFrom="sm">Stack</Box>
          </Button>
        </Group>
      </Group>

      <Grid>
        <Grid.Col span={{ base: 12, md: 7 }}>
          <Group mb="xs">
            <Button
              size="xs" variant="light" color="red"
              onClick={() => bulk.mutate({ action: "reject_worst", metric: "fwhm_px", fraction: 0.1 })}
              loading={bulk.isPending}
            >
              Reject worst 10% (FWHM)
            </Button>
          </Group>
          <Paper withBorder>
            <Table.ScrollContainer minWidth={620} mah="65vh">
              <Table stickyHeader highlightOnHover>
                <Table.Thead>
                  <Table.Tr>
                    <Table.Th w={40}></Table.Th>
                    {cols.map((c) => (
                      <Table.Th
                        key={c.key}
                        onClick={() => setSortCol(c.key)}
                        style={{ cursor: "pointer" }}
                      >
                        {c.label}
                        {sort === c.key ? (order === "asc" ? " ▲" : " ▼") : ""}
                      </Table.Th>
                    ))}
                    <Table.Th w={50}>OK</Table.Th>
                  </Table.Tr>
                </Table.Thead>
                <Table.Tbody>
                  {list.map((f: Frame) => (
                    <Table.Tr
                      key={f.id}
                      onClick={() => setSelected(f.id)}
                      bg={selectedFrame?.id === f.id ? "var(--mantine-color-violet-light)" : undefined}
                      opacity={f.accept ? 1 : 0.45}
                      style={{ cursor: "pointer" }}
                    >
                      <Table.Td>
                        {f.solved ? (
                          <Tooltip label="Plate solved">
                            <IconTelescope size={14} color="var(--mantine-color-teal-5)" />
                          </Tooltip>
                        ) : null}
                      </Table.Td>
                      <Table.Td>{f.timestamp_utc?.replace("T", " ").slice(0, 19) ?? "—"}</Table.Td>
                      <Table.Td>{NUM(f.fwhm_px)}</Table.Td>
                      <Table.Td>{f.star_count ?? "—"}</Table.Td>
                      <Table.Td>{NUM(f.eccentricity_median)}</Table.Td>
                      <Table.Td><NumberFormatter value={f.sky_adu_median ?? 0} decimalScale={0} /></Table.Td>
                      <Table.Td>
                        <ActionIcon
                          size="sm"
                          variant={f.accept ? "filled" : "subtle"}
                          color={f.accept ? "teal" : "red"}
                          onClick={(e) => {
                            e.stopPropagation();
                            patch.mutate({ id: f.id, body: { accept: !f.accept } });
                          }}
                        >
                          {f.accept ? <IconCheck size={14} /> : <IconX size={14} />}
                        </ActionIcon>
                      </Table.Td>
                    </Table.Tr>
                  ))}
                </Table.Tbody>
              </Table>
            </Table.ScrollContainer>
          </Paper>
        </Grid.Col>

        <Grid.Col span={{ base: 12, md: 5 }}>
          <Paper withBorder p="md">
            <Group justify="space-between" mb="sm">
              <Text fw={600}>Preview</Text>
              <Select
                size="xs"
                placeholder="Bayer"
                w={110}
                data={["RGGB", "BGGR", "GRBG", "GBRG"]}
                value={bayer ?? null}
                onChange={(v) => setBayer(v ?? undefined)}
                clearable
              />
            </Group>
            {selectedFrame ? (
              <Stack gap="xs">
                <Box style={{ background: "#000", borderRadius: 8, overflow: "hidden" }}>
                  <Image
                    src={api.framePreviewUrl(safe, selectedFrame.id, 700, bayer)}
                    alt={selectedFrame.name}
                    fallbackSrc=""
                  />
                </Box>
                <Text size="sm" fw={500}>{selectedFrame.name}</Text>
                <Group gap="lg">
                  <Text size="xs" c="dimmed">FWHM {NUM(selectedFrame.fwhm_px)}</Text>
                  <Text size="xs" c="dimmed">Stars {selectedFrame.star_count ?? "—"}</Text>
                  <Text size="xs" c="dimmed">Exp {NUM(selectedFrame.exposure_s, 0)}s</Text>
                </Group>
              </Stack>
            ) : (
              <Center h={240}>
                <IconPhoto size={48} color="var(--mantine-color-dark-3)" />
              </Center>
            )}
          </Paper>
        </Grid.Col>
      </Grid>
    </Stack>
  );
}
