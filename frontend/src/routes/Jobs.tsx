import {
  ActionIcon, Badge, Center, Group, Loader, Paper, Progress, Stack, Text, Title,
} from "@mantine/core";
import { IconX } from "@tabler/icons-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
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
  });

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
      <Title order={2}>Jobs</Title>
      {jobs.length === 0 ? (
        <Text c="dimmed">No jobs yet.</Text>
      ) : (
        jobs.map((j) => <JobRow key={j.id} job={j} onCancel={() => cancel.mutate(j.id)} />)
      )}
    </Stack>
  );
}
