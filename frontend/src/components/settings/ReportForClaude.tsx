import { Button, Divider, Group, Progress, Stack, Text } from "@mantine/core";
import { IconDownload, IconReportAnalytics } from "@tabler/icons-react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { DIAGNOSTICS_REPORT_URL, api } from "../../api/client";
import { reportDownloadable, reportStatusLine } from "./reportForClaude";

/**
 * Settings → Updates & upkeep → "Create a report for Claude" (1.0 roadmap, M1).
 * A section of the existing App updates card, not a card of its own: the
 * owner's "recursive organization" rule puts a new feature inside an existing
 * group.
 *
 * The owner does not run scripts. One press re-runs every read-only library
 * check as a background job; when it finishes, one file downloads for him to
 * drop into a chat. The server bundles only numbers and catalogue names.
 */
export function ReportForClaude() {
  const [jobId, setJobId] = useState<string | null>(null);
  const start = useMutation({
    mutationFn: api.startDiagnosticsReport,
    onSuccess: (r) => setJobId(r.job_id),
  });
  const job = useQuery({
    queryKey: ["job", jobId],
    queryFn: () => api.getJob(jobId as string),
    enabled: jobId !== null,
    refetchInterval: (q) => {
      const s = q.state.data?.state;
      return s === "queued" || s === "running" ? 2000 : false;
    },
  });
  const j = job.data ?? null;
  const running = j?.state === "queued" || j?.state === "running" || start.isPending;
  const pct = j && j.total > 0 ? Math.round((100 * j.done) / j.total) : null;

  return (
    <Stack gap="sm" data-testid="report-for-claude">
      <Divider />
      <Stack gap="sm">
        <Text fw={500}>Create a report for Claude</Text>
        <Text size="sm" c="dimmed" data-testid="report-status">{reportStatusLine(j)}</Text>
        {running && pct !== null && <Progress value={pct} size="sm" />}
        {start.isError && (
          <Text size="sm" c="red">Couldn't start the checks: {(start.error as Error).message}</Text>
        )}
        <Group>
          <Button leftSection={<IconReportAnalytics size={16} />} loading={running}
            onClick={() => start.mutate()}>
            {j ? "Run the checks again" : "Create report"}
          </Button>
          {reportDownloadable(j) && (
            <Button component="a" href={DIAGNOSTICS_REPORT_URL} download variant="light"
              leftSection={<IconDownload size={16} />}>
              Download report
            </Button>
          )}
        </Group>
      </Stack>
    </Stack>
  );
}
