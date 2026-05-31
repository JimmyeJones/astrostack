import {
  Accordion, Alert, Badge, Button, Center, Divider, Group, Loader, NumberInput,
  Paper, SimpleGrid, Stack, Switch, Text, TextInput, Title,
} from "@mantine/core";
import { IconDeviceFloppy, IconInfoCircle } from "@tabler/icons-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { notifications } from "@mantine/notifications";
import { api } from "../api/client";
import { HintLabel, StackOptionControl } from "../components/StackOptionControl";

// Hover hints for every setting (shown via an info icon next to the label).
const HINTS: Record<string, string> = {
  data_root: "Root folder on the mounted dataset. Holds incoming/, library/ and state/.",
  incoming_dir: "Folder watched for new Seestar data. Blank = <data root>/incoming.",
  library_root: "Where organised per-target projects and stacks are stored. Blank = <data root>/library.",
  watcher_enabled: "Automatically detect and process new files dropped into the incoming folder.",
  watch_quiet_period_s:
    "A file must stay unchanged this many seconds before it's read, so half-copied frames arriving over SMB/NFS aren't read mid-write.",
  watch_poll_interval_s:
    "How often to re-scan the incoming folder as a safety net, for when filesystem change events aren't delivered (common on network mounts).",
  auto_ingest: "On new files: register them into the library, grouped per target.",
  auto_qc: "On new files: compute quality metrics (FWHM, star count, eccentricity, sky level).",
  auto_solve: "On new files: plate-solve with ASTAP so frames can be aligned and placed on the sky.",
  auto_stack: "On new files: also stack each touched target automatically (uses the defaults below, or a target's saved defaults).",
  copy_to_cache: "Copy each frame into a fast local cache before processing. Helps with slow or network-mounted sources.",
  astap_path: "Path to the ASTAP executable. Blank = auto-detect (bundled binary → $SEESTACK_ASTAP_PATH → PATH).",
  astap_fov_deg: "Approximate field-of-view height in degrees, used as a solving hint (~1.3° suits the Seestar).",
  astap_timeout_s: "Give up on solving a single frame after this many seconds.",
  cpu_workers: "CPU workers for QC / solve / stack. Blank = all cores.",
};

export function SettingsView() {
  const qc = useQueryClient();
  const settings = useQuery({ queryKey: ["settings"], queryFn: api.getSettings });
  const system = useQuery({ queryKey: ["system"], queryFn: api.getSystem });
  const stackSchema = useQuery({ queryKey: ["schema"], queryFn: api.optionsSchema });
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
    onError: (e: Error) => notifications.show({ message: `Save failed: ${e.message}`, color: "red" }),
  });

  if (settings.isLoading || !settings.data) {
    return <Center h={300}><Loader /></Center>;
  }

  const set = (k: string, v: unknown) => setForm((p) => ({ ...p, [k]: v }));
  const bool = (k: string) => Boolean(form[k]);
  const num = (k: string) => (form[k] === null || form[k] === undefined ? "" : (form[k] as number));
  const lbl = (k: string, label: string) => <HintLabel label={label} hint={HINTS[k]} />;

  // Auto-stack defaults (global). Per-target "Save as defaults" overrides these.
  const stackOpts = (form.default_stack_options as Record<string, unknown>) ?? {};
  const setStackOpt = (k: string, v: unknown) =>
    set("default_stack_options", { ...stackOpts, [k]: v });
  const fields = stackSchema.data ?? [];
  const simple = fields.filter((f) => f.group === "simple");
  const advanced = fields.filter((f) => f.group === "advanced");
  const optVal = (k: string) => (k in stackOpts ? stackOpts[k] : fields.find((f) => f.key === k)?.default);

  return (
    <Stack maw={680}>
      <Title order={2}>Settings</Title>

      {system.data ? (() => {
        const astap = system.data.astap;
        const solveReady = astap.found && astap.star_db_found !== false;
        return (
          <Alert icon={<IconInfoCircle size={16} />} color={solveReady ? "teal" : "yellow"}>
            <Stack gap={6}>
              <Group gap="lg">
                <Text size="sm">Data root: <b>{system.data.data_root}</b></Text>
                <Text size="sm">CPUs: <b>{system.data.cpu_count}</b></Text>
                <Badge color={astap.found ? "teal" : "red"}>
                  ASTAP {astap.found ? "found" : "missing"}
                </Badge>
                {astap.found ? (
                  <Badge color={astap.star_db_found ? "teal" : "red"}>
                    star DB {astap.star_db_found ? `${astap.star_db_count} files` : "missing"}
                  </Badge>
                ) : null}
                {system.data.gpu_available ? <Badge color="violet">GPU</Badge> : null}
                {system.data.disk.free_gb ? (
                  <Text size="sm">Free: <b>{system.data.disk.free_gb} GB</b></Text>
                ) : null}
              </Group>
              {astap.version ? <Text size="xs" c="dimmed">{astap.version}</Text> : null}
              {astap.hint ? <Text size="sm" c="yellow">{astap.hint}</Text> : null}
            </Stack>
          </Alert>
        );
      })() : null}

      <Paper withBorder p="lg">
        <Stack>
          <Text fw={600}>Watched folders</Text>
          <TextInput label={lbl("data_root", "Data root")} value={(form.data_root as string) ?? ""}
            onChange={(e) => set("data_root", e.currentTarget.value)} />
          <SimpleGrid cols={{ base: 1, xs: 2 }}>
            <TextInput label={lbl("incoming_dir", "Incoming dir")}
              value={(form.incoming_dir as string) ?? ""}
              placeholder={settings.data.resolved_incoming_dir}
              onChange={(e) => set("incoming_dir", e.currentTarget.value)} />
            <TextInput label={lbl("library_root", "Library root")}
              value={(form.library_root as string) ?? ""}
              placeholder={settings.data.resolved_library_root}
              onChange={(e) => set("library_root", e.currentTarget.value)} />
          </SimpleGrid>

          <Divider label="Watcher" />
          <Switch label={lbl("watcher_enabled", "Watch for new files automatically")}
            checked={bool("watcher_enabled")}
            onChange={(e) => set("watcher_enabled", e.currentTarget.checked)} />
          <SimpleGrid cols={{ base: 1, xs: 2 }}>
            <NumberInput label={lbl("watch_quiet_period_s", "Quiet period (s)")}
              value={num("watch_quiet_period_s")} min={5}
              onChange={(v) => set("watch_quiet_period_s", Number(v))} />
            <NumberInput label={lbl("watch_poll_interval_s", "Poll interval (s)")}
              value={num("watch_poll_interval_s")} min={2}
              onChange={(v) => set("watch_poll_interval_s", Number(v))} />
          </SimpleGrid>

          <Divider label="Automatic pipeline" />
          <Group>
            <Switch label={lbl("auto_ingest", "Ingest")} checked={bool("auto_ingest")}
              onChange={(e) => set("auto_ingest", e.currentTarget.checked)} />
            <Switch label={lbl("auto_qc", "QC")} checked={bool("auto_qc")}
              onChange={(e) => set("auto_qc", e.currentTarget.checked)} />
            <Switch label={lbl("auto_solve", "Plate-solve")} checked={bool("auto_solve")}
              onChange={(e) => set("auto_solve", e.currentTarget.checked)} />
            <Switch label={lbl("auto_stack", "Auto-stack")} checked={bool("auto_stack")}
              onChange={(e) => set("auto_stack", e.currentTarget.checked)} />
          </Group>
          <Switch label={lbl("copy_to_cache", "Copy frames into local cache")}
            checked={bool("copy_to_cache")}
            onChange={(e) => set("copy_to_cache", e.currentTarget.checked)} />

          <Divider label="Plate solving & compute" />
          <TextInput label={lbl("astap_path", "ASTAP path")}
            value={(form.astap_path as string) ?? ""}
            placeholder="auto-detect"
            onChange={(e) => set("astap_path", e.currentTarget.value || null)} />
          <SimpleGrid cols={{ base: 1, xs: 3 }}>
            <NumberInput label={lbl("astap_fov_deg", "ASTAP FOV (deg)")} value={num("astap_fov_deg")}
              step={0.1} min={0.1} onChange={(v) => set("astap_fov_deg", Number(v))} />
            <NumberInput label={lbl("astap_timeout_s", "ASTAP timeout (s)")} value={num("astap_timeout_s")}
              min={5} onChange={(v) => set("astap_timeout_s", Number(v))} />
            <NumberInput label={lbl("cpu_workers", "CPU workers")} value={num("cpu_workers")}
              min={1} onChange={(v) => set("cpu_workers", v === "" ? null : Number(v))} />
          </SimpleGrid>

          <Group justify="flex-end">
            <Button leftSection={<IconDeviceFloppy size={16} />}
              onClick={() => save.mutate(form)} loading={save.isPending}>
              Save settings
            </Button>
          </Group>
        </Stack>
      </Paper>

      <Paper withBorder p="lg">
        <Stack>
          <Group gap={6}>
            <Text fw={600}>Automated stacking defaults</Text>
            <Badge variant="light" color={bool("auto_stack") ? "teal" : "gray"}>
              {bool("auto_stack") ? "active" : "auto-stack off"}
            </Badge>
          </Group>
          <Text size="sm" c="dimmed">
            Options used when <b>Auto-stack</b> stacks a target automatically. A target's own
            “Save as defaults” (from its Stack page) takes precedence over these.
          </Text>
          {stackSchema.isLoading ? <Loader size="sm" /> : (
            <>
              {simple.map((f) => (
                <StackOptionControl
                  key={f.key} field={f} value={optVal(f.key)}
                  disabled={f.depends_on ? !optVal(f.depends_on) : false}
                  onChange={(v) => setStackOpt(f.key, v)}
                />
              ))}
              <Accordion variant="separated" mt="xs">
                <Accordion.Item value="adv">
                  <Accordion.Control>Advanced options</Accordion.Control>
                  <Accordion.Panel>
                    <Stack>
                      {advanced.map((f) => (
                        <StackOptionControl
                          key={f.key} field={f} value={optVal(f.key)}
                          disabled={f.depends_on ? !optVal(f.depends_on) : false}
                          onChange={(v) => setStackOpt(f.key, v)}
                        />
                      ))}
                    </Stack>
                  </Accordion.Panel>
                </Accordion.Item>
              </Accordion>
            </>
          )}
          <Group justify="flex-end">
            <Button variant="default" leftSection={<IconDeviceFloppy size={16} />}
              onClick={() => save.mutate(form)} loading={save.isPending}>
              Save settings
            </Button>
          </Group>
        </Stack>
      </Paper>
    </Stack>
  );
}
