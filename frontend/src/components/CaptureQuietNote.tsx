import { Alert, Button, Group, Text } from "@mantine/core";
import { IconAntennaOff } from "@tabler/icons-react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import { captureQuietMessage } from "../live/liveSession";

// How often to re-ask while the page is open. The same gentle cadence the Live
// page polls at: a capture night moves in minutes, and the endpoint is a
// read-only aggregation over the frames table.
const POLL_MS = 60_000;

/**
 * "No new subs for a while — capture may have stopped."
 *
 * The failure the owner cannot see happening. They set the Seestar going, walk
 * away, and part-way through an otherwise-clear night it stalls — the connection
 * drops, the microSD fills, a dew-heater trip parks it — so subs simply stop
 * arriving. Nothing in the app noticed: the watcher fires *on* arrival, so a
 * target that stops feeding just goes still, and the owner finds out in the
 * morning that half their night is missing.
 *
 * This is that fact, on the page where their picture lives, while the night is
 * still young enough to do something about it. It is **informational only** — it
 * never acts, never restarts anything, and never touches `incoming/`.
 *
 * The care is all in *not* crying wolf, and it lives in the backend
 * (`seestack/livesession.py`): the wait scales with the cadence this target has
 * actually been keeping, the session must have been mid-run rather than a
 * handful of test subs, and once the silence outlasts the session gap this is
 * simply *last night* — the recap's story, not a live warning. So the note
 * appears for a stall and self-hides for a night that merely ended.
 *
 * Best-effort: an older backend (no `quiet` field) or a failed fetch renders
 * nothing, exactly as before this existed.
 */
export function CaptureQuietNote({ safe }: { safe: string }) {
  const live = useQuery({
    queryKey: ["live-session", safe],
    queryFn: () => api.liveSession(safe).catch(() => null),
    enabled: !!safe,
    refetchInterval: POLL_MS,
    staleTime: 30_000,
    retry: false,
  });
  const l = live.data;
  const message = l ? captureQuietMessage(l) : null;
  if (!message) return null;
  return (
    <Alert color="orange" variant="light" icon={<IconAntennaOff size={18} />}
      title="No new subs from this target for a while"
      data-testid="capture-quiet-note">
      <Text size="sm">{message}</Text>
      <Group gap="xs" mt="xs">
        <Button size="xs" variant="light" color="orange" component={Link}
          to={`/live?target=${encodeURIComponent(safe)}`}>
          See tonight's session
        </Button>
      </Group>
    </Alert>
  );
}
