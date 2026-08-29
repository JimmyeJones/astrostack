import { Anchor, Stack, Text } from "@mantine/core";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { api } from "../../api/client";
import { StackFailedAlert } from "../StackFailedAlert";

/** How many failing targets are shown in full before the rest are summarised. */
const NAMED = 2;

/**
 * "Some of your targets stopped making pictures" — on the page you land on.
 *
 * The walk-away stack is the owner's whole workflow, and a refusal on it is the
 * one failure the app was completely silent about: the scan job finishes `done`,
 * the target's frames all still list, and nothing anywhere says a picture stopped
 * arriving. This is the library-wide mount; the Target page carries the same
 * alert for its own target.
 *
 * Self-hiding at zero — which is every healthy install — so the notice board
 * folds nothing on an ordinary day.
 */
export function StackFailuresNote() {
  const { data } = useQuery({
    queryKey: ["stack-failures"],
    queryFn: api.getStackFailures,
    // A cross-target read on a polling page, and the answer only changes when a
    // stack runs. Once per visit is plenty.
    staleTime: 300_000,
  });

  const failures = data?.failures ?? [];
  if (failures.length === 0) return null;

  const named = failures.slice(0, NAMED);
  const rest = failures.length - named.length;
  return (
    <Stack gap="xs" data-testid="stack-failures-note">
      {named.map((f) => (
        <StackFailedAlert key={f.safe} failure={f} showTargetName />
      ))}
      {rest > 0 ? (
        <Text size="xs" c="dimmed">
          {rest === 1 ? "1 more target" : `${rest} more targets`} stopped stacking too —{" "}
          <Anchor component={Link} to="/library" size="xs">see your Library</Anchor>.
        </Text>
      ) : null}
    </Stack>
  );
}
