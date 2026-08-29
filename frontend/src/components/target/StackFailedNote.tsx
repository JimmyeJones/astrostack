import { useQuery } from "@tanstack/react-query";

import { api } from "../../api/client";
import { StackFailedAlert } from "../StackFailedAlert";

/**
 * The per-target mount of "your last stack didn't run".
 *
 * Shares the Dashboard's query cache (`["stack-failures"]`) and picks out this
 * target's row, so opening a target after the Dashboard costs no second fetch.
 * Self-hiding when this target is fine — which is the ordinary case — so the
 * Target page's notice board folds nothing extra.
 */
export function StackFailedNote({ safe }: { safe: string }) {
  const { data } = useQuery({
    queryKey: ["stack-failures"],
    queryFn: api.getStackFailures,
    staleTime: 300_000,
  });
  const failure = (data?.failures ?? []).find((f) => f.safe === safe);
  if (!failure) return null;
  return <StackFailedAlert failure={failure} />;
}
