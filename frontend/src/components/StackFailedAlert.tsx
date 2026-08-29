import { Alert, Anchor, Button, Group, Text } from "@mantine/core";
import { IconAlertTriangle } from "@tabler/icons-react";
import { Link } from "react-router-dom";

import { formatStampDate } from "../format";
import { friendlyJobError } from "../routes/Jobs";
import type { StackFailure } from "../api/client";

/**
 * "This target stopped producing pictures, and here's why."
 *
 * A stack that *refuses* used to go dark. The engine's refusal is already the
 * best sentence anyone could write — it names the one lever that would make the
 * run fit and the memory it lands at — but on the walk-away path it is caught
 * per target and filed in a scan job's result, where nobody looks. This is that
 * sentence, on a page the owner actually opens.
 *
 * Three deliberate choices:
 *   * **The engine's own words are shown verbatim**, under the plain-language
 *     translation the Jobs page already writes for the same `error_kind`. The
 *     translation says *what happened*; only the raw line carries the numbers
 *     ("~9.4 GB, over the ~6.0 GB budget") that tell you how far off you are.
 *   * **It never offers to apply the fix.** Every lever here (canvas mode,
 *     drizzle scale) changes the picture, which is why the engine declined to
 *     take them silently; the owner clicking it *is* the point. It links to the
 *     control instead.
 *   * **"Nobody was watching" changes the wording, not the fix** — an unattended
 *     refusal is the one a beginner has no other way of finding out about, so it
 *     says so.
 */
export function StackFailedAlert({
  failure, showTargetName = false,
}: {
  failure: StackFailure;
  /** Name the target in the title — for the library-wide (Dashboard) mount. */
  showTargetName?: boolean;
}) {
  const { message, next, action } = friendlyJobError(failure.message, failure.kind);
  const when = formatStampDate(failure.when_utc);
  const subject = showTargetName ? failure.name : "This target";
  return (
    <Alert
      color="orange" variant="light" icon={<IconAlertTriangle size={18} />}
      data-testid="stack-failed-note"
      title={showTargetName
        ? `${failure.name} didn't stack${when ? ` (${when})` : ""}`
        : `Your last stack didn't run${when ? ` (${when})` : ""}`}
    >
      <Text size="sm">
        {failure.unattended
          ? `${subject} tried to stack on its own and stopped, so there is no new `
            + "picture from it."
          : `${subject}'s last stack stopped before it ran, so there is no new `
            + "picture from it."}{" "}
        {message}
      </Text>
      {next ? <Text size="sm" mt={4}>{next}</Text> : null}
      <Text size="xs" c="dimmed" mt={6} style={{ wordBreak: "break-word" }}>
        {failure.message}
      </Text>
      <Group gap="xs" mt="xs">
        {action ? (
          <Button size="compact-xs" variant="light" color="orange"
            component={Link} to={action.href}>
            {action.label}
          </Button>
        ) : null}
        {showTargetName ? (
          <Anchor component={Link} to={`/targets/${failure.safe}`} size="xs">
            Open {failure.name} →
          </Anchor>
        ) : null}
      </Group>
    </Alert>
  );
}
