import { Alert, Button, Text } from "@mantine/core";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api } from "../../api/client";
import { importWaitingNote } from "../../importWaiting";
import { jobKindLabel } from "../../routes/Jobs";

/**
 * "Your new frames haven't been imported yet" — on the screen the owner opens.
 *
 * AstroStack runs one job at a time, so a job that runs for days holds the queue
 * for days. That is visible for a job someone started; the import job is the one
 * nobody starts by hand, and while it waits **nothing anywhere says so**. Every
 * target keeps showing the frame count it had before, and a frame that was never
 * imported has no QC row and no reject reason, so there is nowhere in the record
 * it can be seen to be absent. Reported 2026-09-14 by the on-NAS observer: 2,259
 * subs over two nights sat on disk for eleven days behind a "Reprocess all", the
 * last three of them with an import queued and never started.
 *
 * The Jobs page carries the same sentence (one wording, in `importWaiting.ts`),
 * but overnight.py's own note applies — Jobs is "a screen a beginner has no
 * reason to open", and this failure is precisely the kind you only look for once
 * you already suspect it. So it joins the Dashboard's notice board rather than
 * becoming one more always-on banner (AGENTS.md §1).
 *
 * Ranked `warning`, not `blocking`: nothing is broken and nothing is lost — the
 * subs are safe in `incoming/` and the import runs the moment the worker frees
 * up — but the library is quietly out of date, and every readiness figure for
 * those targets is reading low. Self-hiding on a healthy queue (the ordinary
 * answer is `null`), and it swallows a failed read rather than showing an error,
 * so an older backend with no such endpoint renders nothing. Not dismissable:
 * like the missing-files note, this is a live condition that clears itself.
 */
export function StuckImportNote() {
  const { data } = useQuery({
    queryKey: ["job-queue-health"],
    queryFn: () => api.jobQueueHealth().catch(() => null),
    // The answer moves on the scale of hours, so this costs one cheap request a
    // minute at most. Same key as the Jobs page's own query, so the two share a
    // cache and can never disagree about the queue.
    refetchInterval: 60_000,
    staleTime: 30_000,
  });

  const note = importWaitingNote(data?.waiting, jobKindLabel);
  if (!note) return null;

  return (
    <Alert
      color="yellow" variant="light" data-testid="stuck-import-note"
      title={note.title}
    >
      <Text size="sm">{note.body}</Text>
      <Text size="sm" mt={4}>{note.reassurance}</Text>
      <Button component={Link} to="/jobs" size="xs" variant="light" color="yellow" mt="xs">
        Open Jobs
      </Button>
    </Alert>
  );
}
