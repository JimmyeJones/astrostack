import { Alert, Anchor, Text } from "@mantine/core";
import { IconHourglassLow } from "@tabler/icons-react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { api } from "../api/client";
import { closingUrgentSentence } from "../closingSeason";

/**
 * "This is your last week for M 42." — the one closing-season case worth
 * interrupting somebody with.
 *
 * The Tonight page's card lists everything leaving inside the season, which is
 * right for a page somebody opened in order to plan. This is the Dashboard, and
 * the person looking at it came to see their pictures — so the only thing that
 * earns the slot is the case where *waiting for the next clear night is itself
 * the mistake* (`CLOSING_URGENT_WEEKS`). Everything else stays on the planner.
 *
 * A pointer, not the answer: it names the target and sends you to the page that
 * carries the detail. Self-hiding on an older backend, on a failed fetch, and —
 * most of the year — because nothing of yours is about to go.
 *
 * **What it costs, since this is the landing page.** The scan behind it is a
 * couple of seconds of ephemeris, and the Dashboard is the screen every visit
 * starts on — so it is cached at both ends: a quarter-hour `staleTime` here and
 * the same on the registry-signature cache behind the endpoint, keyed by date
 * and by the library. A season moves by the week, so neither can serve an answer
 * staler than the numbers in it.
 */
export function ClosingSeasonNote() {
  const q = useQuery({
    queryKey: ["plan-closing", null],
    queryFn: () => api.getSeasonClosing(),
    staleTime: 900_000,     // a season moves by the week, not by the minute
    // An older backend 404s this; that's a quiet no-op, not an error to retry.
    retry: false,
  });
  const sentence = closingUrgentSentence(q.data);
  if (!sentence) return null;
  return (
    <Alert color="orange" variant="light" icon={<IconHourglassLow size={18} />}
      title="Last chance this year" data-testid="closing-season-note">
      <Text size="sm">
        {sentence}{" "}
        <Anchor component={Link} to="/tonight">See what's leaving</Anchor>
      </Text>
    </Alert>
  );
}
