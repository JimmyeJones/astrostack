import { Alert, Button, Text } from "@mantine/core";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../../api/client";
import { loadDismissedSig, saveDismissedSig } from "../../dismissal";
import { settingsLink } from "../../settingsSections";
import { NoticeBoard, NOTICE_PRIORITY } from "../NoticeBoard";
import { ClosingSeasonNote } from "../ClosingSeasonNote";
import { astapReadiness, astapReadinessSignature } from "./astapReadiness";
import { folderNoticeText, folderReadiness, folderReadinessSignature } from "./folderReadiness";
import { MissingFilesNote } from "./MissingFilesNote";
import { IncomingLagNote } from "./IncomingLagNote";
import { StuckImportNote } from "./StuckImportNote";
import { NewSubsWaitingNote } from "./NewSubsWaitingNote";
import { OverTrimmedNote } from "./OverTrimmedNote";
import { StackFailuresNote } from "./StackFailuresNote";
import { AutoEditOffNote } from "./AutoEditOffNote";
import { AutoStackOffNote } from "./AutoStackOffNote";
import { UnexportedEditsNote } from "./UnexportedEditsNote";

// Dismissal of the first-run readiness banners, keyed to the *specific* problem
// so dismissing one never suppresses a genuinely different (or returning) one:
// we store the current readiness *signature* rather than a bare boolean, and a
// banner reappears whenever the live signature differs from the dismissed one.
// A banner also self-clears once the problem is fixed (readiness → ready → no
// signature). localStorage-only and defensively guarded so a disabled/broken
// store never breaks the page.
const ASTAP_DISMISS_KEY = "astrostack.dashboard.astapBannerDismissed";
const FOLDER_DISMISS_KEY = "astrostack.dashboard.folderBannerDismissed";

/**
 * The Dashboard's one notice board: every setup problem, fault and offer the
 * home page can raise, prioritised, with the top two inline and the rest folded
 * behind "N more notes".
 *
 * Split out of `routes/Dashboard.tsx` for the owner's "recursive organization"
 * ask (2026-11-17): it is the first of the page's five top-level groups. A later
 * Dashboard warning joins the board here; it never becomes a banner of its own.
 */
export function DashboardNotices() {
  const system = useQuery({ queryKey: ["system"], queryFn: api.getSystem, staleTime: 60_000 });
  const [astapDismissedSig, setAstapDismissedSig] = useState(() => loadDismissedSig(ASTAP_DISMISS_KEY));
  const [folderDismissedSig, setFolderDismissedSig] = useState(() => loadDismissedSig(FOLDER_DISMISS_KEY));

  const solve = astapReadiness(system.data?.astap);
  const folders = folderReadiness(system.data?.folders);
  const astapSig = astapReadinessSignature(solve);
  const folderSig = folderReadinessSignature(folders);

  return (
    // `display: contents`: the board keeps its own spacing and place on the page;
    // the wrapper only names it as one of the Dashboard's top-level groups.
    <div data-dashboard-group="notices" style={{ display: "contents" }}>
      <NoticeBoard
        headlinesFrom={NOTICE_PRIORITY.advisory}
        data-testid="dashboard-notes"
        items={[
          { key: "folders", priority: NOTICE_PRIORITY.blocking,
            node: !folders.ready && (folders.kind === "layout" || folderSig !== folderDismissedSig) ? (
              // The nested layout is not dismissable: while it is set the server
              // refuses deletes and scans, and this is the only place that says why.
              <Alert color={folders.kind === "layout" ? "red" : "yellow"} variant="light"
                data-testid="folder-notice"
                withCloseButton={folders.kind !== "layout"}
                onClose={() => {
                  if (folderSig) { setFolderDismissedSig(folderSig); saveDismissedSig(FOLDER_DISMISS_KEY, folderSig); }
                }}
                title={folderNoticeText(folders).title}>
                <Text size="sm">{folderNoticeText(folders).body}</Text>
                <Button component={Link} to={settingsLink("folders")} size="xs" variant="light"
                  color={folders.kind === "layout" ? "red" : "yellow"} mt="xs">
                  Fix in Settings
                </Button>
              </Alert>
            ) : null },
          { key: "astap", priority: NOTICE_PRIORITY.warning,
            node: !solve.ready && astapSig !== astapDismissedSig ? (
              <Alert color="yellow" variant="light"
                withCloseButton
                onClose={() => {
                  if (astapSig) { setAstapDismissedSig(astapSig); saveDismissedSig(ASTAP_DISMISS_KEY, astapSig); }
                }}
                title={solve.kind === "astap" && solve.cannotRun
                  ? "ASTAP is there but can't be started"
                  : solve.kind === "astap"
                  ? "Plate-solving isn't set up yet"
                  : "Plate-solving needs a star database"}>
                <Text size="sm">
                  {solve.kind === "astap" && solve.cannotRun
                    ? "Solving gives every frame sky coordinates, and it's required before you "
                      + "can stack anything. ASTAP (the plate-solver) was found, but it won't "
                      + "start — check the file is executable and built for this machine."
                    : solve.kind === "astap"
                    ? "Solving gives every frame sky coordinates, and it's required before you "
                      + "can stack anything. ASTAP (the plate-solver) wasn't found, so set it up "
                      + "before you drop in frames."
                    : "ASTAP was found, but it has no star database to match against — solving "
                      + "needs one, and solving is required before you can stack. Add a star "
                      + "database before you drop in frames."}
                </Text>
                <Button component={Link} to={settingsLink("plate-solving")} size="xs" variant="light" color="yellow" mt="xs">
                  Fix in Settings
                </Button>
              </Alert>
            ) : null },
          // A live storage fault, and one the app is otherwise silent about:
          // the frames are all still listed, so nothing looks wrong until a
          // walk-away stack comes out thin. Ranked with the other warnings and
          // below the blocking folder problem, which is the same fault's
          // louder cousin. Self-hiding at zero.
          { key: "missing-files", priority: NOTICE_PRIORITY.warning,
            node: <MissingFilesNote /> },
          // The one serial worker holding the import back. Same rung and the
          // same shape of silence as its neighbour above: nothing looks wrong —
          // every target keeps the frame count it had — while the last nights
          // of shooting simply are not in the library. Self-hiding on a healthy
          // queue, which is every ordinary minute.
          { key: "stuck-import", priority: NOTICE_PRIORITY.warning,
            node: <StuckImportNote /> },
          // The same silence, measured from the other end: files in `incoming/`
          // the library has no row for, whether or not anything was ever queued.
          // Ranked just below the queue note because when both fire they are the
          // same event and the queued job is the more actionable half — it names
          // what is holding the worker. Self-hiding at zero and while a night is
          // still arriving, which is every ordinary install.
          { key: "incoming-lag", priority: NOTICE_PRIORITY.warning,
            node: <IncomingLagNote /> },
          // A target that stopped producing pictures. Same rung as the other
          // warnings: nothing is corrupt, but the walk-away workflow the owner
          // relies on has quietly stopped delivering for that target, and the
          // engine's refusal names the one setting that would fix it. Self-hiding
          // at zero, which is every healthy install.
          { key: "stack-failures", priority: NOTICE_PRIORITY.warning,
            node: <StackFailuresNote /> },
          // Advisory, and the reason this board exists: work of the user's that
          // the app isn't showing anywhere. Self-hiding at zero, so on an
          // ordinary install it costs nothing and the board folds nothing.
          { key: "unexported-edits", priority: NOTICE_PRIORITY.advisory,
            node: <UnexportedEditsNote /> },
          // Not a fault — an offer. `auto_stack` ships on, but an install that
          // has ever run carries an explicit `false` no upgrade may overwrite
          // (§9), so the whole walk-away chain waits on one switch nothing in
          // the app ever mentioned. Speaks only on a night that was captured and
          // stacked nothing, and never again once dismissed.
          { key: "auto-stack-off", priority: NOTICE_PRIORITY.advisory,
            node: <AutoStackOffNote /> },
          // The same offer for the step *after* stacking. Ranked just below its
          // sibling because the two are sequential: with auto-stack off there is
          // nothing to finish, and this note stays silent until the scan really
          // has stacked something and left it as a linear master.
          { key: "auto-edit-off", priority: NOTICE_PRIORITY.advisory,
            node: <AutoEditOffNote /> },
          // The same shape for the other direction: not work of theirs the app
          // isn't showing, but light of theirs the picture doesn't have yet.
          // The Target page has said this per target since v0.90.0; with
          // auto-stack off and a target per object, the library-wide question
          // ("which one do I open?") had no answer anywhere. Self-hiding at
          // zero, so a fully-stacked library costs nothing and folds nothing.
          { key: "new-subs-waiting", priority: NOTICE_PRIORITY.advisory,
            node: <NewSubsWaitingNote /> },
          // Not an offer but a *fault*, so it outranks the two above: an older
          // build's border trim is still cropping finished pictures to a sliver,
          // because the crop it chose lives in each run's saved recipe and
          // nothing re-derives that. The per-picture note is in the editor; this
          // is the "which ones?" the owner had no surface for after upgrading.
          { key: "over-trimmed", priority: NOTICE_PRIORITY.warning,
            node: <OverTrimmedNote /> },
          // An offer with a deadline, which is why it is here at all rather than
          // only on the planner: a target whose season ends this week is gone
          // for a year if the next clear night goes elsewhere. Ranked with the
          // other offers — nothing is broken — and deliberately narrow: only the
          // last week or so speaks here (`CLOSING_URGENT_WEEKS`), the rest of
          // the season stays on Tonight's own card. Self-hiding most of the year.
          { key: "closing-season", priority: NOTICE_PRIORITY.advisory,
            node: <ClosingSeasonNote /> },
        ]}
      />
    </div>
  );
}
