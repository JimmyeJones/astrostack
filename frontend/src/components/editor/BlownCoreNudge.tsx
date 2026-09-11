import { Alert, Button, Text } from "@mantine/core";
import { IconInfoCircle } from "@tabler/icons-react";
import type { HighlightSuggestion } from "../../api/client";
import { blownCoreButtonLabel, blownCoreCaption } from "./blownCore";

/** The measured "your bright core is washing out" nudge, in one place.
 *
 * The server has already decided whether there is anything to say (see
 * `blownCoreCaption` — it declines on a core too small, barely clipped,
 * saturated at capture, or one the knob can't reopen), so this renders the
 * finding and the one-click fix and nothing else. It self-hides when there is
 * no suggestion, or once the slider is already at or past it.
 *
 * It lives on three surfaces — the Stretch op's panel and both Auto notes — and
 * is a component rather than three copies for the ordinary reason: three
 * sentences about one picture drift into three claims about it.
 */
export function BlownCoreNudge(
  { sug, current, onApply, standalone = false }: {
    sug: HighlightSuggestion | undefined;
    /** The op's current `highlights` value, so a nudge already taken goes quiet. */
    current?: unknown;
    onApply: (strength: number) => void;
    /** `true` on the op panel, where the nudge is the whole message and needs its
     * own alert; `false` inside the Auto notes, where it is one more line of an
     * explanation the user is already reading. */
    standalone?: boolean;
  },
) {
  const text = blownCoreCaption(sug, current);
  if (!text) return null;
  const strength = sug!.strength!;
  const body = (
    <>
      <Text size="xs">{text}</Text>
      <Button size="compact-xs" variant="light" mt={6}
        onClick={() => onApply(strength)}>
        {blownCoreButtonLabel(sug)}
      </Button>
    </>
  );
  if (!standalone) return <div style={{ marginTop: 8 }}>{body}</div>;
  return (
    <Alert color="blue" variant="light" py={6} mb="xs"
      icon={<IconInfoCircle size={16} />}>
      {body}
    </Alert>
  );
}
