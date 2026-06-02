import {
  Alert, Badge, Button, Card, Center, Group, Loader, NumberInput, Paper, Progress,
  RingProgress, SimpleGrid, Stack, Text, TextInput, Title,
} from "@mantine/core";
import {
  IconAlertTriangle, IconBattery2, IconPlayerStop, IconPlugConnected,
  IconPlugConnectedX, IconRadar2, IconTelescope, IconTemperature,
} from "@tabler/icons-react";
import { notifications } from "@mantine/notifications";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api, type SeestarDevice } from "../api/client";

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <Text size="xs" c="dimmed">{label}</Text>
      <Text fw={600}>{value}</Text>
    </div>
  );
}

function DeviceCard({ dev, controlEnabled }: { dev: SeestarDevice; controlEnabled: boolean }) {
  const qc = useQueryClient();
  const t = dev.telemetry;
  const [ra, setRa] = useState<number | string>("");
  const [dec, setDec] = useState<number | string>("");
  const [name, setName] = useState("");

  const invalidate = () => qc.invalidateQueries({ queryKey: ["seestar"] });
  const onErr = (e: Error) => notifications.show({ message: e.message, color: "red" });

  const connect = useMutation({
    mutationFn: async () => {
      if (dev.connected) await api.seestarDisconnect(dev.ip);
      else await api.seestarConnect(dev.ip);
    },
    onSuccess: invalidate, onError: onErr,
  });
  const goto = useMutation({
    mutationFn: () => api.seestarGoto(dev.ip, {
      ra_hours: Number(ra), dec_deg: Number(dec), target_name: name || "AstroStack",
    }),
    onSuccess: () => { notifications.show({ message: "Goto sent", color: "teal" }); invalidate(); },
    onError: onErr,
  });
  const stop = useMutation({
    mutationFn: () => api.seestarStop(dev.ip),
    onSuccess: () => notifications.show({ message: "Stop sent", color: "teal" }), onError: onErr,
  });
  const park = useMutation({
    mutationFn: () => api.seestarPark(dev.ip),
    onSuccess: () => notifications.show({ message: "Park sent", color: "teal" }), onError: onErr,
  });

  const battery = t?.battery_pct ?? null;
  const batteryColor = battery == null ? "gray" : battery < 20 ? "red" : battery < 50 ? "yellow" : "teal";
  const storage = t?.free_storage_mb != null && t?.total_storage_mb
    ? `${(t.free_storage_mb / 1024).toFixed(1)} / ${(t.total_storage_mb / 1024).toFixed(1)} GB`
    : "—";

  return (
    <Card withBorder padding="lg" radius="md">
      <Group justify="space-between" wrap="nowrap">
        <Group gap="sm" wrap="nowrap" style={{ minWidth: 0 }}>
          <IconTelescope size={28} color="var(--mantine-color-violet-4)" />
          <div style={{ minWidth: 0 }}>
            <Text fw={700} lineClamp={1}>{dev.device_name || dev.model || dev.ip}</Text>
            <Text size="xs" c="dimmed">{dev.ip}{dev.firmware ? ` · fw ${dev.firmware}` : ""}</Text>
          </div>
        </Group>
        <Group gap="xs" wrap="nowrap">
          <Badge color={dev.connected ? "teal" : dev.reachable ? "yellow" : "gray"}>
            {dev.connected ? "connected" : dev.reachable ? "reachable" : "offline"}
          </Badge>
          <Button size="xs" variant="light" loading={connect.isPending}
            color={dev.connected ? "gray" : "violet"}
            leftSection={dev.connected ? <IconPlugConnectedX size={14} /> : <IconPlugConnected size={14} />}
            onClick={() => connect.mutate()}>
            {dev.connected ? "Disconnect" : "Connect"}
          </Button>
        </Group>
      </Group>

      {dev.error ? (
        <Alert mt="sm" color="red" icon={<IconAlertTriangle size={16} />} py={6}>
          <Text size="xs">{dev.error}</Text>
        </Alert>
      ) : null}

      {t ? (
        <>
          <Group mt="md" gap="xl" wrap="nowrap">
            <RingProgress size={84} thickness={9}
              sections={[{ value: battery ?? 0, color: batteryColor }]}
              label={
                <Center>
                  <Stack gap={0} align="center">
                    <IconBattery2 size={18} />
                    <Text size="xs" fw={700}>{battery != null ? `${battery}%` : "—"}</Text>
                  </Stack>
                </Center>
              } />
            <SimpleGrid cols={2} spacing="md" verticalSpacing={6} style={{ flex: 1 }}>
              <Metric label="Charging" value={t.charging ? (t.charger_status || "yes") : "no"} />
              <Group gap={4}><IconTemperature size={14} />
                <Metric label="Temp" value={t.temp_c != null ? `${t.temp_c}°C` : "—"} /></Group>
              <Metric label="Storage free" value={storage} />
              <Metric label="Mode" value={t.mode || t.state || "idle"} />
            </SimpleGrid>
          </Group>

          {t.target_name || t.stacked_frames != null ? (
            <Paper withBorder mt="md" p="sm" radius="md">
              <Group justify="space-between">
                <Text size="sm" fw={600}>{t.target_name || "—"}</Text>
                <Badge variant="light" color="violet">{t.stage || "—"}</Badge>
              </Group>
              <Group gap="lg" mt={4}>
                <Text size="sm">Stacked: <b>{t.stacked_frames ?? "—"}</b></Text>
                {t.dropped_frames != null ? (
                  <Text size="sm" c="dimmed">dropped {t.dropped_frames}</Text>
                ) : null}
                {t.ra_hours != null && t.dec_deg != null ? (
                  <Text size="sm" c="dimmed">
                    RA {t.ra_hours.toFixed(3)}h · Dec {t.dec_deg.toFixed(2)}°
                  </Text>
                ) : null}
              </Group>
              {t.stacked_frames != null ? (
                <Progress mt={6} value={Math.min(100, (t.stacked_frames % 100))} color="violet" size="sm" />
              ) : null}
            </Paper>
          ) : null}
        </>
      ) : dev.connected ? (
        <Group mt="md" gap="xs"><Loader size="xs" /><Text size="sm" c="dimmed">Waiting for telemetry…</Text></Group>
      ) : (
        <Text mt="md" size="sm" c="dimmed">Connect to view live telemetry.</Text>
      )}

      {controlEnabled && dev.connected ? (
        <Paper withBorder mt="md" p="sm" radius="md">
          <Text size="sm" fw={600} mb={6}>Control</Text>
          <Group align="flex-end" gap="xs">
            <NumberInput size="xs" w={96} label="RA (h)" value={ra} onChange={setRa}
              step={0.1} decimalScale={4} />
            <NumberInput size="xs" w={96} label="Dec (°)" value={dec} onChange={setDec}
              step={0.1} decimalScale={3} />
            <TextInput size="xs" w={120} label="Name" value={name}
              onChange={(e) => setName(e.currentTarget.value)} placeholder="optional" />
            <Button size="xs" loading={goto.isPending}
              disabled={ra === "" || dec === ""}
              onClick={() => { if (window.confirm("Slew the scope and start imaging this target?")) goto.mutate(); }}>
              Goto &amp; image
            </Button>
            <Button size="xs" variant="light" color="orange" loading={stop.isPending}
              leftSection={<IconPlayerStop size={14} />} onClick={() => stop.mutate()}>
              Stop
            </Button>
            <Button size="xs" variant="subtle" color="red" loading={park.isPending}
              onClick={() => { if (window.confirm("Park the telescope?")) park.mutate(); }}>
              Park
            </Button>
          </Group>
        </Paper>
      ) : null}
    </Card>
  );
}

export function SeestarView() {
  const qc = useQueryClient();
  const { data, isLoading } = useQuery({
    queryKey: ["seestar"], queryFn: api.getSeestarDevices, refetchInterval: 3000,
  });

  const scan = useMutation({
    mutationFn: api.seestarScan,
    onSuccess: () => {
      notifications.show({ message: "Scanning the network for Seestars…", color: "violet" });
      qc.invalidateQueries({ queryKey: ["seestar"] });
    },
    onError: (e: Error) => notifications.show({ message: e.message, color: "red" }),
  });

  if (isLoading || !data) {
    return <Center h={300}><Loader /></Center>;
  }

  return (
    <Stack maw={900}>
      <Group justify="space-between">
        <Title order={2}>Telescope</Title>
        {data.enabled ? (
          <Button variant="light" leftSection={<IconRadar2 size={16} />}
            loading={scan.isPending} onClick={() => scan.mutate()}>
            Scan network
          </Button>
        ) : null}
      </Group>

      {!data.enabled ? (
        <Alert color="yellow" icon={<IconAlertTriangle size={16} />}>
          <Text size="sm">
            Seestar integration is off. Enable it under <b>Settings → Telescope</b>. The container
            must be able to reach your Seestar on the LAN (the scope must be in <b>Station mode</b>,
            joined to your network).
          </Text>
        </Alert>
      ) : (
        <>
          <Alert color="gray" icon={<IconAlertTriangle size={16} />} py={8}>
            <Text size="xs">
              This uses Seestar's unofficial local API; it depends on the scope's firmware and may
              break across updates. {data.control_enabled
                ? "Control is enabled — commands here can interrupt an in-progress session."
                : "Control is disabled (monitoring only). Enable it in Settings to send commands."}
            </Text>
          </Alert>
          {data.devices.length === 0 ? (
            <Card withBorder padding="xl">
              <Stack align="center" gap="sm">
                <IconTelescope size={40} color="var(--mantine-color-dark-3)" />
                <Text c="dimmed">No Seestars found yet.</Text>
                <Text c="dimmed" size="sm">
                  Make sure the scope is on and in Station mode, then click “Scan network”.
                  You can also pin its IP under Settings → Telescope.
                </Text>
              </Stack>
            </Card>
          ) : (
            <SimpleGrid cols={{ base: 1, lg: 2 }}>
              {data.devices.map((dev) => (
                <DeviceCard key={dev.id} dev={dev} controlEnabled={data.control_enabled} />
              ))}
            </SimpleGrid>
          )}
        </>
      )}
    </Stack>
  );
}
