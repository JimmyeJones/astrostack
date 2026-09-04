import { Alert, Button, Group, Text } from "@mantine/core";
import { IconSatellite } from "@tabler/icons-react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api } from "../../api/client";
import { settingsLink } from "../../settingsSections";
import { rejectionOutlookNote } from "./rejectionOutlookNote";

/**
 * "Your saved outlier removal won't take these trails out."
 *
 * The one thing about the *next* stack that the owner cannot find out anywhere
 * else until it is too late. `seestack.stackhealth` says it on the finished
 * picture; the Stack form says it about the values on screen. Neither covers the
 * walk-away path — the overnight auto-stack and the one-click **Process target**
 * button both use the target's saved settings, and a saved sigma clip stays
 * blind to a lone trail below about 11 subs on a spot, for as many nights as it
 * takes the owner to notice.
 *
 * Every judgement is the server's (`/rejection-outlook` resolves the same
 * options the job will, through the same helpers), so this cannot describe a
 * different stack than the one that runs. When to *say* it is
 * `rejectionOutlookNote`, which stays silent unless subs really do carry a
 * trail, the setting really is the user's own, and it really cannot reach.
 *
 * Best-effort and self-hiding: a failed fetch, an older backend, or a target
 * with nothing solved renders nothing at all.
 *
 * Two ways out, and the second is the one a walk-away owner actually wants. The
 * Stack form fixes *this* target; `auto_reject_on_unattended` fixes every
 * hands-off stack at once, and a beginner will never find a Settings switch by
 * name. Offering it needs no gate on *whose* setting it is: the note only speaks
 * when the method is the user's own, and turning that setting on hands the
 * choice back to the app — so on an install that already has it, `user_chose` is
 * false and this whole note is silent. It does need a gate on whether it would
 * *do* anything: on a drizzled target the app's choice is overridden anyway, so
 * `unattendedChoiceHelps` withholds the button rather than offering a fix that
 * changes nothing.
 */
export function RejectionOutlookNote(
  { safe, streaked }: { safe: string; streaked: number },
) {
  const outlook = useQuery({
    queryKey: ["rejection-outlook", safe],
    queryFn: () => api.rejectionOutlook(safe).catch(() => null),
    // Only ask when there is a trail to worry about — the note is silent
    // otherwise, so the request would be pure cost on every target page.
    enabled: !!safe && streaked > 0,
    staleTime: 60_000,
    retry: false,
  });
  const note = rejectionOutlookNote(outlook.data, streaked);
  if (!note) return null;
  return (
    <Alert color="orange" variant="light" icon={<IconSatellite size={18} />}
      title={note.title} data-testid="rejection-outlook-note">
      <Text size="sm">{note.text}</Text>
      <Group gap="xs" mt="xs">
        <Button size="xs" variant="light" color="orange" component={Link}
          to={`/targets/${encodeURIComponent(safe)}/stack`}>
          Change how this target stacks
        </Button>
        {note.unattendedChoiceHelps && (
          <Button size="xs" variant="subtle" color="orange" component={Link}
            to={settingsLink("automation")}>
            Let AstroStack choose on every hands-off stack
          </Button>
        )}
      </Group>
    </Alert>
  );
}
