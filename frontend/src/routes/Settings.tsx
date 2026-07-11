import {
  Accordion, Alert, Badge, Button, Center, Divider, FileButton, Group, Loader,
  NumberInput, Paper, Select, SimpleGrid, Stack, Switch, TagsInput, Text, TextInput,
  Title,
} from "@mantine/core";
import {
  IconDeviceFloppy, IconDownload, IconInfoCircle, IconPlus, IconRefresh,
  IconTelescope, IconTrash, IconUpload,
} from "@tabler/icons-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { notifications } from "@mantine/notifications";
import { api, type AutoCastSummary, type ReprocessStatus } from "../api/client";
import { dependencyMet } from "../api/depends";
import { compassPoint } from "../tonight";
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
  auto_edit_on_autostack: "After an automatic stack, also auto-edit the master into a finished picture (the same one-click Auto processing), so an unattended run comes back to a great image, not a flat linear master. Reversible in the editor (Reset). Needs Auto-stack on.",
  auto_bind_calibration: "When a hands-off stack (auto-stack, Process target, or Reprocess everything) has no calibration masters chosen, automatically use the library's best matching master dark/flat/bias for it — so a stack you didn't set up by hand is still calibrated. Only a confident match is used (a dark whose exposure matches your subs within 25%); if nothing matches, the stack is left uncalibrated as before. The Stack form is unaffected — it always uses exactly what you pick.",
  mixed_pointing_guard: "Before a hands-off stack (auto-stack or Process target), check whether the target's solved frames actually point at one object. If they look like two different targets accidentally dropped in one folder (a mosaic never trips it), skip the stack with a message instead of silently combining only one pointing and wasting the run. Open the Frames table and reject the odd-target frames, then stack. The Stack form is unaffected — it already warns you before you stack.",
  copy_to_cache: "Copy each frame into a fast local cache before processing. Helps with slow or network-mounted sources.",
  keep_streaked_frames: "Don't auto-reject a whole frame when QC finds a satellite/plane trail — keep it (flagged) so a stack with sigma-clip or drizzle rejection removes just the streak and keeps the frame's good signal. Only turn on if you stack with rejection enabled.",
  auto_grade_frames: "After QC, automatically reject frames that are clear statistical outliers versus the rest of the target (trailed, cloud-hit or hazy subs), each with a plain-language reason. The same grading is available manually via Auto-grade on a target's page. Frames you graded yourself are never touched.",
  auto_grade_sensitivity: "How strict auto-grading is. Balanced suits most data; Conservative only drops gross outliers; Aggressive cuts deeper into marginal frames.",
  astap_path: "Path to the ASTAP executable. Blank = auto-detect (bundled binary → $SEESTACK_ASTAP_PATH → PATH).",
  astap_fov_deg: "Approximate field-of-view height in degrees, used as a solving hint (~1.3° suits the Seestar).",
  astap_timeout_s: "Give up on solving a single frame after this many seconds.",
  cpu_workers: "CPU workers for QC / solve / stack. Blank = all cores.",
  max_stack_memory_gb: "Working-memory cap for a single stack. Blank = auto (~70% of RAM). Raise it on a big box to allow larger drizzle/mosaic canvases; lower it to leave more headroom. The ASTROSTACK_MAX_STACK_GB env var, if set, overrides this.",
  job_history_limit: "How many finished jobs to keep in the Jobs history (the jobs.sqlite database retains about 10× this). Higher keeps more history at the cost of a slightly larger DB. Takes effect immediately. Default 200.",
  astap_use_solve_hints: "Use each frame's telescope target RA/Dec (from its FITS header) to localise ASTAP's search — faster, more reliable solving. Turn off if your frames lack/contain wrong coordinates.",
  seestar_enabled: "Discover and monitor Seestar telescopes on the LAN via their unofficial local API (port 4700). The container must be able to reach the scope (Station mode).",
  seestar_control_enabled: "Allow sending commands (goto / start / stop / park) to the scope. Off = monitoring only, so watching can never disturb a session.",
  seestar_scan_subnet: "CIDR to scan for scopes, e.g. 192.168.1.0/24. Blank = auto-detect from the container's network.",
  seestar_known_ips: "Pin specific Seestar IPs that auto-discovery can't reach.",
  seestar_scan_interval_s: "How often to re-scan the network for devices.",
  seestar_poll_interval_s: "How often to poll each connected scope for telemetry.",
  site_lat: "Your observing latitude in degrees (north positive). Used by the Tonight planner. Leave blank to read it automatically from a plate-solved Seestar frame.",
  site_lon: "Your observing longitude in degrees (east positive). Used by the Tonight planner. Leave blank to read it automatically from a plate-solved Seestar frame.",
  site_elevation_m: "Your elevation above sea level in metres (a small refinement to the Tonight planner; 0 is fine for most).",
  min_target_altitude_deg: "How high a target must climb to count as usable in the Tonight planner. 30° is a good default; lower it for an open horizon, raise it if trees/buildings block low altitudes.",
  horizon_profile: "Optional: map where trees, buildings or the house block your low sky, so the Tonight planner only counts a target as usable while it's actually clear of them. Each point is a compass direction (azimuth: 0°=N, 90°=E, 180°=S, 270°=W) and the minimum altitude that's unobstructed there; the planner interpolates between points. Leave empty for a flat, open horizon.",
};

type HorizonPoint = [number, number];

// Editor for the Tonight planner's horizon / tree-cover mask: a small list of
// (azimuth, min-clear-altitude) points. Empty = a flat, unobstructed horizon.
function HorizonProfileEditor(
  { value, onChange }: { value: HorizonPoint[]; onChange: (v: HorizonPoint[]) => void },
) {
  const points = Array.isArray(value) ? value : [];
  const setPoint = (i: number, j: 0 | 1, v: number) => {
    const next = points.map((p) => [...p] as HorizonPoint);
    next[i][j] = v;
    onChange(next);
  };
  const addPoint = () => onChange([...points, [0, 20]]);
  const removePoint = (i: number) => onChange(points.filter((_, k) => k !== i));

  return (
    <Stack gap="xs">
      {points.length === 0 ? (
        <Text size="xs" c="dimmed">
          No horizon mask — the planner treats the whole sky above your minimum
          altitude as open. Add points to mark where trees or buildings block it.
        </Text>
      ) : (
        points.map((p, i) => (
          <Group key={i} gap="xs" align="flex-end" wrap="nowrap">
            <NumberInput label={i === 0 ? "Azimuth (°)" : undefined} value={p[0]}
              min={0} max={360} step={5} clampBehavior="strict" w={130}
              rightSection={<Text size="xs" c="dimmed" pr={6}>{compassPoint(p[0])}</Text>}
              onChange={(v) => setPoint(i, 0, v === "" ? 0 : Number(v))} />
            <NumberInput label={i === 0 ? "Min altitude (°)" : undefined} value={p[1]}
              min={0} max={90} step={1} clampBehavior="strict" w={130}
              onChange={(v) => setPoint(i, 1, v === "" ? 0 : Number(v))} />
            <Button variant="subtle" color="red" size="compact-sm"
              leftSection={<IconTrash size={14} />} onClick={() => removePoint(i)}>
              Remove
            </Button>
          </Group>
        ))
      )}
      <Group gap="xs">
        <Button variant="light" size="compact-sm" leftSection={<IconPlus size={14} />}
          onClick={addPoint}>
          Add horizon point
        </Button>
        {points.length > 0 && (
          <Button variant="subtle" color="gray" size="compact-sm" onClick={() => onChange([])}>
            Clear mask
          </Button>
        )}
      </Group>
    </Stack>
  );
}

function BackupRestore() {
  const qc = useQueryClient();
  const restore = useMutation({
    mutationFn: (config: Record<string, unknown>) => api.importSettings(config),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["settings"] });
      notifications.show({ color: "teal", message: "Settings restored from backup." });
    },
    onError: (e: Error) =>
      notifications.show({ color: "red", title: "Restore failed", message: e.message }),
  });

  const onFile = (file: File | null) => {
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => {
      try {
        const parsed = JSON.parse(String(reader.result));
        if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) {
          throw new Error("not a settings object");
        }
        restore.mutate(parsed as Record<string, unknown>);
      } catch {
        notifications.show({
          color: "red", title: "Restore failed",
          message: "That file isn't a valid AstroStack settings backup.",
        });
      }
    };
    reader.readAsText(file);
  };

  return (
    <Paper withBorder p="lg">
      <Stack>
        <Text fw={600}>Backup &amp; restore</Text>
        <Text size="sm" c="dimmed">
          Download all your settings as a JSON file, or restore them from a
          previous backup. Passwords and machine-specific paths (data root,
          incoming/library folders, ASTAP path) are never included, so a backup
          is safe to share and restores cleanly on any install.
        </Text>
        <Group>
          <Button
            component="a"
            href={api.settingsExportUrl()}
            variant="default"
            leftSection={<IconDownload size={16} />}
          >
            Export settings
          </Button>
          <FileButton onChange={onFile} accept="application/json,.json">
            {(props) => (
              <Button
                {...props}
                variant="default"
                loading={restore.isPending}
                leftSection={<IconUpload size={16} />}
              >
                Import settings…
              </Button>
            )}
          </FileButton>
        </Group>
      </Stack>
    </Paper>
  );
}

// Proactive nudge text: after an in-place upgrade, tell the user how many targets'
// images are stale so they don't have to remember to reprocess. Null when nothing
// is outdated (or the status hasn't loaded), so no nudge is shown.
export function reprocessNudgeText(status: ReprocessStatus | undefined): string | null {
  if (!status || status.outdated <= 0) return null;
  const n = status.outdated;
  const subj = n === 1 ? "1 target was" : `${n} targets were`;
  return (
    `${subj} last stacked with an older AstroStack version than the one now `
    + `running (v${status.current_version}). Reprocess ${n === 1 ? "it" : "them"} `
    + `to apply the latest stacking improvements — it's non-destructive, so your `
    + `existing images aren't overwritten.`
  );
}

// Read-only self-check on Auto's colour path: every unattended auto-edit stamps
// its finished sky-background cast, and this turns that per-run signal into one
// plain library-wide answer — of the auto-edited results, how many landed neutral
// vs carried a residual cast, and which tint dominated when they didn't. Null
// until any auto-edited run is measured, so no line is shown on a fresh install.
export function autoCastSummaryText(summary: AutoCastSummary | undefined): string | null {
  if (!summary || summary.measured <= 0) return null;
  const { measured, neutral, cast, by_cast } = summary;
  const runs = measured === 1 ? "auto-edited result" : "auto-edited results";
  if (cast <= 0) {
    return (
      `Auto's background came out neutral on all ${measured} ${runs} so far — `
      + `its colour path is landing clean on your data.`
    );
  }
  // Name the tints that actually appeared, commonest first, so the owner sees
  // which way Auto skews when it isn't neutral.
  const tints = Object.entries(by_cast)
    .sort((a, b) => b[1] - a[1])
    .map(([name, n]) => `${n} ${name}`)
    .join(", ");
  const skew = tints ? ` (${tints})` : "";
  return (
    `Auto's background came out neutral on ${neutral} of ${measured} ${runs}; `
    + `${cast} carried a slight cast${skew}. A run or two off-neutral is normal; a `
    + `consistent tint would be worth a look at the colour steps.`
  );
}

export function Maintenance() {
  const navigate = useNavigate();
  // Default to "only outdated" — after an upgrade the user wants to reprocess just
  // the images that would actually change, not restack the whole library wholesale.
  const [staleOnly, setStaleOnly] = useState(true);
  // Off by default: the common case is a plain restack with the new engine. A deep
  // rescan (re-QC / re-solve / re-grade every frame first) is much slower and only
  // pays off when QC/solving/grading improved too, so make it an explicit opt-in.
  const [deepRescan, setDeepRescan] = useState(false);
  // Off by default: seeds an editor recipe on every restacked run at once, so it's
  // an explicit opt-in. When on, each fresh master opens as a finished picture (the
  // one-click Auto recipe) instead of a flat linear stack.
  const [autoEdit, setAutoEdit] = useState(false);
  const status = useQuery({
    queryKey: ["reprocess-status"],
    queryFn: api.reprocessStatus,
    staleTime: 60_000,
  });
  const nudge = reprocessNudgeText(status.data);
  const castSummary = useQuery({
    queryKey: ["auto-cast-summary"],
    queryFn: api.autoCastSummary,
    staleTime: 60_000,
  });
  const castText = autoCastSummaryText(castSummary.data);
  const reprocess = useMutation({
    mutationFn: (opts: { staleOnly: boolean; deepRescan: boolean; autoEdit: boolean }) =>
      api.reprocessAll(opts.staleOnly, opts.deepRescan, opts.autoEdit),
    onSuccess: (res) => {
      notifications.show({
        color: "teal",
        message: res.already_running
          ? "A reprocess-everything batch is already running — watch it on the Jobs page."
          : "Reprocessing targets — watch progress on the Jobs page.",
      });
      navigate("/jobs");
    },
    onError: (e: Error) =>
      notifications.show({ color: "red", title: "Couldn't start reprocess", message: e.message }),
  });

  const onClick = () => {
    const scope = staleOnly
      ? "Restack every target that hasn't already been stacked with the current "
        + "version?\n\n(Targets already up to date on this version are skipped.)\n\n"
      : "Restack EVERY target with the current engine?\n\n";
    const rescanNote = deepRescan
      ? "Each target's frames are also re-checked (QC), re-plate-solved and "
        + "re-graded before restacking — slower, but picks up quality/solving "
        + "improvements too. Your manual accept/reject choices are kept.\n\n"
      : "";
    const editNote = autoEdit
      ? "Each fresh result is also auto-edited (the one-click Auto look) so it "
        + "opens as a finished picture, not a flat linear stack. This only sets "
        + "the new results' edits — your existing edits are untouched, and every "
        + "auto-edit is reversible in the editor.\n\n"
      : "";
    if (
      window.confirm(
        scope
        + rescanNote
        + editNote
        + "Each target is reprocessed one at a time, reusing its last stack "
        + "settings. This is non-destructive: every restack is saved as a NEW "
        + "result alongside the existing one (nothing is deleted or overwritten), "
        + "so you can compare them in History. A large library can take a while.",
      )
    ) {
      reprocess.mutate({ staleOnly, deepRescan, autoEdit });
    }
  };

  return (
    <Paper withBorder p="lg">
      <Stack>
        <Text fw={600}>Reprocess everything</Text>
        <Text size="sm" c="dimmed">
          Restack every target with the current engine, reusing each target's last
          stack settings. Handy after an upgrade so all your final images benefit
          from the newest stacking improvements. Targets are processed one at a
          time; each restack is saved as a new result alongside the old one, so
          nothing is ever lost.
        </Text>
        {nudge && (
          <Alert
            color="grape"
            variant="light"
            icon={<IconRefresh size={16} />}
            title="Some images are out of date"
          >
            {nudge}
          </Alert>
        )}
        <Switch
          checked={staleOnly}
          onChange={(e) => setStaleOnly(e.currentTarget.checked)}
          label="Only targets not already stacked on this version"
          description="Skips targets whose latest stack was already made with the current version, so a large library isn't reprocessed wholesale."
        />
        <Switch
          checked={deepRescan}
          onChange={(e) => setDeepRescan(e.currentTarget.checked)}
          label="Also re-run QC, plate-solving & grading first"
          description="Re-checks every frame (quality, plate-solve, auto-grade) before restacking, so improvements to those steps apply too — not just the stacker. Slower, and keeps your manual accept/reject choices."
        />
        <Switch
          checked={autoEdit}
          onChange={(e) => setAutoEdit(e.currentTarget.checked)}
          label="Also auto-edit each result into a finished picture"
          description="Applies the one-click Auto look to every restacked result so it opens as a finished picture instead of a flat linear stack. Only sets the new results' edits; your existing edits are untouched and every auto-edit is reversible."
        />
        <Group>
          <Button
            color="grape"
            variant="light"
            leftSection={<IconRefresh size={16} />}
            loading={reprocess.isPending}
            onClick={onClick}
          >
            {staleOnly ? "Reprocess outdated targets…" : "Reprocess all targets…"}
          </Button>
        </Group>
        {castText && (
          <Text size="xs" c="dimmed" mt={4}>
            {castText}
          </Text>
        )}
      </Stack>
    </Paper>
  );
}

function AccessControl() {
  const qc = useQueryClient();
  const status = useQuery({ queryKey: ["auth-status"], queryFn: api.authStatus });
  const [username, setUsername] = useState("admin");
  const [password, setPassword] = useState("");

  useEffect(() => {
    if (status.data?.username) setUsername(status.data.username);
  }, [status.data?.username]);

  const enabled = status.data?.enabled ?? false;

  const setPw = useMutation({
    mutationFn: () => api.setAuthPassword({ password, username }),
    onSuccess: (r) => {
      notifications.show({
        message: r.enabled
          ? "Password set — you'll be asked to sign in on the next request."
          : "Access control disabled.",
        color: "teal",
      });
      setPassword("");
      qc.invalidateQueries({ queryKey: ["auth-status"] });
    },
    onError: (e: Error) => notifications.show({ message: e.message, color: "red" }),
  });

  const disable = useMutation({
    mutationFn: () => api.setAuthPassword({ password: "" }),
    onSuccess: () => {
      notifications.show({ message: "Access control disabled.", color: "teal" });
      qc.invalidateQueries({ queryKey: ["auth-status"] });
    },
    onError: (e: Error) => notifications.show({ message: e.message, color: "red" }),
  });

  return (
    <Paper withBorder p="lg">
      <Stack>
        <Group gap={6}>
          <Text fw={600}>Access control</Text>
          <Badge variant="light" color={enabled ? "teal" : "gray"}>
            {enabled ? "password protected" : "open"}
          </Badge>
        </Group>
        <Text size="sm" c="dimmed">
          Optionally require a username and password (HTTP Basic) to reach AstroStack.
          Leave it off on a trusted LAN; turn it on if the app is exposed beyond your
          network. Best paired with HTTPS so credentials aren't sent in the clear.
        </Text>
        <Group align="flex-end" gap="sm" wrap="wrap">
          <TextInput label="Username" value={username} w={160}
            onChange={(e) => setUsername(e.currentTarget.value)} />
          <TextInput label={enabled ? "New password" : "Password"} type="password"
            placeholder="At least 4 characters" value={password} style={{ flex: 1, minWidth: 180 }}
            onChange={(e) => setPassword(e.currentTarget.value)} />
          <Button onClick={() => setPw.mutate()} loading={setPw.isPending}
            disabled={password.length < 4}>
            {enabled ? "Update" : "Enable"}
          </Button>
          {enabled ? (
            <Button color="red" variant="light" loading={disable.isPending}
              onClick={() => {
                if (window.confirm("Disable access control? The app will be open to anyone who can reach it.")) {
                  disable.mutate();
                }
              }}>
              Disable
            </Button>
          ) : null}
        </Group>
      </Stack>
    </Paper>
  );
}

export function SettingsView() {
  const qc = useQueryClient();
  const settings = useQuery({ queryKey: ["settings"], queryFn: api.getSettings });
  const system = useQuery({ queryKey: ["system"], queryFn: api.getSystem });
  const stackSchema = useQuery({ queryKey: ["schema"], queryFn: api.optionsSchema });
  const [form, setForm] = useState<Record<string, unknown>>({});

  useEffect(() => {
    if (settings.data) setForm(settings.data);
  }, [settings.data]);

  const astapTest = useMutation({ mutationFn: () => api.astapTest() });

  const save = useMutation({
    mutationFn: (patch: Record<string, unknown>) => api.putSettings(patch),
    onSuccess: () => {
      notifications.show({ message: "Settings saved", color: "teal" });
      qc.invalidateQueries({ queryKey: ["settings"] });
      qc.invalidateQueries({ queryKey: ["system"] });
    },
    onError: (e: Error) => notifications.show({ message: `Save failed: ${e.message}`, color: "red" }),
  });

  if (settings.isError) {
    return <Alert color="red" m="md" title="Could not load settings">{(settings.error as Error)?.message}</Alert>;
  }
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
              <Group gap="xs" align="center">
                <Button size="xs" variant="light" loading={astapTest.isPending}
                  disabled={!astap.found} onClick={() => astapTest.mutate()}>
                  Test solve on a real frame
                </Button>
                {astapTest.data ? (
                  <Text size="xs" c={astapTest.data.ok ? "teal" : "red"}>
                    {astapTest.data.ok
                      ? `Solved ${astapTest.data.frame} in ${astapTest.data.elapsed_s}s`
                      : `Failed: ${astapTest.data.detail}`}
                  </Text>
                ) : null}
              </Group>
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
          <Switch label={lbl("auto_edit_on_autostack", "Auto-edit the auto-stacked master into a finished picture")}
            checked={bool("auto_edit_on_autostack")} disabled={!bool("auto_stack")}
            onChange={(e) => set("auto_edit_on_autostack", e.currentTarget.checked)} />
          <Switch label={lbl("auto_bind_calibration", "Auto-apply matching calibration masters to hands-off stacks")}
            checked={bool("auto_bind_calibration")}
            onChange={(e) => set("auto_bind_calibration", e.currentTarget.checked)} />
          <Switch label={lbl("mixed_pointing_guard", "Skip a hands-off stack when the batch looks like two different targets")}
            checked={bool("mixed_pointing_guard")}
            onChange={(e) => set("mixed_pointing_guard", e.currentTarget.checked)} />
          <Switch label={lbl("copy_to_cache", "Copy frames into local cache")}
            checked={bool("copy_to_cache")}
            onChange={(e) => set("copy_to_cache", e.currentTarget.checked)} />
          <Switch label={lbl("keep_streaked_frames", "Keep frames with satellite/plane streaks")}
            checked={bool("keep_streaked_frames")}
            onChange={(e) => set("keep_streaked_frames", e.currentTarget.checked)} />
          <Group align="flex-end">
            <Switch label={lbl("auto_grade_frames", "Auto-grade frames after QC")}
              checked={bool("auto_grade_frames")}
              onChange={(e) => set("auto_grade_frames", e.currentTarget.checked)} />
            <Select label={lbl("auto_grade_sensitivity", "Sensitivity")} size="xs" w={170}
              allowDeselect={false} disabled={!bool("auto_grade_frames")}
              data={[
                { value: "conservative", label: "Conservative" },
                { value: "balanced", label: "Balanced" },
                { value: "aggressive", label: "Aggressive" },
              ]}
              value={(form.auto_grade_sensitivity as string) ?? "balanced"}
              onChange={(v) => set("auto_grade_sensitivity", v ?? "balanced")} />
          </Group>

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
          <Switch label={lbl("astap_use_solve_hints", "Use telescope target as solve hint")}
            checked={bool("astap_use_solve_hints")}
            onChange={(e) => set("astap_use_solve_hints", e.currentTarget.checked)} />

          <Divider label="Observing site (Tonight planner)" />
          <Text size="xs" c="dimmed">
            Leave blank to read your location automatically from a plate-solved
            Seestar frame. Only needed if you want to override it.
          </Text>
          <SimpleGrid cols={{ base: 1, xs: 3 }}>
            <NumberInput label={lbl("site_lat", "Latitude (°N)")} value={num("site_lat")}
              min={-90} max={90} step={0.1} decimalScale={4} placeholder="auto from frames"
              onChange={(v) => set("site_lat", v === "" ? null : Number(v))} />
            <NumberInput label={lbl("site_lon", "Longitude (°E)")} value={num("site_lon")}
              min={-180} max={180} step={0.1} decimalScale={4} placeholder="auto from frames"
              onChange={(v) => set("site_lon", v === "" ? null : Number(v))} />
            <NumberInput label={lbl("site_elevation_m", "Elevation (m)")} value={num("site_elevation_m")}
              min={-500} max={9000} step={10}
              onChange={(v) => set("site_elevation_m", v === "" ? 0 : Number(v))} />
          </SimpleGrid>
          <NumberInput label={lbl("min_target_altitude_deg", "Minimum target altitude (°)")}
            value={num("min_target_altitude_deg")} min={0} max={80} step={5}
            allowDecimal={false} w={{ base: "100%", xs: 260 }}
            onChange={(v) => set("min_target_altitude_deg", v === "" ? 30 : Number(v))} />

          <div>
            <HintLabel label="Horizon / tree mask" hint={HINTS.horizon_profile} />
            <Text size="xs" c="dimmed" mb="xs">
              Mark where trees or buildings block your low sky so the planner only
              counts a target while it's actually clear of them. Azimuth is a compass
              bearing (0°=N, 90°=E, 180°=S, 270°=W).
            </Text>
            <HorizonProfileEditor
              value={(form.horizon_profile as HorizonPoint[]) ?? []}
              onChange={(v) => set("horizon_profile", v)} />
          </div>

          <Divider label="Stacking" />
          <NumberInput label={lbl("max_stack_memory_gb", "Stack memory budget (GB)")}
            value={num("max_stack_memory_gb")} min={0.5} max={1024} step={0.5}
            decimalScale={1} placeholder="auto (~70% of RAM)" w={{ base: "100%", xs: 260 }}
            onChange={(v) => set("max_stack_memory_gb", v === "" ? null : Number(v))} />
          {(() => {
            // Advisory only: a budget higher than the box's available RAM re-opens
            // the OOM door the guard exists to close.
            const budget = form.max_stack_memory_gb;
            const avail = system.data?.memory?.available_gb;
            if (typeof budget !== "number" || typeof avail !== "number") return null;
            if (budget <= avail) return null;
            return (
              <Alert color="orange" icon={<IconInfoCircle size={16} />}
                title="Budget is higher than this machine's available RAM">
                You set {budget} GB, but only about {avail} GB is currently
                available on this box. A stack that actually uses this much could
                still run out of memory. Consider lowering it, or leave it blank
                for the automatic ~70%-of-RAM cap.
              </Alert>
            );
          })()}
          <NumberInput label={lbl("job_history_limit", "Job history to keep")}
            value={num("job_history_limit")} min={10} max={100000} step={50}
            allowDecimal={false} w={{ base: "100%", xs: 260 }}
            onChange={(v) => set("job_history_limit", v === "" ? 200 : Number(v))} />

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
            <IconTelescope size={18} />
            <Text fw={600}>Telescope (Seestar)</Text>
            <Badge variant="light" color={bool("seestar_enabled") ? "teal" : "gray"}>
              {bool("seestar_enabled") ? "on" : "off"}
            </Badge>
          </Group>
          <Text size="sm" c="dimmed">
            Monitor Seestar scopes over the LAN (battery, temperature, stacking progress) and
            optionally control them. This uses an unofficial, firmware-dependent API — see the
            Telescope page for caveats.
          </Text>
          <Group>
            <Switch label={lbl("seestar_enabled", "Enable Seestar integration")}
              checked={bool("seestar_enabled")}
              onChange={(e) => set("seestar_enabled", e.currentTarget.checked)} />
            <Switch label={lbl("seestar_control_enabled", "Allow control commands")}
              checked={bool("seestar_control_enabled")} disabled={!bool("seestar_enabled")}
              onChange={(e) => set("seestar_control_enabled", e.currentTarget.checked)} />
          </Group>
          <TextInput label={lbl("seestar_scan_subnet", "Scan subnet (CIDR)")}
            value={(form.seestar_scan_subnet as string) ?? ""} placeholder="auto-detect"
            onChange={(e) => set("seestar_scan_subnet", e.currentTarget.value)} />
          <TagsInput label={lbl("seestar_known_ips", "Known device IPs")}
            placeholder="e.g. 192.168.1.50"
            value={(form.seestar_known_ips as string[]) ?? []}
            onChange={(v) => set("seestar_known_ips", v)} />
          <SimpleGrid cols={{ base: 1, xs: 2 }}>
            <NumberInput label={lbl("seestar_scan_interval_s", "Scan interval (s)")}
              value={num("seestar_scan_interval_s")} min={30}
              onChange={(v) => set("seestar_scan_interval_s", Number(v))} />
            <NumberInput label={lbl("seestar_poll_interval_s", "Poll interval (s)")}
              value={num("seestar_poll_interval_s")} min={2}
              onChange={(v) => set("seestar_poll_interval_s", Number(v))} />
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
                  disabled={!dependencyMet(f.depends_on, optVal)}
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
                          disabled={!dependencyMet(f.depends_on, optVal)}
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

      <Maintenance />

      <BackupRestore />

      <AccessControl />
    </Stack>
  );
}
