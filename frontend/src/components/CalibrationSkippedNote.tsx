import { Text } from "@mantine/core";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";

/**
 * "Your saved master dark wasn't used: …" — the one thing a walk-away user needs
 * to know about a finished picture that is *less* calibrated than they asked for.
 *
 * The unattended binder is deliberately fail-soft (a master deleted since it was
 * picked, or one built for another camera, is dropped rather than failing the
 * overnight job), and v0.216.0 started recording the reason on the run so the
 * History **Info** panel could say it out loud. But the hands-off user's natural
 * landing spots are the Jobs page's "Process target" result and the Target page's
 * newest-run block — neither of which shows it, and neither of which they have to
 * expand. So the very person the note exists for is the one least likely to read
 * it. This badge puts the same recorded sentences on those two surfaces.
 *
 * Pure display re-use of a field that already ships on the run-info payload
 * (`calibration_skipped`): no new endpoint, no new recording. Shares the Editor's
 * `["stack-run-info", …]` query key so a run fetched on one surface isn't fetched
 * twice, and is best-effort — a failed fetch or an older backend simply renders
 * nothing rather than an error.
 */
export function CalibrationSkippedNote({
  safe,
  runId,
}: {
  safe: string;
  runId: number;
}) {
  const info = useQuery({
    queryKey: ["stack-run-info", safe, runId],
    queryFn: () => api.stackRunInfo(safe, runId).catch(() => null),
    enabled: !!safe && Number.isFinite(runId),
    staleTime: 30_000,
    retry: false,
  });
  const skipped = (info.data?.calibration_skipped ?? [])
    .map((s) => String(s).trim())
    .filter(Boolean);
  if (skipped.length === 0) return null;
  return (
    <Text size="xs" c="yellow.7" fw={600} data-testid="calibration-skipped-note">
      {skipped.join(" ")}
    </Text>
  );
}
