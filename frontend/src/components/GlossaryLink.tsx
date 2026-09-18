import { Anchor, Tooltip } from "@mantine/core";
import { IconBook2 } from "@tabler/icons-react";
import { Link } from "react-router-dom";

/**
 * "What does this word mean?" — a link from a control to the glossary entry that
 * explains the *concept* it acts on.
 *
 * `seestack/data/glossary.md` opens by promising exactly this: *"every entry has
 * its own link — so a screen that uses a word can point straight at the word,
 * and nobody has to leave the app to understand something on screen."* Until now
 * one screen did (`FrameColumnGuide` → `/glossary#fwhm`); everywhere else the
 * glossary was a nav item you had to know to go and look for, which is no use to
 * the person who does not yet know the word they are stuck on.
 *
 * **Why it is a second glyph beside `HintIcon` rather than a longer tooltip.**
 * They answer different questions. `help` says what *this control does to your
 * picture* ("Reject per-pixel outliers (satellites, cosmic rays, planes)"); the
 * glossary says what *sigma clipping is*, in a paragraph, with when to use it.
 * A tooltip cannot hold the second — and it cannot hold a link either: Mantine's
 * closes on `pointerleave`, so anything clickable inside one is unreachable with
 * a mouse and, on a phone, gone before a finger arrives.
 *
 * **And why it is a glyph rather than an underlined label.** `HintLabel` renders
 * inside the control's own `<label>`, where a click on a link is *forwarded to
 * the control it labels* — the v0.374.11 trap, one level along: asking what a
 * word means would flip the setting. A plain `<a>` has no such default, and it
 * carries no padding, so no row gets taller (the standing "the pages are
 * extremely busy" priority, AGENTS.md §1).
 *
 * Self-hiding: a control whose descriptor carries no slug — most of them, and
 * every one served by an older backend — renders exactly as it did before.
 */
export function GlossaryLink({ slug, term }: {
  slug: string;
  /** The word being explained, for the tooltip and the accessible name. */
  term: string;
}) {
  return (
    <Tooltip label={`What is ${term.toLowerCase()}? Opens the glossary`}
      withArrow position="top-start" multiline w={240}>
      <Anchor
        component={Link}
        to={`/glossary#${slug}`}
        // Deliberately not the control's own label as the accessible name: the
        // label is how a screen reader and a test find the *control*, so
        // repeating it here would give the page two things with one name.
        aria-label={`What is ${term.toLowerCase()}?`}
        data-testid={`glossary-link-${slug}`}
        // Inside a <label>, a click is forwarded to the control unless it is
        // stopped — the same fact `HintIcon` documents. An <a> navigates on its
        // own, so the forwarded click would *also* toggle the setting on the way
        // out.
        onClick={(e) => e.stopPropagation()}
        style={{ display: "inline-flex", lineHeight: 0, flexShrink: 0 }}
      >
        <IconBook2 size={14} color="var(--mantine-color-dimmed)" />
      </Anchor>
    </Tooltip>
  );
}
