import { Alert, Box, Button, type MantineSpacing, Text } from "@mantine/core";
import type { ReactNode } from "react";
import { NoticeBoard, NOTICE_PRIORITY } from "./NoticeBoard";

/** One rung above ``blocking``: the confirmation of a click the reader has just
 *  made, carrying its Undo. It must never fold behind "N more notes" — the Undo
 *  is only useful while the reader still remembers what they clicked. */
export const JUST_DONE_PRIORITY = NOTICE_PRIORITY.blocking - 5;

/** The button most Stack-form notes carry: the one setting change it is about. */
export type AlertNoticeFix = {
  label: ReactNode;
  onClick: () => void;
  loading?: boolean;
  leftSection?: ReactNode;
  /** Omitted = the app's primary colour, as the form's buttons always were. */
  color?: string;
};

/**
 * One Stack-form note. Most say one sentence and offer one fix, so ``text`` +
 * ``fix`` cover them; ``body`` replaces the sentence outright for a note whose
 * wording carries links or several paragraphs, and ``extra`` is appended below
 * for anything else (a second button, a dimmed footnote).
 */
export type AlertNotice = {
  key: string;
  priority: number;
  color: string;
  title?: ReactNode;
  icon?: ReactNode;
  text?: ReactNode;
  body?: ReactNode;
  fix?: AlertNoticeFix | null;
  extra?: ReactNode;
  /** A close button that dismisses the note (the editor's "What Auto-process
   *  did" summary is the reader's to put away). */
  onClose?: () => void;
  /** ``data-testid`` on the note's own Alert, for a note tests look up by id. */
  testId?: string;
  /** Padding for a titled note that sits somewhere dense (a Jobs row) and
   *  kept Alert's ``p="xs"`` before it moved onto a board. */
  p?: MantineSpacing;
};

/**
 * One note drawn as the `<Alert>` every {@link AlertNoticeBoard} uses, for a
 * page whose own board mixes these with self-hiding note components (the
 * Target page's ``target-notes`` and its Auto-grade dialog, v0.507.11). The
 * board below is this plus the folding; a caller that already has a
 * {@link NoticeBoard} hands it ``node: cond ? alertNoticeNode({...}) : null``.
 */
export function alertNoticeNode(n: AlertNotice) {
  return (
    <Alert
      color={n.color}
      variant="light"
      title={n.title}
      icon={n.icon}
      // A titled note is a page-level one and keeps Alert's own spacing;
      // the one-sentence form notes stay compact, as they always were.
      {...(n.p != null ? { p: n.p } : n.title ? {} : { py: 6, px: "sm" })}
      data-notice={n.key}
      data-testid={n.testId}
      withCloseButton={Boolean(n.onClose)}
      onClose={n.onClose}
    >
      {n.body ?? (n.text != null ? <Text size="xs">{n.text}</Text> : null)}
      {n.fix ? (
        <Button
          size="compact-xs"
          variant="light"
          color={n.fix.color}
          mt={6}
          loading={n.fix.loading}
          leftSection={n.fix.leftSection}
          onClick={n.fix.onClick}
        >
          {n.fix.label}
        </Button>
      ) : null}
      {n.extra}
    </Alert>
  );
}

/**
 * A notice board of `<Alert>` notes — first written for the Stack form, now
 * shared with the Editor (v0.507.9).
 *
 * The Stack form's notice boards. The form used to put each of its ~40 notes —
 * calibration mismatches, rejection advice, drizzle nudges, the auto-grade offer
 * — on screen as an always-on `<Alert>` of its own, so a target with a few
 * imperfect masters and a streaky night opened onto a wall of coloured boxes
 * above "Start stacking" (owner, 2026-11-17: "simplicity is sometimes best — or
 * at least recursive organization"). Each group of the form now hands its notes
 * to one board: the most important one or two stay inline (a red "this will
 * fail" always outranks a blue "you could also…"), the rest fold behind "N more
 * notes", and nothing is removed — every note and every fix button is one click
 * away.
 *
 * ``items`` may hold ``null``s so a caller can list every possible note with its
 * condition inline, the same way the form used to write them.
 */
export function AlertNoticeBoard({
  items,
  mt,
  mb,
  "data-testid": testId,
}: {
  items: (AlertNotice | null | false | undefined)[];
  /** Spacing around the board, applied only when it has a note to show — an
   *  empty board must not leave a gap where its notes would have been. */
  mt?: string | number;
  mb?: string | number;
  "data-testid"?: string;
}) {
  const live = items.filter((n): n is AlertNotice => Boolean(n));
  if (!live.length) return null;
  const board = (
    <NoticeBoard
      data-testid={testId}
      items={live.map((n) => ({
        key: n.key,
        priority: n.priority,
        node: alertNoticeNode(n),
      }))}
    />
  );
  return mt != null || mb != null ? <Box mt={mt} mb={mb}>{board}</Box> : board;
}
