import { Tooltip, type TooltipProps } from "@mantine/core";
import { cloneElement, useState, type ReactElement } from "react";

/**
 * A `Tooltip` whose explanation a **tap** can open — for a chip or read-out that
 * is not itself a control.
 *
 * A phone has no hover, and Mantine's `Tooltip` ships
 * `events={{ hover: true, focus: false, touch: false }}`: it opens on
 * `mouseenter` and on nothing else. So a badge whose entire meaning lives in its
 * tooltip — "Cleanest", "Hazy night", "Noise 0.021", "✨ sharpest yet" — is, on
 * the device this app is mostly read on, a word with no explanation anywhere.
 * Turning Mantine's `touch` event on is not the fix: floating-ui opens on
 * `pointerenter` and closes again on the `pointerleave` a lifted finger fires,
 * so the answer flashes and goes.
 *
 * This is the same controlled-tooltip affordance the app already uses for its
 * *controls* — `HintIcon` (v0.402.1) and `HintLabel` (v0.374.11) — applied to
 * the other half of the class: an anchor with no behaviour of its own to
 * collide with, so the tap can simply toggle the hint. The anchor keeps its own
 * markup (this clones the child rather than wrapping it in a box), so no row
 * moves and no page gets taller — the standing "the pages are extremely busy"
 * priority.
 *
 * Nothing changes for a mouse: hovering opens the same tooltip with the same
 * words. Keyboard users gain it for the first time — the anchor becomes
 * focusable, which is a real cost on a list of cards (one tab stop per chip) and
 * is taken deliberately: `role="button"` without keyboard operation would be
 * worse than either, and the chips these wrap are content a reader may well want
 * to ask about.
 */
export function HintAnchor(
  { children, ...tooltip }:
    Omit<TooltipProps, "opened" | "children"> & { children: ReactElement },
) {
  // Two reasons a hint can be showing, kept apart so a pointer leaving doesn't
  // dismiss one the user deliberately tapped open. Blur closes both: on touch,
  // tapping anything else takes focus away, which is how a tapped hint is
  // dismissed without a second, precise tap on a small chip.
  const [tapped, setTapped] = useState(false);
  const [pointed, setPointed] = useState(false);
  const own = children.props as Record<string, unknown> & {
    role?: string;
    tabIndex?: number;
    onClick?: (e: React.MouseEvent) => void;
    onKeyDown?: (e: React.KeyboardEvent) => void;
    onMouseEnter?: (e: React.MouseEvent) => void;
    onMouseLeave?: (e: React.MouseEvent) => void;
    onFocus?: (e: React.FocusEvent) => void;
    onBlur?: (e: React.FocusEvent) => void;
  };
  const anchor = cloneElement(children, {
    // `role`/`tabIndex` are what make the tap reach us at all on iOS Safari,
    // which does not dispatch `click` on a plain `<div>`/`<span>`. The site's
    // own value wins if it set one.
    role: own.role ?? "button",
    tabIndex: own.tabIndex ?? 0,
    onClick: (e: React.MouseEvent) => {
      e.preventDefault();
      setTapped((open) => !open);
      own.onClick?.(e);
    },
    onKeyDown: (e: React.KeyboardEvent) => {
      own.onKeyDown?.(e);
      if (e.key !== "Enter" && e.key !== " ") return;
      e.preventDefault();   // Space would scroll the page
      setTapped((open) => !open);
    },
    onMouseEnter: (e: React.MouseEvent) => { setPointed(true); own.onMouseEnter?.(e); },
    onMouseLeave: (e: React.MouseEvent) => { setPointed(false); own.onMouseLeave?.(e); },
    onFocus: (e: React.FocusEvent) => { setPointed(true); own.onFocus?.(e); },
    onBlur: (e: React.FocusEvent) => {
      setPointed(false);
      setTapped(false);
      own.onBlur?.(e);
    },
  });
  return <Tooltip {...tooltip} opened={tapped || pointed}>{anchor}</Tooltip>;
}
