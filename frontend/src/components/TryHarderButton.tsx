import { Button } from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "../api/client";

/** "Try harder to locate these" — the deep-image rescue, offered wherever a
 *  beginner has just been told that most of their subs couldn't be placed.
 *
 *  Its own component because every surface that wants it needs the same two
 *  things and neither belongs in a pure summary helper: the server's answer to
 *  "would the rescue actually engage on this target?" (`deep_rescue_offered`,
 *  the engine's own gate — see `seestack/solve/bootstrap.rescue_is_worth_offering`)
 *  and a mutation with its own pending state.
 *
 *  It renders **nothing at all** until the server says yes, so an ordinary
 *  target, a target that has never been plate-solved, an older backend that
 *  omits the field, and a failed or still-loading read all leave the caller
 *  exactly as it was. That is deliberate: this sits under advice that is already
 *  useful on its own, and a dead button under it would be worse than no button.
 *
 *  The query shares the Target page's own `["reject-summary", safe]` key, so
 *  opening a target after pressing this — the likely next move — costs nothing
 *  extra, and the invalidation below refreshes both surfaces at once.
 */
export function TryHarderButton({ safe }: { safe: string }) {
  const qc = useQueryClient();
  const summary = useQuery({
    queryKey: ["reject-summary", safe],
    queryFn: () => api.rejectSummary(safe),
  });
  const rescue = useMutation({
    mutationFn: () => api.rescueUnsolved(safe),
    onSuccess: () => {
      notifications.show({
        message: "Trying harder — combining your un-located subs into one deeper "
          + "image to locate them together. Watch Jobs for progress.",
        color: "violet",
      });
      qc.invalidateQueries({ queryKey: ["jobs"] });
      qc.invalidateQueries({ queryKey: ["reject-summary", safe] });
    },
    onError: (e: Error) => notifications.show({ message: e.message, color: "red" }),
  });

  if (!summary.data?.deep_rescue_offered) return null;
  return (
    <Button size="compact-xs" variant="light" mt={4}
      loading={rescue.isPending} onClick={() => rescue.mutate()}>
      Try harder to locate these
    </Button>
  );
}
