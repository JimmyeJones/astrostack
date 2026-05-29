import { useEffect, useState } from "react";
import type { Job } from "../api/client";

// Subscribe to a job's SSE progress stream. Returns the latest job snapshot.
export function useJobEvents(jobId: string | null): Job | null {
  const [job, setJob] = useState<Job | null>(null);

  useEffect(() => {
    if (!jobId) {
      setJob(null);
      return;
    }
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
    es.onerror = () => es.close();
    return () => es.close();
  }, [jobId]);

  return job;
}
