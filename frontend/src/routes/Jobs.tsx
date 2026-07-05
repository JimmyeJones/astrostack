import {
  ActionIcon, Badge, Button, Center, Group, Loader, Paper, Progress, Stack, Text, Title,
} from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { IconActivity, IconDownload, IconPhoto, IconX } from "@tabler/icons-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { type ReactNode } from "react";
import { api, type Job } from "../api/client";
import { QueryError } from "../components/QueryError";

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
  const failedArr = Array.isArray(r.failed) ? r.failed : [];
  const failed = failedArr
    .map((f) => (f && typeof f === "object"
      ? String((f as Record<string, unknown>).target ?? "") : ""))
    .filter(Boolean);
  let line = `Restacked ${stacked}/${total} target${total === 1 ? "" : "s"}`;
  if (r.cancelled) line += " (cancelled early)";
  // Only present when the deep-rescan option was used (re-ran QC/solve/grade first).
  if (rescanned > 0) line += ` — re-ran QC/solve/grade on ${rescanned}`;
  if (skipped > 0) line += ` — ${skipped} already up to date`;
  if (failed.length) line += ` — ${failed.length} failed`;
  return { line: `${line}.`, failed };
}

/** Result-specific actions for finished editor jobs (download / view). */
function JobResultActions({ job }: { job: Job }) {
  if (job.state !== "done" || !job.result) return null;
  const r = job.result as Record<string, unknown>;
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

function JobRow({ job, onCancel }: { job: Job; onCancel: () => void }) {
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

export function JobsView() {
  const qc = useQueryClient();
  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: ["jobs"],
    queryFn: api.listJobs,
    refetchInterval: 1500,
  });
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
        {finished > 0 ? (
          <Button size="xs" variant="subtle" color="gray" loading={clear.isPending}
            onClick={() => clear.mutate()}>
            Clear {finished} finished
          </Button>
        ) : null}
      </Group>
      {jobs.length === 0 ? (
        <Paper withBorder p="xl">
          <Stack align="center" gap="sm">
            <IconActivity size={40} color="var(--mantine-color-dark-3)" />
            <Text c="dimmed">No jobs running.</Text>
            <Text c="dimmed" size="sm" ta="center" maw={420}>
              Click “Scan incoming” in the header to import and process your Seestar
              frames — ingest, quality check and plate-solve run here as jobs.
            </Text>
          </Stack>
        </Paper>
      ) : (
        jobs.map((j) => <JobRow key={j.id} job={j} onCancel={() => cancel.mutate(j.id)} />)
      )}
    </Stack>
  );
}
