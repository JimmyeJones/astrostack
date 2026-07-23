import {
  ActionIcon, Alert, Anchor, Badge, Button, Center, Group, Loader, Paper, Progress, Stack, Switch,
  Text, Title, Tooltip,
} from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { IconActivity, IconDownload, IconFlask, IconPhoto, IconX } from "@tabler/icons-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { type ReactNode, useRef, useState } from "react";
import { api, type Job } from "../api/client";
import { QueryError } from "../components/QueryError";
import { StackNoiseBadge } from "../components/StackNoiseBadge";
import { thinStackWarning, type ThinStackWarning } from "../components/target/thinStack";
import { rejectionNote } from "../components/target/rejectionNote";
import { type EtaSample, etaLabel, updateEtaAnchor } from "../jobEta";
import {
  isJobNotifyEnabled, notificationsSupported, requestNotificationPermission,
  setJobNotifyEnabled,
} from "../jobNotify";

const COLOR: Record<string, string> = {
  running: "violet",
  queued: "gray",
  done: "teal",
  error: "red",
  cancelled: "orange",
  interrupted: "orange",
};

// Plain-language names for the engine's internal job kinds. The backend submits
// jobs under snake_case identifiers (webapp/pipeline.py) — `pipeline`, `qc_solve`,
// `editor_png` … — which mean nothing to a Seestar beginner, and Jobs is the very
// first screen a new user lands on (clicking "Scan incoming" navigates here). Every
// other screen already translates engine jargon (History's combineMethodLabel,
// Target's rejectReasonLabel); this brings Jobs into line. Unknown kinds fall back
// to the raw identifier so a future job type is still shown, just untranslated.
const KIND_LABEL: Record<string, string> = {
  pipeline: "Importing & processing new frames",
  qc_solve: "Quality check & plate-solve",
  process_target: "Processing target (check, solve & stack)",
  stack: "Stacking",
  reprocess_all: "Reprocessing all targets",
  editor_png: "Rendering full-resolution PNG",
  editor_export: "Exporting edited image",
  editor_batch: "Batch export",
  build_master: "Building calibration master",
  channel_combine: "Channel combine",
};

/** Human-readable name for an engine job kind (pure, tested). */
export function jobKindLabel(kind: string): string {
  return KIND_LABEL[kind] ?? kind;
}

// Plain-language text for each *known fatal* failure category. Keyed by the stable
// canonical `error_kind` the backend now stamps on a failed job (webapp/jobs.py),
// so a beginner sees a sentence + next step instead of a bare Python exception like
// `MemoryError: stack output canvas 8000×6000 …` or `ValueError: no accepted,
// plate-solved frames to stack`.
const JOB_ERROR_KIND: Record<string, { message: string; next?: string }> = {
  // Stack refused *before running* because the output canvas would exceed the
  // memory budget (the OOM guard in stacker.py, raised as MemoryError).
  memory_budget: {
    message:
      "This stack needs more memory than the budget allows, so it was refused "
      + "before running rather than risk crashing the app.",
    next:
      "Lower the drizzle scale, set Canvas mode to “reference”, reject off-target "
      + "frames, or raise the memory limit in Settings, then stack again.",
  },
  // Nothing accepted + plate-solved to stack.
  no_solved_frames: {
    message: "There are no accepted, plate-solved frames to stack yet.",
    next:
      "Run Quality check & plate-solve first, and make sure at least one accepted "
      + "frame solved successfully.",
  },
  // Alignment produced nothing usable (non-overlapping / different fields).
  no_alignment: {
    message: "None of the frames could be aligned into a stack.",
    next:
      "This usually means the frames don’t overlap or solved to different fields — "
      + "check they’re all the same target, then re-run plate-solve and stack again.",
  },
  // Reference frame has no usable WCS to align the others against.
  no_reference_wcs: {
    message: "The reference frame isn’t plate-solved, so the stack has nothing to align to.",
    next: "Re-run Quality check & plate-solve, then stack again.",
  },
  // A "Build master" job was pointed at a folder with no FITS frames.
  no_fits_in_folder: {
    message: "No FITS frames were found in that folder.",
    next:
      "Point it at the folder that holds your calibration frames (the .fits darks, "
      + "flats or bias subs) and build the master again.",
  },
};

// Translate a failed job into a plain sentence + next step. Prefer the backend's
// stable `error_kind` (reword-proof, classified server-side where the exception
// *type* is known); fall back to matching the raw `error` string for an older
// backend that doesn't stamp the field. Anything unrecognised falls through to the
// raw text verbatim so no information is ever hidden.
export function friendlyJobError(
  raw: string, kind?: string | null,
): { message: string; next?: string } {
  if (kind && JOB_ERROR_KIND[kind]) return JOB_ERROR_KIND[kind];
  const s = raw.toLowerCase();
  if (s.includes("memoryerror") || s.includes("working memory")) {
    return JOB_ERROR_KIND.memory_budget;
  }
  if (s.includes("plate-solve") || s.includes("plate solved")
      || s.includes("plate-solved")) {
    return JOB_ERROR_KIND.no_solved_frames;
  }
  if (s.includes("no frames could be aligned") || s.includes("no usable frames")
      || s.includes("did not intersect the canvas")
      || s.includes("produced no usable frames")) {
    return JOB_ERROR_KIND.no_alignment;
  }
  if (s.includes("missing wcs") || s.includes("wcs could not be parsed")
      || s.includes("reference wcs")) {
    return JOB_ERROR_KIND.no_reference_wcs;
  }
  if (s.includes("no fits files found")) {
    return JOB_ERROR_KIND.no_fits_in_folder;
  }
  return { message: raw };
}

/** Plain-language outcome of a finished reprocess-all batch (pure, tested). */
export function reprocessSummary(r: Record<string, unknown>): {
  line: string; failed: string[];
} {
  const total = Number(r.total ?? 0);
  const stacked = Number(r.stacked ?? 0);
  const skipped = Number(r.skipped ?? 0);
  const rescanned = Number(r.rescanned ?? 0);
  const autoEdited = Number(r.auto_edited ?? 0);
  const failedArr = Array.isArray(r.failed) ? r.failed : [];
  const failed = failedArr
    .map((f) => (f && typeof f === "object"
      ? String((f as Record<string, unknown>).target ?? "") : ""))
    .filter(Boolean);
  let line = `Restacked ${stacked}/${total} target${total === 1 ? "" : "s"}`;
  if (r.cancelled) line += " (cancelled early)";
  // Only present when the deep-rescan option was used (re-ran QC/solve/grade first).
  if (rescanned > 0) line += ` — re-ran QC/solve/grade on ${rescanned}`;
  // Only present when the auto-edit option was used (finished pictures, not linear).
  if (autoEdited > 0) line += ` — auto-edited ${autoEdited}`;
  if (skipped > 0) line += ` — ${skipped} already up to date`;
  if (failed.length) line += ` — ${failed.length} failed`;
  return { line: `${line}.`, failed };
}

/** Plain-language outcome of a finished one-click "Process target" job (pure,
 * tested). Mirrors `reprocessSummary` for the single-target chain: says whether a
 * master was produced and, when it wasn't, why — so the user isn't left with a
 * bare "done" and no idea where the result is (or why there isn't one). */
export function processTargetSummary(r: Record<string, unknown>): {
  line: string; stacked: boolean; thin: ThinStackWarning | null;
  cleaned: string | null;
} {
  const stacked = Boolean(r.stacked);
  const solved = Number(r.solved_accepted ?? 0);
  const graded = Number(r.auto_graded ?? 0);
  if (stacked) {
    const stack = r.stack && typeof r.stack === "object"
      ? (r.stack as Record<string, unknown>) : {};
    const used = Number(stack.n_frames_used ?? 0) || solved;
    let line = `Stacked ${used} frame${used === 1 ? "" : "s"} into a new master`;
    if (graded > 0) line += ` (auto-grade dropped ${graded})`;
    // A thin auto-stack (≤4 combined frames) is the owner's "gibberish" case:
    // the Jobs page would otherwise cheerfully report a green "Stacked 1 frame"
    // with a View-result link and no hint the picture is just noise. Surface the
    // same honest heads-up the Target page shows, right where the result lands.
    const thin = thinStackWarning(used);
    // Name the invisible outlier-rejection clean-up (e.g. the lone satellite/
    // plane trail a small walk-away auto-stack removed with min/max) — the honest
    // counterpart to "some frames were left out". Omit it on a thin stack, where
    // the "this is basically one noisy sub" warning is the message that matters.
    const cleaned = thin ? null : rejectionNote(
      typeof stack.rejection_mode === "string" ? stack.rejection_mode : null,
      typeof stack.rejection_fraction === "number" ? stack.rejection_fraction : null,
      Number(stack.n_frames_used ?? 0) || null,
    );
    return { line: `${line}.`, stacked, thin, cleaned };
  }
  const reason = typeof r.stack_skipped_reason === "string"
    ? r.stack_skipped_reason : null;
  let line: string;
  if (reason === "cancelled") {
    line = "Cancelled before stacking.";
  } else if (reason === "no_solved_frames") {
    line = "Checked and solved, but no frames could be plate-solved yet — "
      + "so there was nothing to stack.";
  } else {
    line = "Finished, but no stack was produced.";
  }
  return { line, stacked, thin: null, cleaned: null };
}

/** Plain-language outcome of a finished "Build master" job (pure, tested). A
 * beginner building a master from a Dark/Flat folder should see how many of
 * their frames were actually combined — and, when some were set aside (wrong
 * size / unreadable), how many and why — rather than a bare "done" hiding a
 * silently smaller master. */
export function buildMasterSummary(r: Record<string, unknown>): string {
  const kind = typeof r.kind === "string" && r.kind ? r.kind : "master";
  const n = Number(r.n_frames ?? 0) || 0;
  const skipped = Number(r.n_skipped ?? 0) || 0;
  let line = `Built a master ${kind} from ${n} frame${n === 1 ? "" : "s"}`;
  if (skipped > 0) {
    const buckets = r.skipped_buckets && typeof r.skipped_buckets === "object"
      ? (r.skipped_buckets as Record<string, unknown>) : {};
    const parts = Object.entries(buckets)
      .filter(([, c]) => (Number(c) || 0) > 0)
      .map(([reason, c]) => `${Number(c)} ${reason}`);
    const detail = parts.length ? ` (${parts.join(", ")})` : "";
    line += ` · ${skipped} frame${skipped === 1 ? "" : "s"} set aside${detail}`;
  }
  return `${line}.`;
}

/** Result-specific actions for finished editor jobs (download / view). */
function JobResultActions({ job }: { job: Job }) {
  if (job.state !== "done" || !job.result) return null;
  const r = job.result as Record<string, unknown>;
  if (job.kind === "process_target") {
    const { line, stacked, thin, cleaned } = processTargetSummary(r);
    // Deep-link straight to the finished run's editor when we know its id
    // (v0.85.3+ backend); fall back to the target's History on an older backend.
    const stack = r.stack && typeof r.stack === "object"
      ? (r.stack as Record<string, unknown>) : {};
    const runId = stacked && typeof stack.run_id === "number" ? stack.run_id : null;
    const to = !job.target
      ? null
      : !stacked
        ? `/targets/${job.target}`
        : runId != null
          ? `/targets/${job.target}/edit/${runId}`
          : `/targets/${job.target}/history`;
    return (
      <Stack gap={4} mt="xs">
        <Text size="sm">{line}</Text>
        {thin ? (
          <Alert color={thin.level === "single" ? "orange" : "yellow"} p="xs"
            title="Very few frames stacked">
            <Text size="xs">{thin.message}</Text>
          </Alert>
        ) : null}
        {/* The honest "we quietly removed the trails" trust cue — self-omits on a
            thin stack (warning wins) and when no rejection pass cleaned anything. */}
        {cleaned ? (
          <Text size="xs" c="dimmed">{cleaned}</Text>
        ) : null}
        {/* The satisfying "stacking cut your noise ~N×" payoff, right where the
            finished picture lands (self-omits for a thin stack — small ratio). */}
        {job.target && stacked && runId != null ? (
          <StackNoiseBadge safe={job.target} runId={runId}
            nFrames={Number(stack.n_frames_used ?? 0) || null} />
        ) : null}
        {to ? (
          <Group>
            <Button size="xs" variant="light" leftSection={<IconPhoto size={14} />}
              component={Link} to={to}>
              {stacked ? "View result" : "Open target"}
            </Button>
          </Group>
        ) : null}
      </Stack>
    );
  }
  if (job.kind === "reprocess_all") {
    const { line, failed } = reprocessSummary(r);
    return (
      <Stack gap={2} mt="xs">
        <Text size="sm">{line}</Text>
        {failed.length ? (
          <Text size="xs" c="red">Failed: {failed.join(", ")}</Text>
        ) : null}
      </Stack>
    );
  }
  if (job.kind === "build_master") {
    const skipped = Number(r.n_skipped ?? 0) || 0;
    return (
      <Stack gap={4} mt="xs">
        <Text size="sm" c={skipped > 0 ? "orange" : undefined}>
          {buildMasterSummary(r)}
        </Text>
        <Group>
          <Button size="xs" variant="light" leftSection={<IconFlask size={14} />}
            component={Link} to="/calibration">
            View masters
          </Button>
        </Group>
      </Stack>
    );
  }
  let action: ReactNode = null;
  if (job.kind === "editor_png" && r.png_path && r.safe && r.run_id != null) {
    action = (
      <Button size="xs" variant="light" leftSection={<IconDownload size={14} />}
        component="a" href={api.editPngUrl(String(r.safe), Number(r.run_id), job.id)}>
        Download PNG
      </Button>
    );
  } else if (job.kind === "editor_export" && r.safe) {
    action = (
      <Button size="xs" variant="light" leftSection={<IconPhoto size={14} />}
        component={Link} to={`/targets/${r.safe}/history`}>
        View result
      </Button>
    );
  } else if (job.kind === "editor_batch") {
    const n = Array.isArray(r.exported) ? r.exported.length : 0;
    action = (
      <Button size="xs" variant="light" leftSection={<IconPhoto size={14} />}
        component={Link} to="/gallery">
        View {n} in Gallery
      </Button>
    );
  }
  return action ? <Group mt="xs">{action}</Group> : null;
}

/** A failed job's error, translated to plain language where we recognise it. */
function JobError({ raw, kind }: { raw: string; kind?: string | null }) {
  const { message, next } = friendlyJobError(raw, kind);
  return (
    <>
      <Text c="red" size="sm" mt="xs">{message}</Text>
      {next ? <Text c="dimmed" size="xs" mt={2}>{next}</Text> : null}
    </>
  );
}

export function JobRow(
  { job, onCancel, eta }: { job: Job; onCancel: () => void; eta?: string | null },
) {
  const pct = job.total ? Math.round((job.done / job.total) * 100) : 0;
  const active = job.state === "running" || job.state === "queued";
  return (
    <Paper withBorder p="md">
      <Group justify="space-between">
        <Group>
          <Badge color={COLOR[job.state] ?? "gray"}>{job.state}</Badge>
          <Text fw={500}>{jobKindLabel(job.kind)}</Text>
          {job.target ? <Text c="dimmed" size="sm">{job.target}</Text> : null}
        </Group>
        <Group>
          <Text size="sm" c="dimmed">
            {job.phase} {job.total ? `${job.done}/${job.total}` : ""}
            {/* Per-step "time left" — shown next to this step's count so it reads
                unambiguously as the current step, not the whole job. */}
            {job.state === "running" && eta ? ` · ${eta}` : ""}
          </Text>
          {active ? (
            <ActionIcon variant="subtle" color="red" onClick={onCancel} aria-label="Cancel job">
              <IconX size={16} />
            </ActionIcon>
          ) : null}
        </Group>
      </Group>
      {active ? <Progress value={job.state === "queued" ? 0 : pct} animated mt="xs" /> : null}
      {job.error ? <JobError raw={job.error} kind={job.error_kind} /> : null}
      {job.detail ? <Text c="dimmed" size="xs" mt={4}>{job.detail}</Text> : null}
      <JobResultActions job={job} />
    </Paper>
  );
}

// Per-job "time left" for the running jobs. We can't estimate this whole-job
// (each step restarts its own done/total — see jobEta.ts), so we anchor on the
// first observation of the *current* step and project from the rate since then.
// The anchors persist across the 1.5 s poll in a ref (a display cache, not
// render-affecting state); finished jobs are pruned so it can't grow unbounded.
function useJobEtas(jobs: Job[]): Record<string, string | null> {
  const store = useRef<Map<string, { anchor: EtaSample; cur: EtaSample }>>(new Map());
  const now = Date.now();
  const out: Record<string, string | null> = {};
  const live = new Set<string>();
  for (const j of jobs) {
    if (j.state !== "running") continue;
    live.add(j.id);
    const obs = { phase: j.phase ?? "", total: j.total ?? 0, done: j.done ?? 0 };
    const rec = store.current.get(j.id);
    // Reuse the stored observation timestamp while nothing has changed, so the
    // estimate doesn't drift upward on re-renders between polls.
    const cur: EtaSample =
      rec && rec.cur.phase === obs.phase && rec.cur.total === obs.total && rec.cur.done === obs.done
        ? rec.cur
        : { ...obs, tMs: now };
    const anchor = updateEtaAnchor(rec ? rec.anchor : null, cur);
    store.current.set(j.id, { anchor, cur });
    out[j.id] = etaLabel(anchor, cur);
  }
  for (const id of [...store.current.keys()]) {
    if (!live.has(id)) store.current.delete(id);
  }
  return out;
}

/** The "Notify me when done" opt-in toggle.
 *
 * This only owns the switch state + the permission request; the actual
 * notification firing lives in the always-mounted `GlobalJobNotifier` (App.tsx),
 * so a job pings regardless of which page is open — and, being the single firing
 * site, a job can never double-notify. The toggle persists to localStorage, which
 * the global watcher reads fresh each poll, so flipping it here takes effect
 * app-wide with no shared React state. */
function useJobFinishNotifications() {
  const [enabled, setEnabled] = useState(isJobNotifyEnabled);

  const toggle = async (on: boolean) => {
    if (!on) {
      setJobNotifyEnabled(false);
      setEnabled(false);
      return;
    }
    const perm = await requestNotificationPermission();
    if (perm === "granted") {
      setJobNotifyEnabled(true);
      setEnabled(true);
    } else {
      setJobNotifyEnabled(false);
      setEnabled(false);
      notifications.show({
        color: "gray",
        message: perm === "unsupported"
          ? "This browser doesn't support desktop notifications."
          : "Your browser blocked notifications — allow them for this site to get a ping when a job finishes.",
      });
    }
  };

  return { enabled, toggle, supported: notificationsSupported() };
}

export function JobsView() {
  const qc = useQueryClient();
  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: ["jobs"],
    queryFn: api.listJobs,
    refetchInterval: 1500,
  });
  const notify = useJobFinishNotifications();
  const cancel = useMutation({
    mutationFn: (id: string) => api.cancelJob(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["jobs"] }),
    onError: (e: Error) => notifications.show({ message: e.message, color: "red" }),
  });
  const clear = useMutation({
    mutationFn: () => api.clearJobs(),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["jobs"] }),
  });
  const finished = (data ?? []).filter(
    (j) => !["running", "queued"].includes(j.state),
  ).length;
  // Computed every render (before the early returns) so the hook order is stable.
  const etas = useJobEtas(data ?? []);

  if (isError && !data) {
    return <QueryError error={error} onRetry={() => refetch()} />;
  }
  if (isLoading) {
    return (
      <Center h={300}>
        <Loader />
      </Center>
    );
  }

  const jobs = data ?? [];

  return (
    <Stack>
      <Group justify="space-between">
        <Title order={2}>Jobs</Title>
        <Group gap="md">
          {notify.supported ? (
            <Tooltip
              label="Get a desktop notification when a job finishes, so you can switch tabs while it runs."
              multiline w={240} withArrow
            >
              <Switch
                size="sm"
                checked={notify.enabled}
                onChange={(e) => { void notify.toggle(e.currentTarget.checked); }}
                label="Notify me when done"
              />
            </Tooltip>
          ) : null}
          {finished > 0 ? (
            <Button size="xs" variant="subtle" color="gray" loading={clear.isPending}
              onClick={() => clear.mutate()}>
              Clear {finished} finished
            </Button>
          ) : null}
        </Group>
      </Group>
      {jobs.length === 0 ? (
        <Paper withBorder p="xl">
          <Stack align="center" gap="sm">
            <IconActivity size={40} color="var(--mantine-color-dark-3)" />
            <Text c="dimmed">No jobs running.</Text>
            <Text c="dimmed" size="sm" ta="center" maw={420}>
              Click “Scan incoming” in the header to import and process your Seestar
              frames — ingest, quality check and plate-solve run here as jobs. No NAS
              share? <Anchor component={Link} to="/library">Upload FITS files</Anchor> from your
              computer in the Library instead.
            </Text>
          </Stack>
        </Paper>
      ) : (
        jobs.map((j) => (
          <JobRow key={j.id} job={j} onCancel={() => cancel.mutate(j.id)} eta={etas[j.id]} />
        ))
      )}
    </Stack>
  );
}
