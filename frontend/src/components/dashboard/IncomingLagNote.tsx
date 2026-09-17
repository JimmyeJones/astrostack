import { Alert, Button, Group, Text } from "@mantine/core";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { notifications } from "@mantine/notifications";
import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../../api/client";
import { loadDismissedSig, saveDismissedSig } from "../../dismissal";
import { incomingLagCause, incomingLagUnreadable, waitedFor } from "../../importWaiting";

const DISMISS_KEY = "astrostack.dashboard.incomingLagDismissed";

// How many folders the note names outright before it stops listing — the same
// bound the other library-wide notes use, because three is what fits on one line
// on a phone.
const NAMED = 3;

/**
 * "Some of your subs never made it into your library."
 *
 * This is the failure that cannot be seen from inside the app. A frame that was
 * never imported has no QC row, no reject reason and nowhere in the record it
 * can be *seen* to be absent — so the library quietly stops growing while every
 * screen looks perfectly healthy, and the only person who could notice is the
 * one who counts files on disk by hand. On the owner's own box that came to
 * 2,259 subs across two nights sitting in `incoming/` for eleven days.
 *
 * `StuckImportNote` is its sibling and says the same thing from the other end:
 * an import job *queued* behind the one serial worker. That is how it happened
 * that time, but it is one of several ways, and the others (a poll that walked a
 * folder during a job that then died, a scan-side error swallowed before a row
 * is written) leave nothing queued for that note to find. This one does not ask
 * about jobs at all — it compares what is on disk with what is in the library —
 * so it is the signal that catches every shape.
 *
 * **Written to under-report.** The backend only counts folders a scan would
 * actually ingest (the Seestar's own pictures, videos and scratch folders are
 * skipped on purpose, not lag), and only once a folder has stopped changing for
 * a couple of hours — a night still arriving over SMB is *supposed* to be ahead
 * of the library. So the ordinary answer on every healthy install is zero, and
 * the note renders nothing at all.
 *
 * **Reassurance first, then the offer.** "Your frames aren't in your library" is
 * an alarming sentence to a beginner whose only copy of those frames is the
 * folder in question, so the note says plainly that nothing is lost and that
 * AstroStack never writes there. The action is the ordinary "Scan incoming" —
 * the same thing the watcher would do by itself — because there is nothing to
 * repair, only something to retry.
 *
 * **Except when the sibling above has already answered.** Both notes fire on the
 * owner's own reported event, both rank `warning`, and the board keeps two
 * inline — so on the case they were built for, this one used to *guess* at a
 * cause (`"this usually means an import is still waiting its turn"`) that
 * `StuckImportNote` had just stated as a measured fact with a duration, repeat
 * its "nothing is lost", and then offer the opposite action: a scan, while that
 * note said to let the queue through. The worker is serial, so a second scan
 * only joins the back of the queue the first one is already at the front of.
 * `incomingLagCause` reads the queue instead of guessing — off the same query
 * key the sibling already populates, so it costs no request and the two cannot
 * disagree — and the note then says what it uniquely knows (how many, which
 * folders, how long) and points at the Jobs page rather than at a scan that
 * would not help.
 *
 * **And the other case where a scan would not help: a file that cannot be read.**
 * Comparing files on disk with frame rows is the right question and is blind to
 * *why* a row is missing. A damaged or headerless FITS has no row **permanently**,
 * so it counts as waiting forever and this note has been telling the owner, since
 * May and about six real files, that they "haven't been imported yet" over a
 * button that can never import them. `n_unreadable` (v0.452.1) is that count, off
 * the record the scan leaves behind rather than by opening anything, and it moves
 * the note by exactly as much as it should: a mixed folder keeps its headline and
 * gains a sentence, an all-damaged one stops calling itself a delay and withdraws
 * the scan. The dismissal signature carries the split too, so a note dismissed as
 * "waiting" speaks again once it turns out to be damage.
 */
export function IncomingLagNote() {
  const { data } = useQuery({
    queryKey: ["incoming-lag"],
    queryFn: () => api.getIncomingLag().catch(() => null),
    // A cross-target read on a polling page, answering a question that moves on
    // the scale of hours. Once per visit is plenty, and a failed read renders
    // nothing rather than an error — an older backend has no such endpoint.
    staleTime: 300_000,
  });
  // Same key and same options as `StuckImportNote`, so the two share one cache
  // entry: no second request, and no way for them to hold different opinions
  // about the queue they are both describing.
  const queue = useQuery({
    queryKey: ["job-queue-health"],
    queryFn: () => api.jobQueueHealth().catch(() => null),
    refetchInterval: 60_000,
    staleTime: 30_000,
  });
  const [dismissedSig, setDismissedSig] = useState(() => loadDismissedSig(DISMISS_KEY));
  const qc = useQueryClient();
  const navigate = useNavigate();
  const scan = useMutation({
    mutationFn: () => api.scan(),
    onSuccess: () => {
      notifications.show({ message: "Scan started — watching for new frames", color: "violet" });
      qc.invalidateQueries({ queryKey: ["jobs"] });
      navigate("/jobs");
    },
  });

  const waiting = data?.n_waiting ?? 0;
  if (!data?.checked || waiting <= 0) return null;

  const items = data.items ?? [];
  // The signature carries the counts, so importing some and leaving others makes
  // the note speak again about what is left rather than staying quiet.
  const sig = `${waiting}|${data.n_unreadable ?? 0}|`
    + items.map((i) => `${i.folder}:${i.n_waiting}:${i.n_unreadable ?? 0}`).join(",");
  if (sig === dismissedSig) return null;

  const named = items.slice(0, NAMED);
  const longest = items.reduce(
    (worst, it) => (it.still_hours > worst ? it.still_hours : worst), 0);
  const sat = waitedFor(longest);
  const cause = incomingLagCause(queue.data?.waiting);
  // Files the app has opened and cannot read. They count as waiting forever, so
  // the title and the button above are both wrong about them — and since
  // v0.452.0 the Jobs page says so out loud, which makes it a contradiction
  // rather than merely a wrong sentence. When *every* waiting file is one of
  // these, the note is not about a delay at all and stops pretending to be.
  const damaged = incomingLagUnreadable(waiting, data.n_unreadable);
  const title = damaged?.title ?? (waiting === 1
    ? "A sub in your incoming folder hasn't been imported yet"
    : `${waiting.toLocaleString()} subs in your incoming folder haven't been imported yet`);
  // A scan cannot import a file it cannot read, so the offer is withdrawn only
  // when there is nothing else left for it to pick up.
  const scanHelps = cause.scanHelps && !damaged?.all;

  return (
    <Alert
      color="yellow" variant="light" data-testid="incoming-lag-note"
      withCloseButton closeButtonLabel="Not now"
      onClose={() => { setDismissedSig(sig); saveDismissedSig(DISMISS_KEY, sig); }}
      title={title}
    >
      <Text size="sm">
        {waiting === 1 ? "A file is " : `${waiting.toLocaleString()} files are `}
        sitting in your incoming folder that your library has no record of
        {data.n_folders > 1 ? `, across ${data.n_folders} folders` : ""}
        {sat ? `, and ${waiting === 1 ? "it has" : "they have"} been there for ${sat}` : ""}.
      </Text>
      {cause.reassurance && !damaged?.all ? (
        <Text size="sm" mt={4}>{cause.reassurance}</Text>
      ) : null}
      {/* On an all-damaged note the cause sentence is simply untrue ("a scan is
          what picks these up"), so it stands aside for the one that is. On a
          mixed note both are true and both are said, the delay first. */}
      {damaged?.all ? null : <Text size="sm" mt={4}>{cause.sentence}</Text>}
      {damaged ? (
        <Text size="sm" mt={4}>{damaged.sentence}</Text>
      ) : null}
      <Group gap="sm" mt="xs" wrap="wrap">
        {scanHelps ? (
          <Button
            size="compact-xs" variant="light" color="yellow"
            onClick={() => scan.mutate()} loading={scan.isPending}
          >
            Scan incoming now
          </Button>
        ) : (
          <Button
            component={Link} to="/jobs"
            size="compact-xs" variant="light" color="yellow"
          >
            Open Jobs
          </Button>
        )}
        {named.map((it) => (
          <Text key={it.folder || "(loose files)"} size="xs" c="dimmed">
            {`${it.folder || "loose in the folder"} · ${it.n_waiting.toLocaleString()} of `
              + `${it.n_on_disk.toLocaleString()} not imported`
              + ((it.n_unreadable ?? 0) > 0
                ? ` (${(it.n_unreadable ?? 0).toLocaleString()} unreadable)` : "")}
          </Text>
        ))}
        {/* Deliberately not a link to a list nobody wrote: no screen in the app
            enumerates incoming folders, and promising one would be the kind of
            small untruth this app keeps having to unpick. */}
        {data.n_folders > named.length ? (
          <Text size="xs" c="dimmed">
            {`and ${data.n_folders - named.length} more`}
          </Text>
        ) : null}
      </Group>
    </Alert>
  );
}
