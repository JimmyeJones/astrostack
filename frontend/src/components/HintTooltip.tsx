import { Tooltip } from "@mantine/core";
import type { FloatingPosition } from "@mantine/core";
import { cloneElement, useState } from "react";
import type { ReactElement } from "react";

/**
 * A tooltip whose words can be **tapped** open, wrapped around a trigger that
 * does nothing else.
 *
 * A phone has no hover, so a sentence that only ever appears on `mouseenter`
 * is, on the device this app is mostly read on, not written at all. `HintIcon`
 * (and `HintLabel` before it) fixed that for an explanation sitting *beside a
 * control*: there the tap leaked into the control, so reading the hint changed
 * the setting.
 *
 * A `Badge` is the other half of the same class and the worse one. It is not a
 * control at all — a badge saying "Hazy night", "seams flat" or "24 streaked"
 * has no action to leak into, so on a touch device there is no gesture that
 * reveals its meaning and none that could be. Several of them even set
 * `cursor: "help"`, an affordance a phone cannot render. The word is on the
 * screen and the only sentence explaining it is unreachable.
 *
 * So this is the same state machine as `HintIcon` — shared with it through
 * {@link useHintDisclosure}, so the two cannot drift into two different
 * gestures — attached to the caller's own trigger instead of to an icon:
 *
 *   - **tap** opens it, and tapping again (or touching anything else, which
 *     takes focus away) dismisses it;
 *   - **hover** is byte-for-byte what it was, so nothing changes for a mouse;
 *   - **focus / Enter / Space** open it, so a keyboard reaches it for the first
 *     time.
 *
 * Nothing is added to the page: no icon, no prose, no padding — the trigger is
 * the badge that was already there, which is what the standing "the pages are
 * extremely busy" priority requires of a friendliness fix.
 *
 * **Only for a trigger with no action of its own.** Wrapping a `Button` or an
 * `ActionIcon` in this would make one tap both open the hint and run the
 * button; those sites want `HintIcon` beside the control instead.
 */

/** The two reasons a hint can be showing, and the props that drive them.
 *
 * They are kept apart so a pointer leaving does not dismiss one the user
 * deliberately tapped open. Blur closes both: on touch, tapping anything else
 * takes focus away, and that is how a tapped hint is dismissed without a
 * second, precise tap on a small target.
 */
export function useHintDisclosure({ preventDefault = false }: {
  /** Call `preventDefault()` on the click. Load-bearing when the trigger sits
   * inside a control's `<label>` (`HintIcon`), where the tap would otherwise be
   * forwarded to the control it labels; harmless elsewhere. */
  preventDefault?: boolean;
} = {}) {
  const [tapped, setTapped] = useState(false);
  const [pointed, setPointed] = useState(false);
  const toggle = () => setTapped((open) => !open);
  return {
    opened: tapped || pointed,
    triggerProps: {
      onClick: (e: { preventDefault: () => void }) => {
        if (preventDefault) e.preventDefault();
        toggle();
      },
      onKeyDown: (e: { key: string; preventDefault: () => void }) => {
        if (e.key !== "Enter" && e.key !== " ") return;
        e.preventDefault();   // Space would scroll the page
        toggle();
      },
      onMouseEnter: () => setPointed(true),
      onMouseLeave: () => setPointed(false),
      onFocus: () => setPointed(true),
      onBlur: () => { setPointed(false); setTapped(false); },
    },
  };
}

type AnyHandler = ((e: never) => void) | undefined;

/** Run the trigger's own handler, if it had one, and then ours. */
function compose(theirs: AnyHandler, ours: (e: never) => void) {
  if (!theirs) return ours;
  return (e: never) => { theirs(e); ours(e); };
}

export function HintTooltip({ label, children, w, multiline, withArrow,
  position, openDelay, disabled }: {
  /** `null` reads as "nothing to say" and pairs with `disabled`, so a caller
   * whose sentence is conditional does not have to invent an empty one. */
  label: string | null;
  /** The trigger. Must be a single element with no action of its own. */
  children: ReactElement;
  /** No hint to show — the trigger stays exactly the element it was, with no
   * role, no tab stop and nothing to tap, so a badge with nothing to say does
   * not advertise itself as answerable. */
  disabled?: boolean;
  // The presentation props are pass-through with **no defaults of their own**:
  // every call site keeps the bubble it already had, so this change is about the
  // gestures that reach the words and nothing else.
  w?: number;
  multiline?: boolean;
  withArrow?: boolean;
  position?: FloatingPosition;
  openDelay?: number;
}) {
  const { opened, triggerProps } = useHintDisclosure();
  const off = disabled || !label;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const own = (children.props ?? {}) as Record<string, any>;
  const trigger = off ? children : cloneElement(children, {
    // A focusable, button-roled trigger: the badge's own text is its accessible
    // name, so — unlike `HintIcon`, which needs a generic one — nothing has to
    // be invented here, and nothing that looks the badge up by its words has to
    // know the hint exists.
    role: own.role ?? "button",
    tabIndex: own.tabIndex ?? 0,
    onClick: compose(own.onClick, triggerProps.onClick as (e: never) => void),
    onKeyDown: compose(own.onKeyDown, triggerProps.onKeyDown as (e: never) => void),
    onMouseEnter: compose(own.onMouseEnter, triggerProps.onMouseEnter),
    onMouseLeave: compose(own.onMouseLeave, triggerProps.onMouseLeave),
    onFocus: compose(own.onFocus, triggerProps.onFocus),
    onBlur: compose(own.onBlur, triggerProps.onBlur),
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
  } as any);
  return (
    <Tooltip label={label ?? ""} multiline={multiline} w={w} withArrow={withArrow}
      position={position} openDelay={openDelay} disabled={off}
      opened={off ? false : opened}>
      {trigger}
    </Tooltip>
  );
}
