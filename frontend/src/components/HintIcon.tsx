import { Tooltip, UnstyledButton } from "@mantine/core";
import { IconInfoCircle } from "@tabler/icons-react";
import { useState } from "react";

/**
 * A small info icon whose explanation can be **tapped** open, not only hovered.
 *
 * A phone has no hover, so a sentence that only ever appears on `mouseenter` is,
 * on the device this app is mostly read on, not written at all. Worse, when a
 * `Tooltip` is wrapped around a *control* — a switch, a segmented filter — the
 * one gesture a touch user could try is the one that operates the control: you
 * ask "what does this do?" by doing it, and the answer never appears.
 *
 * This is the icon half of `HintLabel` (`StackOptionControl.tsx`), which fixed
 * exactly that for every descriptor-driven option in v0.374.11. It is lifted out
 * so a control the app lays out itself can put the same affordance *beside* the
 * control instead of inside its `<label>` — same words, same gestures, and no
 * change to the control's own accessible name.
 *
 * Nothing changes for a mouse: hovering opens the same tooltip with the same
 * words, and the button carries no padding, so no row gets taller (the standing
 * "the pages are extremely busy" priority). Keyboard users get it too — the icon
 * is focusable, and focus opens the hint.
 */
export function HintIcon({ hint, position = "top-start" }: {
  hint: string;
  /** Where the bubble sits, for an icon near the right edge of the screen. */
  position?: "top-start" | "top-end" | "bottom-start" | "bottom-end" | "top";
}) {
  // Two reasons a hint can be showing, kept apart so a pointer leaving doesn't
  // dismiss one the user deliberately tapped open. Blur closes both: on touch,
  // tapping anything else takes focus away, which is how a tapped hint is
  // dismissed without a second, precise tap on a 14 px target.
  const [tapped, setTapped] = useState(false);
  const [pointed, setPointed] = useState(false);
  return (
    <Tooltip label={hint} multiline w={260} withArrow position={position}
      opened={tapped || pointed}>
      <UnstyledButton
        // A <span> carrying the role explicitly, not a <button>: `HintLabel`
        // renders this inside a control's own <label>, where a <button> is a
        // *labelable* element and would make the field's label name two controls
        // at once. Beside a control that is not the case, but one shape for both
        // keeps the two from drifting into two different affordances.
        component="span" role="button" tabIndex={0}
        // Deliberately generic rather than naming the control: the control's own
        // label is how it is found, by a screen reader and by a test alike, so
        // repeating it here would collide with it.
        aria-label="What does this do?"
        onClick={(e) => {
          // Harmless beside a control; load-bearing inside a <label>, where the
          // tap would otherwise be forwarded to the control it labels — reading
          // the hint would change the setting.
          e.preventDefault();
          setTapped((open) => !open);
        }}
        onKeyDown={(e) => {
          if (e.key !== "Enter" && e.key !== " ") return;
          e.preventDefault();   // Space would scroll the panel
          setTapped((open) => !open);
        }}
        onMouseEnter={() => setPointed(true)}
        onMouseLeave={() => setPointed(false)}
        onFocus={() => setPointed(true)}
        onBlur={() => { setPointed(false); setTapped(false); }}
        style={{ display: "inline-flex", lineHeight: 0, flexShrink: 0,
          cursor: "pointer" }}
      >
        <IconInfoCircle size={14} color="var(--mantine-color-dimmed)" />
      </UnstyledButton>
    </Tooltip>
  );
}
