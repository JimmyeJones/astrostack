/** The Stack form's notice board: the shared `<Alert>` board under its first
 *  caller's names (moved to ``components/AlertNoticeBoard.tsx`` in v0.507.9 so
 *  the Editor can use the same one). */
export {
  AlertNoticeBoard as StackNoticeBoard,
  JUST_DONE_PRIORITY,
  type AlertNotice as StackNotice,
  type AlertNoticeFix as StackNoticeFix,
} from "../AlertNoticeBoard";
