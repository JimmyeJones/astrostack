import {
  Accordion, Button, Center, Group, Loader, Paper, Progress,
  Stack, Text, Title, Tooltip,
} from "@mantine/core";
import { IconPlayerPlay } from "@tabler/icons-react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { notifications } from "@mantine/notifications";
import { api, type StackOptionField } from "../api/client";
import { StackOptionControl as FieldControl } from "../components/StackOptionControl";
import { useJobEvents } from "../hooks/useJobEvents";

export function StackView() {
  const { safe = "" } = useParams();
  const [values, setValues] = useState<Record<string, unknown>>({});
  const [jobId, setJobId] = useState<string | null>(null);
  const job = useJobEvents(jobId);

  const schema = useQuery({ queryKey: ["schema"], queryFn: api.optionsSchema });
  const defaults = useQuery({
    queryKey: ["stack-defaults", safe],
    queryFn: () => api.getStackDefaults(safe),
  });

  useEffect(() => {
    if (defaults.data) setValues(defaults.data);
  }, [defaults.data]);

  const trigger = useMutation({
    mutationFn: () => api.triggerStack(safe, values),
    onSuccess: (r) => {
      setJobId(r.job_id);
      notifications.show({ message: "Stacking started", color: "violet" });
    },
    onError: (e: Error) => notifications.show({ message: e.message, color: "red" }),
  });

  const saveDefaults = useMutation({
    mutationFn: () => api.putStackDefaults(safe, values),
    onSuccess: () => notifications.show({
      title: "Saved as defaults",
      message: "These options will pre-fill this form and drive auto-stacking for this target.",
      color: "teal",
    }),
    onError: (e: Error) => notifications.show({ message: `Save failed: ${e.message}`, color: "red" }),
  });

  if (schema.isLoading || defaults.isLoading) {
    return (
      <Center h={300}>
        <Loader />
      </Center>
    );
  }

  const fields = schema.data ?? [];
  const set = (k: string, v: unknown) => setValues((p) => ({ ...p, [k]: v }));
  const isDisabled = (f: StackOptionField) =>
    f.depends_on ? !values[f.depends_on] : false;

  const simple = fields.filter((f) => f.group === "simple");
  const advanced = fields.filter((f) => f.group === "advanced");
  const running = job && (job.state === "running" || job.state === "queued");
  const pct = job && job.total ? Math.round((job.done / job.total) * 100) : 0;

  return (
    <Stack maw={720}>
      <Group justify="space-between">
        <Title order={2}>Stack — {safe}</Title>
        <Button component={Link} to={`/targets/${safe}`} variant="subtle">
          Back to frames
        </Button>
      </Group>

      <Paper withBorder p="lg">
        <Stack>
          {simple.map((f) => (
            <FieldControl
              key={f.key}
              field={f}
              value={values[f.key]}
              disabled={isDisabled(f)}
              onChange={(v) => set(f.key, v)}
            />
          ))}

          <Accordion variant="separated" mt="xs">
            <Accordion.Item value="advanced">
              <Accordion.Control>Advanced options</Accordion.Control>
              <Accordion.Panel>
                <Stack>
                  {advanced.map((f) => (
                    <FieldControl
                      key={f.key}
                      field={f}
                      value={values[f.key]}
                      disabled={isDisabled(f)}
                      onChange={(v) => set(f.key, v)}
                    />
                  ))}
                </Stack>
              </Accordion.Panel>
            </Accordion.Item>
          </Accordion>

          {job ? (
            <Stack gap={4}>
              <Group justify="space-between">
                <Text size="sm" c="dimmed">
                  {job.state === "done"
                    ? "Done"
                    : job.state === "error"
                      ? `Error: ${job.error}`
                      : `${job.phase || "working"} ${job.done}/${job.total}`}
                </Text>
                <Text size="sm" c="dimmed">{pct}%</Text>
              </Group>
              <Progress
                value={job.state === "done" ? 100 : pct}
                color={job.state === "error" ? "red" : job.state === "done" ? "teal" : "violet"}
                animated={Boolean(running)}
              />
              {job.state === "done" ? (
                <Button component={Link} to={`/targets/${safe}/history`} variant="light" mt="xs">
                  View result in History
                </Button>
              ) : null}
            </Stack>
          ) : null}

          <Group justify="flex-end" mt="sm">
            <Tooltip label="Remember these options for this target — they pre-fill this form and are used when auto-stacking is on">
              <Button variant="default" onClick={() => saveDefaults.mutate()} loading={saveDefaults.isPending}>
                Save as defaults
              </Button>
            </Tooltip>
            <Button
              leftSection={<IconPlayerPlay size={16} />}
              onClick={() => trigger.mutate()}
              loading={trigger.isPending || Boolean(running)}
            >
              Start stacking
            </Button>
          </Group>
        </Stack>
      </Paper>
    </Stack>
  );
}
