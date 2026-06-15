import {
  ActionIcon, Badge, Button, Center, Group, Loader, Paper, Progress, Stack, Text, Title,
} from "@mantine/core";
import { IconDownload, IconPhoto, IconX } from "@tabler/icons-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { type ReactNode } from "react";
import { api, type Job } from "../api/client";

const COLOR: Record<string, string> = {
  running: "violet",
  queued: "gray",
  done: "teal",
  error: "red",
  cancelled: "orange",
  interrupted: "orange",
};

/** Result-specific actions for finished editor jobs (download / view). */
function JobResultActions({ job }: { job: Job }) {
  if (job.state !== "done" || !job.result) return null;
  const r = job.result as Record<string, unknown>;
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

function JobRow({ job, onCancel }: { job: Job; onCancel: () => void }) {
  const pct = job.total ? Math.round((job.done / job.total) * 100) : 0;
  const active = job.state === "running" || job.state === "queued";
  return (
    <Paper withBorder p="md">
      <Group justify="space-between">
        <Group>
          <Badge color={COLOR[job.state] ?? "gray"}>{job.state}</Badge>
          <Text fw={500}>{job.kind}</Text>
          {job.target ? <Text c="dimmed" size="sm">{job.target}</Text> : null}
        </Group>
        <Group>
          <Text size="sm" c="dimmed">
            {job.phase} {job.total ? `${job.done}/${job.total}` : ""}
          </Text>
          {active ? (
            <ActionIcon variant="subtle" color="red" onClick={onCancel}>
              <IconX size={16} />
            </ActionIcon>
          ) : null}
        </Group>
      </Group>
      {active ? <Progress value={job.state === "queued" ? 0 : pct} animated mt="xs" /> : null}
      {job.error ? <Text c="red" size="sm" mt="xs">{job.error}</Text> : null}
      {job.detail ? <Text c="dimmed" size="xs" mt={4}>{job.detail}</Text> : null}
      <JobResultActions job={job} />
    </Paper>
  );
}

export function JobsView() {
  const qc = useQueryClient();
  const { data, isLoading } = useQuery({
    queryKey: ["jobs"],
    queryFn: api.listJobs,
    refetchInterval: 1500,
  });
  const cancel = useMutation({
    mutationFn: (id: string) => api.cancelJob(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["jobs"] }),
  });

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
      <Title order={2}>Jobs</Title>
      {jobs.length === 0 ? (
        <Text c="dimmed">No jobs yet.</Text>
      ) : (
        jobs.map((j) => <JobRow key={j.id} job={j} onCancel={() => cancel.mutate(j.id)} />)
      )}
    </Stack>
  );
}
