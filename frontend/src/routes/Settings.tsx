import {
  Alert, Badge, Button, Center, Divider, Group, Loader, NumberInput, Paper, Stack, Switch,
  Text, TextInput, Title,
} from "@mantine/core";
import { IconDeviceFloppy, IconInfoCircle } from "@tabler/icons-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { notifications } from "@mantine/notifications";
import { api } from "../api/client";

export function SettingsView() {
  const qc = useQueryClient();
  const settings = useQuery({ queryKey: ["settings"], queryFn: api.getSettings });
  const system = useQuery({ queryKey: ["system"], queryFn: api.getSystem });
  const [form, setForm] = useState<Record<string, unknown>>({});

  useEffect(() => {
    if (settings.data) setForm(settings.data);
  }, [settings.data]);

  const save = useMutation({
    mutationFn: (patch: Record<string, unknown>) => api.putSettings(patch),
    onSuccess: () => {
      notifications.show({ message: "Settings saved", color: "teal" });
      qc.invalidateQueries({ queryKey: ["settings"] });
      qc.invalidateQueries({ queryKey: ["system"] });
    },
  });

  if (settings.isLoading || !settings.data) {
    return (
      <Center h={300}>
        <Loader />
      </Center>
    );
  }

  const set = (k: string, v: unknown) => setForm((p) => ({ ...p, [k]: v }));
  const bool = (k: string) => Boolean(form[k]);
  const num = (k: string) => (form[k] === null || form[k] === undefined ? "" : (form[k] as number));

  return (
    <Stack maw={680}>
      <Title order={2}>Settings</Title>

      {system.data ? (
        <Alert icon={<IconInfoCircle size={16} />} color={system.data.astap.found ? "teal" : "yellow"}>
          <Group gap="lg">
            <Text size="sm">Data root: <b>{system.data.data_root}</b></Text>
            <Text size="sm">CPUs: <b>{system.data.cpu_count}</b></Text>
            <Badge color={system.data.astap.found ? "teal" : "red"}>
              ASTAP {system.data.astap.found ? "found" : "missing"}
            </Badge>
            {system.data.gpu_available ? <Badge color="violet">GPU</Badge> : null}
            {system.data.disk.free_gb ? (
              <Text size="sm">Free: <b>{system.data.disk.free_gb} GB</b></Text>
            ) : null}
          </Group>
        </Alert>
      ) : null}

      <Paper withBorder p="lg">
        <Stack>
          <Text fw={600}>Watched folders</Text>
          <TextInput label="Data root" value={(form.data_root as string) ?? ""}
            onChange={(e) => set("data_root", e.currentTarget.value)} />
          <Group grow>
            <TextInput label="Incoming dir (blank = data_root/incoming)"
              value={(form.incoming_dir as string) ?? ""}
              placeholder={settings.data.resolved_incoming_dir}
              onChange={(e) => set("incoming_dir", e.currentTarget.value)} />
            <TextInput label="Library root (blank = data_root/library)"
              value={(form.library_root as string) ?? ""}
              placeholder={settings.data.resolved_library_root}
              onChange={(e) => set("library_root", e.currentTarget.value)} />
          </Group>

          <Divider label="Watcher" />
          <Switch label="Watch for new files automatically" checked={bool("watcher_enabled")}
            onChange={(e) => set("watcher_enabled", e.currentTarget.checked)} />
          <Group grow>
            <NumberInput label="Quiet period (s) before a file is read" value={num("watch_quiet_period_s")}
              min={5} onChange={(v) => set("watch_quiet_period_s", Number(v))} />
            <NumberInput label="Poll interval (s)" value={num("watch_poll_interval_s")}
              min={2} onChange={(v) => set("watch_poll_interval_s", Number(v))} />
          </Group>

          <Divider label="Automatic pipeline" />
          <Group>
            <Switch label="Ingest" checked={bool("auto_ingest")}
              onChange={(e) => set("auto_ingest", e.currentTarget.checked)} />
            <Switch label="QC" checked={bool("auto_qc")}
              onChange={(e) => set("auto_qc", e.currentTarget.checked)} />
            <Switch label="Plate-solve" checked={bool("auto_solve")}
              onChange={(e) => set("auto_solve", e.currentTarget.checked)} />
            <Switch label="Auto-stack" checked={bool("auto_stack")}
              onChange={(e) => set("auto_stack", e.currentTarget.checked)} />
          </Group>
          <Switch label="Copy frames into local cache (use for slow/network sources)"
            checked={bool("copy_to_cache")}
            onChange={(e) => set("copy_to_cache", e.currentTarget.checked)} />

          <Divider label="Plate solving & compute" />
          <TextInput label="ASTAP path (blank = auto-detect / $SEESTACK_ASTAP_PATH)"
            value={(form.astap_path as string) ?? ""}
            onChange={(e) => set("astap_path", e.currentTarget.value || null)} />
          <Group grow>
            <NumberInput label="ASTAP FOV (deg)" value={num("astap_fov_deg")} step={0.1}
              onChange={(v) => set("astap_fov_deg", Number(v))} />
            <NumberInput label="CPU workers (blank = all cores)" value={num("cpu_workers")}
              min={1} onChange={(v) => set("cpu_workers", v === "" ? null : Number(v))} />
          </Group>

          <Group justify="flex-end">
            <Button leftSection={<IconDeviceFloppy size={16} />}
              onClick={() => save.mutate(form)} loading={save.isPending}>
              Save settings
            </Button>
          </Group>
        </Stack>
      </Paper>
    </Stack>
  );
}
