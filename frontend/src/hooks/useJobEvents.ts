import { useEffect, useState } from "react";
import type { Job } from "../api/client";

// Subscribe to a job's SSE progress stream. Returns the latest job snapshot.
export function useJobEvents(jobId: string | null): Job | null {
  const [job, setJob] = useState<Job | null>(null);

  useEffect(() => {
    // Drop the previous job's snapshot on *every* id change (not just when it
    // clears): otherwise, right after starting a new job, the hook keeps returning
    // the previous job's stale (often "done") snapshot until the new stream emits.
    setJob(null);
    if (!jobId) return;
    const es = new EventSource(`/api/jobs/${jobId}/events`);
    const onMessage = (e: MessageEvent) => {
      try {
        setJob(JSON.parse(e.data) as Job);
      } catch {
        /* ignore malformed */
      }
    };
    es.addEventListener("progress", onMessage);
    es.addEventListener("done", (e) => {
      onMessage(e as MessageEvent);
      es.close();
    });
    es.onerror = () => {
      // A *transient* drop (laptop sleep, proxy idle-timeout, a network blip
      // mid-stack) leaves readyState === CONNECTING and EventSource auto-reconnects
      // on its own; the backend re-sends the current state (and `done` if the job
      // already finished) on every reconnect, so the UI still resolves. Closing
      // here would defeat that reconnect and freeze the panel forever on the last
      // snapshot. Only tidy up once the browser has permanently given up
      // (readyState CLOSED — e.g. the job 404'd), where it won't reconnect anyway.
      if (es.readyState === EventSource.CLOSED) es.close();
    };
    return () => es.close();
  }, [jobId]);

  return job;
}
