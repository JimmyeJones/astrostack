import {
  ActionIcon, Alert, Badge, Box, Button, Center, Grid, Group, HoverCard, Image,
  Loader, Menu, Modal, NumberFormatter, NumberInput, Paper, Progress, Select, Stack,
  Table, TagsInput, Text, Textarea, Title, Tooltip,
} from "@mantine/core";
import {
  IconAlertTriangle, IconArrowBackUp, IconCheck, IconChevronDown, IconClock,
  IconDeviceFloppy, IconDeviceMobile, IconDownload, IconHistory,
  IconNotes, IconPhoto, IconPhotoDown, IconSparkles, IconStack2, IconTelescope,
  IconTargetArrow, IconVideo, IconWand, IconX,
} from "@tabler/icons-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState, type CSSProperties } from "react";
import { Link, useParams } from "react-router-dom";
import { notifications } from "@mantine/notifications";
import { api, type Frame } from "../api/client";
import { fullResPngLabel } from "../fullres";
import { formatCaptureNights, formatIntegration } from "../format";
import { integrationReadiness, readinessColor, noiseReductionHint } from "../readiness";
import { QueryError } from "../components/QueryError";
import { settingsLink } from "../settingsSections";
import { AutoStackHoldNote } from "../components/AutoStackHoldNote";
import { CaptureQuietNote } from "../components/CaptureQuietNote";
import { CleanestShotNote } from "../components/CleanestShotNote";
import { GrainierNewestNote } from "../components/GrainierNewestNote";
import { NoticeBoard, NOTICE_PRIORITY } from "../components/NoticeBoard";
import { RestackGainNote } from "../components/RestackGainNote";
import { StackFailedNote } from "../components/target/StackFailedNote";
import { ObjectInfoCard, describeObject } from "../components/ObjectInfoCard";
import { InsightTabs } from "../components/InsightTabs";
import { NightsCard } from "../components/NightsCard";
import { estimateClearNights } from "../components/clearNights";
import { FocusTrendCard } from "../components/FocusTrendCard";
import { TransparencyTrendCard } from "../components/TransparencyTrendCard";
import { NextSessionCard } from "../components/NextSessionCard";
import { BestMonthsStrip } from "../components/BestMonthsStrip";
import { MoonInterferenceCard } from "../components/MoonInterferenceCard";
import { DeepeningReelCard } from "../components/DeepeningReelCard";
import { SessionRecapCard } from "../components/SessionRecapCard";
import { StackHealthCard } from "../components/StackHealthCard";
import { CalibrationSkippedNote } from "../components/CalibrationSkippedNote";
import { StackNoiseBadge } from "../components/StackNoiseBadge";
import { FirstLookCard } from "../components/FirstLookCard";
import { SampleTourNote } from "../components/SampleTourNote";
import { WallpaperMenuItems } from "../components/WallpaperMenu";
import { SharePictureButton } from "../components/SharePictureButton";
import { ScanToPhoneModal } from "../components/ScanToPhoneButton";
import { keepsakeFilename, sharePictureText } from "../share";
import { detectSolveSetupProblem } from "../components/target/solveSetup";
import { RejectionBreakdown } from "../components/target/RejectionBreakdown";
import { UnsolvedHelp } from "../components/target/UnsolvedHelp";
import { SkyBrightnessNote } from "../components/target/SkyBrightnessNote";
import { thinStackWarning } from "../components/target/thinStack";
import { missingFilesNote } from "../components/target/missingFiles";
import { SharpestYetBadge } from "../components/target/SharpestYetBadge";
import { NextBestMoveBadge } from "../components/target/NextBestMoveBadge";
import { FramingVerdictNote, useStackFraming } from "../components/target/FramingVerdictNote";
import { LatestPictureCard } from "../components/target/LatestPictureCard";
import { FrameColumnGuide } from "../components/target/FrameColumnGuide";
import { FRAME_COLUMNS, type SortKey } from "../components/target/frameColumns";
import { cardGrainProjection } from "../components/target/grainProjection";
import { IntegrationTrendBadge } from "../components/target/IntegrationTrendBadge";
import { nextBestMove } from "../components/target/nextBestMove";
import { softerThanUsual } from "../components/target/softStars";
import { detectMixedPointings } from "../components/target/mixedPointings";
import { DownloadMenuItem } from "../components/DownloadMenuItem";

// Re-exported for existing tests that import it from this route module.
export { describeObject };

const NUM = (v: number | null, digits = 2) =>
  v === null || v === undefined ? "—" : v.toFixed(digits);

// One line of plain-language help under a menu item's label — the wording that
// used to live in each button's hover tooltip, now readable without hovering
// (which a phone can't do anyway). Matches the History card's menus.
const MENU_HINT: CSSProperties = {
  display: "block", fontSize: "0.72rem", opacity: 0.6, whiteSpace: "normal",
};

const REJECT_METRICS = [
  { value: "fwhm_px", label: "FWHM" },
  { value: "eccentricity_median", label: "Eccentricity" },
  { value: "star_count", label: "Star count" },
  { value: "sky_adu_median", label: "Sky level" },
  { value: "transparency_score", label: "Transparency" },
];

// Median of a non-empty numeric array (used for the within-target trailed
// eccentricity outlier count). Sorts a copy, so the input is left untouched.
function medianOf(xs: number[]): number {
  const s = [...xs].sort((a, b) => a - b);
  const mid = Math.floor(s.length / 2);
  return s.length % 2 ? s[mid] : (s[mid - 1] + s[mid]) / 2;
}

// Parse an ISO timestamp to epoch ms, forcing a naive (no-offset) string to UTC
// so a browser in a non-UTC zone doesn't shift it. Frame DATE-OBS and stack-run
// timestamps are both stored timezone-aware ("…+00:00"), but a fits header can
// fall back to a raw naive string, so normalise defensively. NaN on unparseable.
function parseUtcMs(s: string): number {
  const hasTz = /[Zz]$|[+-]\d{2}:?\d{2}$/.test(s);
  return Date.parse(hasTz ? s : s + "Z");
}

// Count accepted, plate-solved frames captured *after* the target's most recent
// genuine stack ran — i.e. subs the current master doesn't yet include. Powers
// the "N new subs since your last stack — restack?" nudge for the multi-night
// Seestar workflow (drop another night in, the old master silently no longer
// reflects all your data). Only accepted+solved frames count, so a pile of
// rejected/unsolved new subs never nags; returns 0 when there's no genuine
// stack timestamp to compare against.
export function countNewSubsSinceStack(
  frames: Frame[],
  latestStackUtc: string | null | undefined,
): number {
  if (!latestStackUtc) return 0;
  const stackMs = parseUtcMs(latestStackUtc);
  if (Number.isNaN(stackMs)) return 0;
  return frames.filter((f) => {
    if (!f.accept || !f.solved || !f.timestamp_utc) return false;
    const t = parseUtcMs(f.timestamp_utc);
    return !Number.isNaN(t) && t > stackMs;
  }).length;
}

// Count frames that couldn't be quality-checked at all — QC raised on them
// (unreadable/corrupt/truncated FITS), so they carry a `qc_error:…` reject
// reason. Such a frame is left `accept=1` but is silently skipped when stacking
// (the stacker can't load it) and — because the reject-summary tallies only
// rejected frames — it never shows in the "why frames were dropped" breakdown,
// so a beginner otherwise gets zero signal that some subs were unreadable. We
// count them regardless of accept state so a later manual reject doesn't hide
// the QC failure. Powers a small "N frames couldn't be quality-checked" callout.
export function countQcUncheckable(frames: Frame[]): number {
  return frames.filter((f) => (f.reject_reason ?? "").startsWith("qc_error")).length;
}

// Turn a raw `reject_reason` (qc:fwhm, bulk:streaked, user, …) into a plain-language
// label so a beginner can see *why* frames were dropped, not just how many.
const METRIC_LABEL: Record<string, string> = {
  fwhm_px: "FWHM", star_count: "star count",
  eccentricity_median: "eccentricity", sky_adu_median: "sky level",
  transparency_score: "transparency",
};
export function rejectReasonLabel(reason: string): string {
  if (reason === "user") return "Manual reject";
  if (reason === "bulk:streaked") return "Streaked (bulk)";
  if (reason === "bulk:trailed") return "Trailed (bulk)";
  if (reason.startsWith("auto:grade:")) {
    const m = reason.slice(11);
    return `Auto-grade: ${METRIC_LABEL[m] ?? m}`;
  }
  if (reason.startsWith("qc:")) {
    const m = reason.slice(3);
    return `QC: ${METRIC_LABEL[m] ?? m}`;
  }
  if (reason.startsWith("bulk:")) {
    const m = reason.slice(5);
    return `Worst ${METRIC_LABEL[m] ?? m} (bulk)`;
  }
  if (reason === "auto:streak") return "Auto: streak";
  if (reason.startsWith("auto:")) {
    const m = reason.slice(5);
    return `Auto: ${METRIC_LABEL[m] ?? m}`;
  }
  if (reason.startsWith("qc_error")) return "QC error";
  if (reason.startsWith("solve_failed")) return "Plate-solve failed";
  return reason;
}

const SENSITIVITIES = [
  { value: "conservative", label: "Conservative — only gross outliers" },
  { value: "balanced", label: "Balanced (recommended)" },
  { value: "aggressive", label: "Aggressive — stricter cut" },
];

// Preview-first auto-grading: shows which accepted frames are statistical
// outliers (and why, in plain language) before anything is rejected.
/** Say, in the auto-grade dialog, that a mosaic's panels are judged against
 * themselves — or nothing at all for an ordinary single-pointing target.
 *
 * Panels are different patches of sky, so a panel pointed at emptier sky
 * legitimately shows fewer stars; grading it against the rest of the target
 * used to read that as cloud and could flag the whole panel. The backend now
 * splits the flux-like metrics per panel and reports how many it found
 * (`pointing_groups`; absent on an older backend, hence the optional). Saying
 * so is the difference between a user trusting the numbers and wondering why
 * one panel is treated differently. */
export function mosaicGradingNote(groups: number | undefined): string | null {
  if (!groups || groups < 2) return null;
  return (
    `This looks like a ${groups}-panel mosaic, so each panel is compared `
    + "against itself — a panel pointed at emptier sky genuinely has fewer "
    + "stars, and that isn't cloud."
  );
}

function AutoGradeModal({
  safe, opened, onClose, onApplied,
}: {
  safe: string;
  opened: boolean;
  onClose: () => void;
  onApplied: (ids: number[]) => void;
}) {
  const [sensitivity, setSensitivity] = useState<string | undefined>(undefined);

  const preview = useQuery({
    queryKey: ["auto-grade", safe, sensitivity ?? "default"],
    queryFn: () => api.autoGradePreview(safe, sensitivity),
    enabled: opened,
  });

  const apply = useMutation({
    mutationFn: () => api.autoGradeApply(safe, sensitivity),
    onSuccess: (r) => {
      const ids = r.changed_ids ?? [];
      notifications.show({
        message: ids.length
          ? `Auto-grade rejected ${ids.length} frame${ids.length === 1 ? "" : "s"}`
          : "Nothing to reject — frames already graded",
        color: "violet",
      });
      onApplied(ids);
      onClose();
    },
    onError: (e: Error) => notifications.show({ message: e.message, color: "red" }),
  });

  const report = preview.data;
  const recs = report?.recommendations ?? [];
  const nothingGradable = report && report.metrics_used.length === 0;

  return (
    <Modal opened={opened} onClose={onClose} title="Auto-grade frames" size="lg">
      <Stack gap="sm">
        <Text size="sm" c="dimmed">
          Compares every accepted frame against this target's typical FWHM, star
          count, sky level, eccentricity and transparency, and flags the clear
          outliers — trailed, cloud-hit or hazy subs. Nothing is rejected until
          you apply, and one click undoes it.
        </Text>
        {mosaicGradingNote(report?.pointing_groups) ? (
          <Text size="sm" c="dimmed">
            {mosaicGradingNote(report?.pointing_groups)}
          </Text>
        ) : null}
        <Select
          label="Sensitivity" size="xs" w={280} allowDeselect={false}
          data={SENSITIVITIES}
          value={sensitivity ?? report?.sensitivity ?? "balanced"}
          onChange={(v) => setSensitivity(v ?? undefined)}
        />
        {preview.isLoading ? (
          <Center h={80}><Loader size="sm" /></Center>
        ) : preview.isError ? (
          <Alert color="red">{(preview.error as Error).message}</Alert>
        ) : nothingGradable ? (
          <Alert color="gray">
            Not enough graded frames to judge — run QC first (each metric needs
            at least 10 measured frames).
          </Alert>
        ) : recs.length === 0 ? (
          <Alert color="teal">
            No outliers found — your {report?.n_accepted ?? 0} accepted frames
            look consistent at this sensitivity.
          </Alert>
        ) : (
          <>
            <Text size="sm">
              <b>{recs.length}</b> of {report?.n_accepted} accepted frames look
              like outliers:
            </Text>
            {report?.capped ? (
              <Alert color="orange" p="xs">
                More frames were flagged than the 25% safety cap allows — only
                the worst are listed. Consider a conservative pass first, or
                review the night's data.
              </Alert>
            ) : null}
            <Table.ScrollContainer minWidth={400} mah={300}>
              <Table striped withTableBorder>
                <Table.Tbody>
                  {recs.map((rec) => (
                    <Table.Tr key={rec.frame_id}>
                      <Table.Td style={{ whiteSpace: "nowrap" }}>
                        <Text size="xs" fw={500}>{rec.name}</Text>
                      </Table.Td>
                      <Table.Td>
                        <Stack gap={2}>
                          {rec.reasons.map((r) => (
                            <Text key={r.metric} size="xs" c="dimmed">{r.label}</Text>
                          ))}
                        </Stack>
                      </Table.Td>
                    </Table.Tr>
                  ))}
                </Table.Tbody>
              </Table>
            </Table.ScrollContainer>
          </>
        )}
        <Group justify="flex-end">
          <Button variant="default" size="xs" onClick={onClose}>Cancel</Button>
          <Button
            size="xs" color="red" loading={apply.isPending}
            disabled={!recs.length}
            onClick={() => apply.mutate()}
          >
            Reject {recs.length || "0"} frame{recs.length === 1 ? "" : "s"}
          </Button>
        </Group>
      </Stack>
    </Modal>
  );
}

function NotesPanel({ safe, notes, tags }: { safe: string; notes: string | null; tags: string[] }) {
  const qc = useQueryClient();
  const [noteText, setNoteText] = useState(notes ?? "");
  const [tagList, setTagList] = useState<string[]>(tags);

  // Re-sync when the loaded target changes (e.g. navigating between targets).
  useEffect(() => { setNoteText(notes ?? ""); setTagList(tags); }, [safe, notes, tags]);

  const save = useMutation({
    mutationFn: () => api.patchTarget(safe, { notes: noteText, tags: tagList }),
    onSuccess: () => {
      notifications.show({ message: "Notes saved", color: "teal" });
      qc.invalidateQueries({ queryKey: ["target", safe] });
      qc.invalidateQueries({ queryKey: ["targets"] });
    },
    onError: (e: Error) => notifications.show({ message: e.message, color: "red" }),
  });

  const dirty = noteText !== (notes ?? "") || tagList.join("\u0000") !== tags.join("\u0000");

  return (
    <Paper withBorder p="md">
      <Group gap={6} mb="xs">
        <IconNotes size={16} />
        <Text fw={600}>Notes &amp; tags</Text>
      </Group>
      <TagsInput
        label="Tags" placeholder="Add a tag…" value={tagList} onChange={setTagList}
        clearable mb="sm"
      />
      <Textarea
        label="Notes" placeholder="Acquisition notes, conditions, ideas…"
        autosize minRows={2} maxRows={8}
        value={noteText} onChange={(e) => setNoteText(e.currentTarget.value)}
      />
      <Group justify="flex-end" mt="sm">
        <Button size="xs" leftSection={<IconDeviceFloppy size={14} />}
          disabled={!dirty} loading={save.isPending} onClick={() => save.mutate()}>
          Save
        </Button>
      </Group>
    </Paper>
  );
}

export function TargetView() {
  const { safe = "" } = useParams();
  const qc = useQueryClient();
  const [sort, setSort] = useState<SortKey>("id");
  const [order, setOrder] = useState<"asc" | "desc">("asc");
  const [selected, setSelected] = useState<number | null>(null);
  const [bayer, setBayer] = useState<string | undefined>(undefined);
  const [rejectMetric, setRejectMetric] = useState("fwhm_px");
  const [rejectPct, setRejectPct] = useState(10);
  // Inline editor for the "Is it enough yet?" integration goal (hours).
  const [editingGoal, setEditingGoal] = useState(false);
  const [goalHoursInput, setGoalHoursInput] = useState<number | "">("");
  // Ids touched by the last bulk *reject* so we can offer a one-click undo of an
  // over-aggressive cut (a 30% reject_worst, or reject_streaked that went too far).
  const [lastReject, setLastReject] = useState<{ ids: number[]; label: string } | null>(null);
  const [gradeOpen, setGradeOpen] = useState(false);
  // The "To phone" QR. It lives on the page rather than inside the Save / share
  // menu item that opens it, because the menu closes on click — a popover owned
  // by the item would be unmounted with the dropdown before it could be read.
  const [toPhone, setToPhone] = useState(false);

  const target = useQuery({ queryKey: ["target", safe], queryFn: () => api.getTarget(safe) });
  // "What am I looking at?" — an offline catalog lookup that turns a bare folder
  // name (or the solved centre) into friendly context. Renders nothing on no match.
  const identity = useQuery({
    queryKey: ["identify", safe],
    queryFn: () => api.identifyTarget(safe),
  });
  // The user's own integration goal for this target (opt-in). null → the
  // readiness card uses its sane per-object-type default.
  const goal = useQuery({
    queryKey: ["integration-goal", safe],
    queryFn: () => api.getIntegrationGoal(safe),
  });
  // Night-by-night accrual, newest first — the same query the Nights card runs
  // (identical key, so TanStack serves one request to both). Feeds the "how many
  // more clear nights?" estimate under the readiness verdict.
  const nights = useQuery({
    queryKey: ["nights", safe],
    queryFn: () => api.targetNights(safe),
  });
  const setGoal = useMutation({
    mutationFn: (goalS: number | null) => api.setIntegrationGoal(safe, goalS),
    onSuccess: (r) => {
      qc.setQueryData(["integration-goal", safe], r);
      notifications.show({
        message: r.goal_s ? "Saved your integration goal" : "Cleared your goal",
        color: "violet",
      });
    },
  });
  const rejectedCount = target.data
    ? target.data.n_frames - target.data.n_frames_accepted
    : 0;
  // Fetch the why-breakdown once the target is loaded: it also surfaces accepted
  // subs that haven't plate-solved yet (silently excluded from the stack), which
  // aren't visible from the target's accepted/rejected counts alone.
  const rejectSummary = useQuery({
    queryKey: ["reject-summary", safe],
    queryFn: () => api.rejectSummary(safe),
    enabled: !!target.data,
  });
  // Accepted-but-not-yet-solved subs the stacker can't use — the honest count
  // behind a thin/gibberish stack. Comes from the breakdown's "unsolved" bucket.
  const unsolvedCount =
    rejectSummary.data?.summary?.buckets.find((b) => b.key === "unsolved")
      ?.count ?? 0;
  // Accepted subs whose files aren't on disk right now (offline share, unmounted
  // drive, cleared cache with the originals gone). They're silently skipped when
  // stacking, so without this the user only finds out an hour later, from a thin
  // result. Self-hides when nothing is missing or an older backend omits the counts.
  const missingFiles = missingFilesNote(
    rejectSummary.data?.n_missing_files,
    rejectSummary.data?.n_accepted,
  );
  // "Was last night's sky bright?" — the honest explanation for a washed-out
  // result. Self-hiding: the endpoint returns null unless it can answer honestly.
  const skyBrightness = useQuery({
    queryKey: ["sky-brightness", safe],
    queryFn: () => api.skyBrightness(safe),
    enabled: !!target.data,
  });
  const frames = useQuery({
    queryKey: ["frames", safe, sort, order],
    queryFn: () => api.listFrames(safe, sort, order),
  });
  const runs = useQuery({ queryKey: ["runs", safe], queryFn: () => api.listStackRuns(safe) });
  const latestRun = runs.data?.[0];  // listStackRuns returns newest first
  // *The* picture of this target — the one this page shows, saves, shares and
  // edits. Every other surface (the Library tile, the Best wall, the montage,
  // `gallery._representative_run`) resolves the **pinned cover** first and only
  // falls back to the newest run; this page took the newest run flat, so pinning
  // run 3 and then stacking run 4 left the Target page showing a different
  // picture from the Library card while its own notes talked about "the cover".
  // Same precedence as `_representative_run`, including its degrade: a cover
  // whose preview has gone silently falls back to the newest picture.
  //
  // `latestRun` deliberately stays the newest run: the analysis notes below
  // (thin stack, noise badge, "sharpest yet", integration trend) are statements
  // about the *latest* stack, and pinning an old favourite must not make them
  // describe it.
  // The fallback is the newest run **that has a picture**, not simply the newest
  // run — the second half of `_representative_run`'s precedence, and the same
  // divergence one step along: a newest run with no preview (a channel-combine,
  // or one whose preview file has gone) left this page showing *nothing* while
  // the Library tile went on showing the run before it. A target with no picture
  // anywhere still falls all the way back to `latestRun`, because the action row
  // (Edit, Stack) works on a run that has yet to render one.
  const pictureRun = useMemo(() => {
    const coverId = target.data?.cover_stack_run_id ?? null;
    const list = runs.data ?? [];
    if (coverId != null) {
      const pinned = list.find((r) => r.id === coverId && r.has_preview);
      if (pinned) return pinned;
    }
    return list.find((r) => r.has_preview) ?? latestRun;
  }, [runs.data, target.data?.cover_stack_run_id, latestRun]);
  // ...and whether that picture is a pinned cover that ISN'T the newest stack —
  // the one case a beginner could be confused by ("why isn't my new stack here?").
  // Compared against the newest run *with a picture*, so falling back past a
  // preview-less newest run doesn't claim a cover nobody pinned.
  const newestPicture = useMemo(
    () => (runs.data ?? []).find((r) => r.has_preview), [runs.data]);
  const showingOlderCover = !!pictureRun && !!newestPicture
    && pictureRun.id !== newestPicture.id;
  // The night this picture's subs were **shot**, for the share sheet's caption —
  // never `timestamp_utc`, which is when the stack ran. `""` on a run with no
  // recorded window, which `sharePictureText` turns into no date clause at all.
  const captureLabel = formatCaptureNights(
    pictureRun?.capture_night_start, pictureRun?.capture_night_end);
  // The *measured* framing verdict for the newest picture, if there is one. The
  // note below renders it; this page reads the same answer (one shared query) so
  // the object card can drop its catalog "will it fit?" prediction while the
  // measurement of the very same thing is on screen — the page said "it's bigger
  // than one frame" twice, near the top and again at the bottom.
  const measuredFraming = useStackFraming(
    safe, latestRun?.has_fits ? latestRun.id : null);
  // Whether to offer the wallpaper "North up" toggle: only when the latest run's
  // WCS yields a real orientation correction (else the endpoint no-ops). One
  // cheap read of the run's own suggestion, gated on it having a FITS to read.
  const renderSuggestion = useQuery({
    queryKey: ["render-suggestion", safe, pictureRun?.id],
    queryFn: () => api.stackRenderSuggestion(safe, pictureRun!.id),
    enabled: !!pictureRun?.has_fits,
    staleTime: Infinity,
  });
  const wallpaperCanNorthUp = typeof renderSuggestion.data?.north_up_deg === "number";
  // Honest heads-up when the newest stack combined very few frames — it will
  // look noisy (a stack only smooths noise as it combines more subs), so say so
  // rather than presenting a single-sub result as a finished picture.
  const thinStack = useMemo(
    () => thinStackWarning(latestRun?.n_frames_used),
    [latestRun],
  );
  // Which "next best move" tip is currently in play (or null when none) — the
  // plateau verdict defers to it so the two never contradict ("add more time"
  // vs "more time won't help"). Mirrors NextBestMoveBadge's own inputs.
  const coachKind = useMemo(
    () =>
      nextBestMove({
        nFramesUsed: latestRun?.n_frames_used,
        integrationS: latestRun?.total_exposure_s,
        nUnsolved: unsolvedCount,
        softStars: softerThanUsual(runs.data),
      })?.kind ?? null,
    [latestRun, unsolvedCount, runs.data],
  );
  // When walk-away Auto-stack is on, it now holds a target back rather than
  // publishing a 1-2 frame single-frame-speckle "master" (see auto_stack_min_frames
  // — v0.183.0). A held target produces no stack, so without this it looks like
  // nothing is happening. Read the two relevant settings and, when the target is
  // sitting below the floor with subs still waiting to be located, say so plainly
  // and point at the fix (plate-solve). Display-only.
  const settings = useQuery({ queryKey: ["settings"], queryFn: api.getSettings });
  const heldForSolve = useMemo(() => {
    if (!settings.data || settings.data.auto_stack !== true) return null;
    const floor = Number(settings.data.auto_stack_min_frames ?? 3);
    if (!Number.isFinite(floor) || floor <= 1) return null;
    const accepted = target.data?.n_frames_accepted ?? 0;
    const solvedAccepted = Math.max(0, accepted - unsolvedCount);
    // Only "waiting" when we're below the floor, more subs are still unsolved
    // (so locating them would lift us over it), and no healthy stack exists yet.
    const haveHealthyStack = (latestRun?.n_frames_used ?? 0) >= floor;
    if (solvedAccepted >= floor || unsolvedCount <= 0 || haveHealthyStack) return null;
    return { located: solvedAccepted, floor };
  }, [settings.data, target.data, unsolvedCount, latestRun]);

  const patch = useMutation({
    mutationFn: ({ id, body }: { id: number; body: Record<string, unknown> }) =>
      api.patchFrame(safe, id, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["frames", safe] });
      qc.invalidateQueries({ queryKey: ["target", safe] });
      // A single accept/reject changes the "why frames were left out" breakdown
      // too — invalidate it like every sibling bulk mutation does, or the
      // left-out hovercard goes stale until the next refetch.
      qc.invalidateQueries({ queryKey: ["reject-summary", safe] });
    },
  });

  const bulk = useMutation({
    mutationFn: (body: Record<string, unknown>) => api.bulkFrames(safe, body),
    onSuccess: (r, body) => {
      // When the backend explains a no-op (e.g. "Reject worst" with no QC metric
      // measured yet), surface that guidance instead of a bare "Updated 0 frames".
      // A note can also accompany work that *did* happen (e.g. a mosaic cut taken
      // per panel), so keep the count and drop the warning colour in that case.
      if (r.note) {
        notifications.show({
          message: r.changed ? `Updated ${r.changed} frames — ${r.note}` : r.note,
          color: r.changed ? "violet" : "yellow",
        });
      } else {
        notifications.show({ message: `Updated ${r.changed} frames`, color: "violet" });
      }
      qc.invalidateQueries({ queryKey: ["frames", safe] });
      qc.invalidateQueries({ queryKey: ["target", safe] });  // accepted-count badge
      qc.invalidateQueries({ queryKey: ["reject-summary", safe] });
      // Remember a bulk reject so the user can undo it; clear on the undo itself.
      const action = (body as { action?: string }).action;
      const ids = r.changed_ids ?? [];
      if (
        (action === "reject_worst" || action === "reject_streaked" ||
          action === "reject_trailed") && ids.length
      ) {
        const label =
          action === "reject_streaked" ? "streaked"
            : action === "reject_trailed" ? "trailed"
              : "worst-frame";
        setLastReject({ ids, label });
      } else {
        setLastReject(null);
      }
    },
    onError: (e: Error) => notifications.show({ message: e.message, color: "red" }),
  });

  const qcSolve = useMutation({
    mutationFn: () => api.qcSolve(safe),
    onSuccess: () => {
      notifications.show({ message: "QC + solve started", color: "violet" });
      qc.invalidateQueries({ queryKey: ["jobs"] });
    },
  });

  // One-click "just do it": QC + plate-solve, auto-grade (when enabled) and stack
  // this target in a single job — the whole middle of the workflow without a form.
  const process = useMutation({
    mutationFn: () => api.processTarget(safe),
    onSuccess: () => {
      notifications.show({
        message: "Processing target — checking, solving & stacking. Watch Jobs for progress.",
        color: "violet",
      });
      qc.invalidateQueries({ queryKey: ["jobs"] });
    },
    onError: (e: Error) => notifications.show({ message: e.message, color: "red" }),
  });

  // One-click "reject the odd-target frames" for the mixed-pointing guard: reject
  // exactly the subs outside the largest pointing (the ones the stacker would
  // silently drop), leaving a clean single-target batch. Undoable — auto-grade
  // style — because it changes accept state, so a stray good frame is one click
  // back. Its own state (not the bulk `lastReject`) so the messaging is specific.
  const [mixedRejected, setMixedRejected] = useState<number[] | null>(null);
  const rejectMixed = useMutation({
    mutationFn: (ids: number[]) => api.bulkFrames(safe, { action: "reject", ids }),
    onSuccess: (_r, ids) => {
      setMixedRejected(ids);
      notifications.show({
        message: `Rejected ${ids.length} odd-target frame${ids.length === 1 ? "" : "s"}`,
        color: "violet",
      });
      qc.invalidateQueries({ queryKey: ["frames", safe] });
      qc.invalidateQueries({ queryKey: ["target", safe] });
      qc.invalidateQueries({ queryKey: ["reject-summary", safe] });
    },
    onError: (e: Error) => notifications.show({ message: e.message, color: "red" }),
  });
  const undoMixed = useMutation({
    mutationFn: (ids: number[]) => api.bulkFrames(safe, { action: "accept", ids }),
    onSuccess: () => {
      setMixedRejected(null);
      notifications.show({ message: "Re-accepted the odd-target frames", color: "violet" });
      qc.invalidateQueries({ queryKey: ["frames", safe] });
      qc.invalidateQueries({ queryKey: ["target", safe] });
      qc.invalidateQueries({ queryKey: ["reject-summary", safe] });
    },
    onError: (e: Error) => notifications.show({ message: e.message, color: "red" }),
  });

  // Plate-solve *setup* problem (ASTAP or its star database not available) —
  // when present, every frame's solve fails identically, so the whole target's
  // frames pile up as "Plate-solve failed" with no hint that the fix is a
  // one-time setup step rather than dropping frames. Turn that into one
  // actionable banner. Null (the common case) renders nothing.
  // Prefer the server's classification (v0.84.1+) — it's reliable for the
  // star-database case too, since those failures are now stored with a stable
  // canonical reason. Fall back to detecting it from `counts` on an older
  // backend (or if the field is absent).
  const solveSetup = useMemo(
    () =>
      rejectSummary.data?.solve_setup_problem ??
      detectSolveSetupProblem(rejectSummary.data?.counts),
    [rejectSummary.data],
  );

  const list = frames.data ?? [];
  // Accepted frames still carrying a streak flag (satellite/plane trail). With
  // "keep streaked frames" on, QC flags rather than rejects these, so per-pixel
  // rejection (sigma-clip / drizzle reject) can clean the trail while keeping
  // the frame's good signal. Surfacing the count tells the user at a glance what
  // that rejection will need to handle.
  const streakedAccepted = list.filter((f) => f.accept && f.streak_detected).length;
  // Accepted frames whose stars are a strong eccentricity outlier for this
  // target — a bad-tracking / wind / bumped-mount sub. A frame counts as
  // "trailed" only when its eccentricity is *both* a >3·MAD within-target
  // outlier *and* above an absolute floor of noticeably elongated stars, so a
  // uniformly round set never flags anything. Mirrors the server-side
  // `trailed_frame_ids` used by the reject_trailed bulk action; keep in sync.
  const trailedAccepted = useMemo(() => {
    const ecc = list
      .filter((f) => f.accept && f.eccentricity_median != null)
      .map((f) => f.eccentricity_median as number);
    if (ecc.length < 5) return 0;
    const med = medianOf(ecc);
    const mad = medianOf(ecc.map((v) => Math.abs(v - med)));
    const threshold = Math.max(med + 3 * mad, 0.6);
    return ecc.filter((v) => v > threshold).length;
  }, [list]);
  const selectedFrame = useMemo(
    () => list.find((f) => f.id === selected) ?? list[0],
    [list, selected],
  );

  // Getting-started nudge: highlight the one-click "Process target" as the next
  // step for a target whose newest frames haven't been turned into a stack yet.
  // Fires when there are frames to work with *and* either no stack has ever run,
  // or accepted frames are still waiting to be plate-solved (so a stack can't
  // include them). Suppressed while the plate-solve *setup* banner is showing
  // (that has to be fixed first, and Process would just re-fail the same way),
  // and once every accepted frame is solved and a stack exists — so it fades
  // out the moment the target has been processed rather than nagging. Purely a
  // discoverability aid; the toolbar button does the same thing.
  const needsProcessing = useMemo(() => {
    if (solveSetup) return false;
    if (list.length === 0) return false;
    const acceptedUnsolved = list.some((f) => f.accept && !f.solved);
    return !latestRun || acceptedUnsolved;
  }, [solveSetup, list, latestRun]);

  // Multi-night nudge: the target already has a stack, but accepted+solved subs
  // have arrived *since* it ran, so the current master no longer reflects all
  // the user's data. Compare against the newest *genuine* stack run's timestamp
  // (an editor-export/combine run — `reusable === false` — doesn't reset the
  // clock). Only shown when there's nothing more pressing to do first
  // (`needsProcessing`/`solveSetup` take precedence). Read-only detection; the
  // one-click reuses the same Process chain.
  const newSubsSinceStack = useMemo(() => {
    if (needsProcessing || solveSetup) return 0;
    const latestGenuine = runs.data?.find((r) => r.reusable);
    return countNewSubsSinceStack(list, latestGenuine?.timestamp_utc);
  }, [needsProcessing, solveSetup, runs.data, list]);

  // "Is it enough yet?" — judge this target's accumulated integration against a
  // sane per-object-type goal so a beginner gets a plain-language answer to "do
  // I have enough subs, or keep shooting?" The object type comes from the
  // offline identify card (a catalog match); unknown → a mid-range default. A
  // suggestion only — never gates stacking. Null (no integration yet) → no card.
  const readiness = useMemo(
    () =>
      target.data
        ? integrationReadiness(
            target.data.total_exposure_s,
            identity.data?.type,
            goal.data?.goal_s != null ? goal.data.goal_s / 3600 : null,
          )
        : null,
    [target.data, identity.data, goal.data],
  );

  // "…and how much longer will that take me?" — the question the readiness
  // verdict leaves hanging whenever the answer is "not yet". Projects the
  // remaining gap forward at the owner's *own* recent pace on this target, in
  // clear nights (the app can't promise weather). Self-hides once the goal is
  // met or when there's too little history to derive an honest pace.
  const clearNights = useMemo(
    () =>
      readiness
        ? estimateClearNights(
            (readiness.goalHours - readiness.hours) * 3600,
            nights.data,
          )
        : null,
    [readiness, nights.data],
  );

  // "Is more time worth it?" — the same question again, but answered from the
  // *measured* grain of this target's own deepest genuine stack instead of a
  // per-object-type time goal. It supersedes the goal-independent √N line below
  // it once a real stack exists (that line reads integration time alone and
  // would just say a weaker version of the same thing), and stays null until
  // then, so a target with no stack sees exactly what it saw before.
  const grain = useMemo(() => cardGrainProjection(runs.data), [runs.data]);

  // Frames QC couldn't read at all (corrupt/truncated FITS): make them visible —
  // they're skipped when stacking but invisible in the reject breakdown. A full
  // QC + Solve re-checks them (`only_new_qc=False`), so offer that one click.
  const qcUncheckable = useMemo(() => countQcUncheckable(list), [list]);

  // Pre-flight mixed-pointing guard: the accepted+solved subs cluster into two
  // (or more) well-separated pointings, so the folder probably holds frames from
  // two different targets. Stacking would waste the run on one pointing and
  // silently drop the rest. Suppressed while plate-solving is misconfigured (the
  // RA/Dec we cluster on would be missing/unreliable then). Read-only detection.
  const mixedPointings = useMemo(
    () => (solveSetup ? null : detectMixedPointings(list)),
    [solveSetup, list],
  );

  // Keyboard grading: j/k or arrows to move, a to accept, r/x to reject. Skips
  // when typing in a field so notes/tags editing isn't hijacked.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const el = e.target as HTMLElement | null;
      const tag = el?.tagName;
      if (tag === "INPUT" || tag === "TEXTAREA" || el?.isContentEditable) return;
      if (!list.length) return;
      const cur = selectedFrame;
      const idx = cur ? list.findIndex((f) => f.id === cur.id) : -1;
      switch (e.key) {
        case "ArrowDown":
        case "j": {
          e.preventDefault();
          const next = list[Math.min((idx < 0 ? -1 : idx) + 1, list.length - 1)];
          if (next) setSelected(next.id);
          break;
        }
        case "ArrowUp":
        case "k": {
          e.preventDefault();
          const prev = list[Math.max((idx < 0 ? 1 : idx) - 1, 0)];
          if (prev) setSelected(prev.id);
          break;
        }
        case "a":
          if (cur) { e.preventDefault(); patch.mutate({ id: cur.id, body: { accept: true } }); }
          break;
        case "r":
        case "x":
          if (cur) { e.preventDefault(); patch.mutate({ id: cur.id, body: { accept: false } }); }
          break;
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [list, selectedFrame, patch]);

  const setSortCol = (key: SortKey) => {
    if (sort === key) setOrder(order === "asc" ? "desc" : "asc");
    else {
      setSort(key);
      setOrder("asc");
    }
  };

  if (target.isLoading) {
    return (
      <Center h={300}>
        <Loader />
      </Center>
    );
  }

  // A missing target (deleted, or a stale bookmark/shared link) 404s from
  // api.getTarget. Without this branch the page still renders via the optional
  // chaining below — a blank title, a "/accepted" badge and an empty table — a
  // confusing dead-end. Show the same recoverable error the sibling routes do;
  // gated on !target.data so a background-refetch blip never blanks a working page.
  if (target.isError && !target.data) {
    return <QueryError error={target.error} onRetry={() => target.refetch()} />;
  }

  // The columns and their explanations live in one shared array, so the header
  // tooltips and the "What do these numbers mean?" disclosure below the table
  // can't drift into two different answers (see `frameColumns.ts`).
  const cols = FRAME_COLUMNS;

  return (
    <Stack>
      {/* First-run coaching, on the sample demo only (see SampleTourNote). */}
      <SampleTourNote step="target" safe={safe} />
      {/* Every note this page can raise, in one prioritised area: the top two
          speak inline and the rest fold behind a "N more notes" line. Nothing is
          dropped — see NoticeBoard, which measures which of these self-hiding
          notes actually has something to say. */}
      <NoticeBoard
        inlineCount={2}
        data-testid="target-notes"
        items={[
          // "Your last stack didn't run, and here's the setting that would fix
          // it." Self-hiding when this target is fine. A warning rather than
          // blocking: the target still has all its frames and everything else
          // works — it just stopped producing new pictures.
          { key: "stack-failed", priority: NOTICE_PRIORITY.warning,
            node: <StackFailedNote safe={safe} /> },
          { key: "solve-setup", priority: NOTICE_PRIORITY.blocking, node: solveSetup ? (
            <Alert color="orange" icon={<IconAlertTriangle size={18} />}
              title={solveSetup.kind === "astap"
                ? "Plate-solving isn't set up — ASTAP wasn't found"
                : "Plate-solving needs a star database"}>
              <Text size="sm">
                {solveSetup.kind === "astap"
                  ? `${solveSetup.frames} frame${solveSetup.frames === 1 ? "" : "s"} couldn't be `
                    + "plate-solved because ASTAP (the plate-solver) wasn't found. Frames need "
                    + "sky coordinates before they can be stacked, so this blocks the whole "
                    + "target. Install ASTAP and set its path in Settings, then re-run solving."
                  : `${solveSetup.frames} frame${solveSetup.frames === 1 ? "" : "s"} couldn't be `
                    + "plate-solved because ASTAP couldn't find a star database to match against. "
                    + "Download an ASTAP star database (e.g. the D50/H17/H18 catalog) into ASTAP's "
                    + "folder, then re-run solving."}
              </Text>
              <Group gap="xs" mt="xs">
                <Button size="xs" variant="filled" color="orange"
                  loading={qcSolve.isPending} onClick={() => qcSolve.mutate()}>
                  Re-run QC + Solve
                </Button>
                <Button size="xs" variant="light" color="orange"
                  component={Link} to={settingsLink("plate-solving")}>
                  Open Settings
                </Button>
              </Group>
            </Alert>
          ) : null },
          { key: "needs-processing", priority: NOTICE_PRIORITY.advisory, node: needsProcessing ? (
            <Alert color="violet" icon={<IconSparkles size={18} />}
              title="Ready to process?">
              <Text size="sm">
                One click runs quality-check, plate-solving and stacking for this
                target — no form to fill. You'll get a finished master image to edit.
              </Text>
              <Group gap="xs" mt="xs">
                <Button size="xs" variant="filled" color="violet"
                  leftSection={<IconSparkles size={14} />}
                  loading={process.isPending} onClick={() => process.mutate()}>
                  Process target
                </Button>
              </Group>
            </Alert>
          ) : null },
          { key: "new-subs", priority: NOTICE_PRIORITY.advisory, node: newSubsSinceStack > 0 ? (
            <Alert color="blue" variant="light" icon={<IconStack2 size={18} />}
              title={`${newSubsSinceStack} new sub${newSubsSinceStack === 1 ? "" : "s"} since your last stack`}>
              <Text size="sm">
                {newSubsSinceStack === 1 ? "A frame has" : `${newSubsSinceStack} frames have`}{" "}
                been accepted and solved since this target was last stacked, so the
                current master doesn't include{" "}
                {newSubsSinceStack === 1 ? "it" : "them"} yet. Restack to fold in the
                new data.
              </Text>
              <Group gap="xs" mt="xs">
                <Button size="xs" variant="filled" color="blue"
                  leftSection={<IconStack2 size={14} />}
                  loading={process.isPending} onClick={() => process.mutate()}>
                  Restack
                </Button>
              </Group>
            </Alert>
          ) : null },
          /* "Your newest stack is cleaner than the cover you pinned — swap?"
              Only ever an offer, and only when a cover is pinned. Self-hides. */
          { key: "cleanest-shot", priority: NOTICE_PRIORITY.advisory,
            node: <CleanestShotNote safe={safe} /> },
          /* The mirror case: with *nothing* pinned the cover follows the newest
              stack, so a hazy restack can silently demote a better picture.
              Mutually exclusive with the note above (that one needs a pin, this
              one needs none), so the two can never both appear. Self-hides. */
          { key: "grainier-newest", priority: NOTICE_PRIORITY.advisory,
            node: <GrainierNewestNote safe={safe} /> },
          { key: "autostack-hold", priority: NOTICE_PRIORITY.warning,
            node: <AutoStackHoldNote safe={safe} /> },
          /* "This picture can't say which night it's from" — an offer to
              re-stack a picture made before the app recorded when its subs were
              shot, named as the gain rather than as a version. Suppressed while
              the "N new subs" note is up: that one already offers a restack, for
              a more pressing reason, and a re-stack answers both. Advisory, so
              it can never take a warning's inline slot. */
          { key: "restack-gain", priority: NOTICE_PRIORITY.advisory,
            node: newSubsSinceStack > 0 ? null : <RestackGainNote safe={safe} /> },
          /* "Capture may have stopped" — subs were arriving steadily and then
              stopped, mid-session. A warning rather than an advisory because it
              is only actionable while the night is still running; it self-hides
              the moment the silence outlasts the session, and never fires on a
              night the owner simply finished. */
          { key: "capture-quiet", priority: NOTICE_PRIORITY.warning,
            node: <CaptureQuietNote safe={safe} /> },
          { key: "missing-files", priority: NOTICE_PRIORITY.warning, node: missingFiles !== null ? (
            <Alert color="orange" variant="light" icon={<IconAlertTriangle size={18} />}
              title={missingFiles.title}>
              <Text size="sm">{missingFiles.message}</Text>
              <Group gap="xs" mt="xs">
                <Button size="xs" variant="light" color="orange"
                  loading={rejectSummary.isFetching}
                  onClick={() => {
                    qc.invalidateQueries({ queryKey: ["reject-summary", safe] });
                  }}>
                  Check again
                </Button>
              </Group>
            </Alert>
          ) : null },
          { key: "qc-uncheckable", priority: NOTICE_PRIORITY.warning, node: qcUncheckable > 0 ? (
            <Alert color="gray" variant="light" icon={<IconAlertTriangle size={18} />}
              title={`${qcUncheckable} frame${qcUncheckable === 1 ? "" : "s"} couldn't be quality-checked`}>
              <Text size="sm">
                {qcUncheckable === 1 ? "A frame" : `${qcUncheckable} frames`} couldn't be
                read during quality-check (an unreadable, corrupt or truncated FITS
                file), so {qcUncheckable === 1 ? "it has" : "they have"} no metrics and{" "}
                {qcUncheckable === 1 ? "is" : "are"} skipped when stacking. Re-check{" "}
                {qcUncheckable === 1 ? "it" : "them"} in case the read failure was
                transient (a copy still in progress).
              </Text>
              <Group gap="xs" mt="xs">
                <Button size="xs" variant="light" color="gray"
                  loading={qcSolve.isPending} onClick={() => qcSolve.mutate()}>
                  Re-check these frames
                </Button>
              </Group>
            </Alert>
          ) : null },
          { key: "mixed-pointings", priority: NOTICE_PRIORITY.warning, node: mixedRejected === null && mixedPointings ? (
            <Alert color="orange" variant="light" icon={<IconAlertTriangle size={18} />}
              title={`This batch looks like ${mixedPointings.pointings} different targets`}>
              <Text size="sm">
                {mixedPointings.majority} of your accepted, plate-solved subs point at
                one place and {mixedPointings.others} point about{" "}
                {Math.round(mixedPointings.separationDeg)}° away — that usually means two
                different targets' frames landed in the same folder (or some subs
                plate-solved to the wrong place). If you stack now, only the frames
                matching the reference pointing are combined and the other{" "}
                {mixedPointings.others === 1 ? "one is" : `${mixedPointings.others} are`}{" "}
                silently dropped, so you'd waste a stack on part of the data. Reject the
                odd frames to keep just the main pointing, or check each frame's solved
                RA/Dec in the Frames table below and split them into their own target.
              </Text>
              {mixedPointings.minorityIds.length ? (
                <Button mt="xs" size="xs" variant="light" color="orange"
                  loading={rejectMixed.isPending}
                  onClick={() => rejectMixed.mutate(mixedPointings.minorityIds)}>
                  Reject the {mixedPointings.minorityIds.length} odd-target frame
                  {mixedPointings.minorityIds.length === 1 ? "" : "s"}
                </Button>
              ) : null}
            </Alert>
          ) : null },
          { key: "mixed-rejected", priority: NOTICE_PRIORITY.info, node: mixedRejected !== null ? (
            <Alert color="teal" variant="light" icon={<IconCheck size={18} />}
              title="Rejected the odd-target frames">
              <Text size="sm">
                Rejected {mixedRejected.length} sub{mixedRejected.length === 1 ? "" : "s"} that
                didn't match the main pointing — the batch is a single target now, so a
                stack won't waste itself on part of the data.
              </Text>
              <Button mt="xs" size="xs" variant="light" color="teal"
                leftSection={<IconArrowBackUp size={14} />}
                loading={undoMixed.isPending}
                onClick={() => undoMixed.mutate(mixedRejected)}>
                Undo — re-accept {mixedRejected.length} frame{mixedRejected.length === 1 ? "" : "s"}
              </Button>
            </Alert>
          ) : null },
          /* Was the sky brighter than usual on the latest night? Explains a washed-out
              result the owner would otherwise blame on themselves. Self-hides. */
          { key: "sky-brightness", priority: NOTICE_PRIORITY.info, node: <SkyBrightnessNote read={skyBrightness.data?.read} /> },
          { key: "held-for-solve", priority: NOTICE_PRIORITY.advisory, node: heldForSolve ? (
            <Alert
              color="blue"
              variant="light"
              icon={<IconClock size={18} />}
              title="Auto-stack is waiting for more of your subs to be located"
            >
              <Text size="sm">
                {heldForSolve.located === 0
                  ? "None of your accepted subs have been located (plate-solved) yet"
                  : `Only ${heldForSolve.located} of your accepted subs `
                    + `${heldForSolve.located === 1 ? "has" : "have"} been located `
                    + "(plate-solved) so far"}
                {`, so the hands-off auto-stack is holding off rather than making a `
                  + `picture out of one or two frames (that would just be noise). It `
                  + `will stack automatically once at least ${heldForSolve.floor} subs `
                  + `are located — run Plate Solve to locate more, or use "Stack" / `
                  + `"Process this target" to make one now anyway.`}
              </Text>
            </Alert>
          ) : null },
          { key: "thin-stack", priority: NOTICE_PRIORITY.warning, node: thinStack ? (
            <Alert
              color={thinStack.level === "single" ? "orange" : "yellow"}
              variant="light"
              icon={<IconAlertTriangle size={18} />}
              title={thinStack.level === "single"
                ? "This stack is really just one frame"
                : "Very few frames were combined"}
            >
              <Text size="sm">{thinStack.message}</Text>
            </Alert>
          ) : null },
          /* The concrete "stacking cut your noise ~N×" payoff, right where a beginner
              lands on the finished picture (self-hides for a thin/unmeasurable stack). */
          { key: "stack-noise", priority: NOTICE_PRIORITY.praise, node: latestRun?.has_preview ? (
            <StackNoiseBadge safe={safe} runId={latestRun.id}
              nFrames={latestRun.n_frames_used ?? null} />
          ) : null },
          /* A calibration master the user explicitly saved that the newest run had
              to drop — recorded by the unattended stack and, until now, only visible
              if they expanded History's Info panel. Self-hides on a clean run. */
          { key: "calibration-skipped", priority: NOTICE_PRIORITY.warning, node: latestRun ? (
            <CalibrationSkippedNote safe={safe} runId={latestRun.id} />
          ) : null },
          /* Per-target personal-record beat: celebrate when the newest stack came
              out sharper than any previous stack of this target (self-hides on the
              first run or when it's not a record). */
          { key: "sharpest-yet", priority: NOTICE_PRIORITY.praise, node: latestRun?.has_preview ? (
            <SharpestYetBadge name={target.data?.name ?? "target"} runs={runs.data} />
          ) : null },
          /* "To make this even better": one plain-language coaching line naming the
              single highest-leverage next step (locate more subs / add subs / add
              time), or a short well-done note. Suppressed while the louder thin-stack
              warning is up so the two never duplicate the "add more subs" nudge. */
          { key: "next-best-move", priority: NOTICE_PRIORITY.advisory, node: latestRun?.has_preview && !thinStack ? (
            <NextBestMoveBadge
              name={target.data?.name ?? "target"}
              nFramesUsed={latestRun.n_frames_used}
              integrationS={latestRun.total_exposure_s}
              nUnsolved={unsolvedCount}
              runs={runs.data}
            />
          ) : null },
          /* "About as clean as your sky allows": when this target's measured noise
              has plateaued (sky-limited), tell the beginner more subs won't help it
              much — right where they decide whether to revisit it. Self-hiding, and
              suppressed whenever the coaching above is nudging "add more time" so the
              two never contradict. */
          { key: "integration-trend", priority: NOTICE_PRIORITY.info, node: latestRun?.has_preview ? (
            <IntegrationTrendBadge runs={runs.data} coachKind={coachKind} />
          ) : null },
          /* "Did I frame it well?" — how the finished picture actually caught the
              target, measured from the run's own WCS. Self-hides when the target
              isn't a sized catalog object or the run has no solved WCS. */
          { key: "framing-verdict", priority: NOTICE_PRIORITY.advisory, node: latestRun?.has_fits ? (
            <FramingVerdictNote safe={safe} runId={latestRun.id} />
          ) : null },
        ]}
      />
      <Group justify="space-between" gap="xs">
        <Group gap="xs" style={{ minWidth: 0 }}>
          <Title order={2} style={{ wordBreak: "break-word" }}>{target.data?.name}</Title>
          <Badge variant="light" color="violet">
            {target.data?.n_frames_accepted}/{target.data?.n_frames} accepted
          </Badge>
          {/* Total integration time (sum of the *accepted* subs' exposures) — the
              number every astrophotographer thinks in and the honest "do I have
              enough light yet?" signal for the multi-night Seestar workflow. The
              Library card and Dashboard already show it; surface it here on the
              page where a user decides whether to keep shooting this target. */}
          {target.data?.total_exposure_s ? (
            <Tooltip label="Total light collected across all accepted subs"
              withArrow openDelay={200}>
              <Badge variant="light" color="teal" style={{ cursor: "help" }}>
                {formatIntegration(target.data.total_exposure_s)} integration
              </Badge>
            </Tooltip>
          ) : null}
          {rejectedCount > 0 || unsolvedCount > 0 ? (
            <HoverCard width={300} shadow="md" withArrow openDelay={100}>
              <HoverCard.Target>
                <Badge
                  variant="light"
                  // Amber whenever silently-dropped unsolved subs are present —
                  // they're the honesty concern behind a thin stack, even when a
                  // few frames were also rejected. Both left-out sets are disjoint
                  // and both miss the stack, so surface each rather than letting a
                  // single reject hide a far larger unsolved count.
                  color={unsolvedCount > 0 ? "orange" : "gray"}
                  style={{ cursor: "help" }}
                >
                  {rejectedCount > 0 && unsolvedCount > 0
                    ? `${rejectedCount} rejected · ${unsolvedCount} not located yet`
                    : unsolvedCount > 0
                      ? `${unsolvedCount} not located yet`
                      : `${rejectedCount} rejected`}
                </Badge>
              </HoverCard.Target>
              <HoverCard.Dropdown>
                {rejectSummary.data?.summary?.buckets.length ? (
                  // Plain-language grouped breakdown + verdict (v0.159.2+).
                  <RejectionBreakdown summary={rejectSummary.data.summary} />
                ) : rejectSummary.data && Object.keys(rejectSummary.data.counts).length ? (
                  // Fallback for an older backend without the friendly summary.
                  <>
                    <Text size="sm" fw={600} mb={4}>Why frames were rejected</Text>
                    <Stack gap={2}>
                      {Object.entries(rejectSummary.data.counts)
                        .sort((a, b) => b[1] - a[1])
                        .map(([reason, n]) => (
                          <Group key={reason} justify="space-between" gap="xs">
                            <Text size="xs">{rejectReasonLabel(reason)}</Text>
                            <Text size="xs" fw={600}>{n}</Text>
                          </Group>
                        ))}
                    </Stack>
                  </>
                ) : (
                  <Text size="xs" c="dimmed">
                    {rejectSummary.isLoading ? "Loading…" : "No breakdown available"}
                  </Text>
                )}
              </HoverCard.Dropdown>
            </HoverCard>
          ) : null}
          {/* Visible plain-language explainer beside the "not located yet" count —
              "located"/"plate-solve" is jargon a first-light owner can misread as
              an error, and the breakdown that explains it is otherwise only found
              by hovering the badge. Shown only when there are unsolved subs. */}
          {unsolvedCount > 0 ? <UnsolvedHelp /> : null}
          {lastReject ? (
            <Button
              size="compact-xs"
              variant="subtle"
              color="teal"
              leftSection={<IconArrowBackUp size={14} />}
              loading={bulk.isPending}
              aria-label="Undo last bulk reject"
              onClick={() => bulk.mutate({ action: "accept", ids: lastReject.ids })}
            >
              Undo {lastReject.label} reject ({lastReject.ids.length})
            </Button>
          ) : null}
          {streakedAccepted > 0 ? (
            <Group gap={4}>
              <Tooltip
                multiline
                w={260}
                label={`${streakedAccepted} accepted frame${streakedAccepted === 1 ? "" : "s"} carry a satellite/plane trail. Stack with sigma-clip or drizzle outlier rejection to remove the trail while keeping the frame, or reject them all here.`}
              >
                <Badge variant="light" color="orange">
                  {streakedAccepted} streaked
                </Badge>
              </Tooltip>
              <Button
                size="compact-xs"
                variant="subtle"
                color="orange"
                loading={bulk.isPending}
                aria-label="Reject all streaked frames"
                onClick={() => {
                  if (
                    window.confirm(
                      `Reject all ${streakedAccepted} accepted frame${streakedAccepted === 1 ? "" : "s"} carrying a satellite/plane trail?`,
                    )
                  ) {
                    bulk.mutate({ action: "reject_streaked" });
                  }
                }}
              >
                Reject all
              </Button>
            </Group>
          ) : null}
          {trailedAccepted > 0 ? (
            <Group gap={4}>
              <Tooltip
                multiline
                w={260}
                label={`${trailedAccepted} accepted frame${trailedAccepted === 1 ? "" : "s"} have unusually elongated stars for this target — a sign of tracking error, wind or a bumped mount on that whole sub. Rejecting them can sharpen the stack.`}
              >
                <Badge variant="light" color="yellow">
                  {trailedAccepted} trailed
                </Badge>
              </Tooltip>
              <Button
                size="compact-xs"
                variant="subtle"
                color="yellow"
                loading={bulk.isPending}
                aria-label="Reject all trailed frames"
                onClick={() => {
                  if (
                    window.confirm(
                      `Reject all ${trailedAccepted} accepted frame${trailedAccepted === 1 ? "" : "s"} with unusually elongated (trailed) stars?`,
                    )
                  ) {
                    bulk.mutate({ action: "reject_trailed" });
                  }
                }}
              >
                Reject all
              </Button>
            </Group>
          ) : null}
        </Group>
        <Group gap="xs">
          <Button
            variant="filled"
            color="violet"
            leftSection={<IconSparkles size={16} />}
            onClick={() => process.mutate()}
            loading={process.isPending}
            aria-label="Process this target"
            title="Quality-check, plate-solve and stack this target in one step"
          >
            <Box visibleFrom="sm">Process target</Box>
            <Box hiddenFrom="sm">Process</Box>
          </Button>
          <Button
            variant="default"
            leftSection={<IconTelescope size={16} />}
            onClick={() => qcSolve.mutate()}
            loading={qcSolve.isPending}
            aria-label="Re-run QC and Solve"
          >
            <Box visibleFrom="sm">Re-run QC + Solve</Box>
            <Box hiddenFrom="sm">Re-check</Box>
          </Button>
          <Button component={Link} to={`/targets/${safe}/history`} variant="default"
            leftSection={<IconHistory size={16} />} aria-label="History">
            History
          </Button>
          {pictureRun ? (
            <Button component={Link} to={`/targets/${safe}/edit/${pictureRun.id}`} variant="default"
              leftSection={<IconWand size={16} />} aria-label="Edit latest stack">
              Edit
            </Button>
          ) : null}
          {/* Everything you can *do with the finished picture* lives behind one
              menu. This row used to lay nine controls out side by side — with
              two dropdowns ("Picture" and "Wallpaper") that were both "save this
              picture" — on the page the owner named as the busiest in the app.
              Nothing was removed: every item below is the control that used to
              be a button, with its own wording and behaviour. */}
          {pictureRun?.has_preview ? (
            <Menu shadow="md" width={260} position="bottom-end" withinPortal>
              <Menu.Target>
                <Button variant="default" leftSection={<IconDownload size={16} />}
                  rightSection={<IconChevronDown size={16} />}
                  aria-label="Save or share the latest picture">
                  <Box visibleFrom="sm">Save / share</Box>
                  <Box hiddenFrom="sm">Save</Box>
                </Button>
              </Menu.Target>
              {/* Same cap the History card needed (v0.267.2): a dropdown this
                  tall flips upwards under a card halfway down the screen and
                  loses its first item off the top — scroll instead of clip. */}
              <Menu.Dropdown mah={420} style={{ overflowY: "auto" }}>
                <Menu.Label>Download</Menu.Label>
                {pictureRun.has_fits ? (
                  <Menu.Item leftSection={<IconPhotoDown size={16} />}
                    component="a" href={api.stackFullResPngUrl(safe, pictureRun.id)}>
                    {fullResPngLabel(pictureRun.canvas_w, pictureRun.canvas_h)}
                  </Menu.Item>
                ) : null}
                <Menu.Item leftSection={<IconPhotoDown size={16} />}
                  component="a" href={api.stackArtifactUrl(safe, pictureRun.id, "preview")}>
                  {pictureRun.has_fits ? "Quick preview PNG (up to 1024px)" : "PNG (best quality)"}
                </Menu.Item>
                <Menu.Item leftSection={<IconPhotoDown size={16} />}
                  component="a" href={api.stackArtifactUrl(safe, pictureRun.id, "jpeg")}>
                  JPEG (smaller — best for sharing)
                </Menu.Item>
                {/* The framed variant: the same picture matted on a dark card
                    with its name, date and total exposure set *beneath* it, so
                    the story travels with the file instead of living in a
                    caption box that never leaves the app. */}
                <Menu.Item leftSection={<IconPhotoDown size={16} />}
                  component="a"
                  href={api.stackArtifactUrl(
                    safe, pictureRun.id, "jpeg", false, false, true)}>
                  Framed keepsake
                  <span style={MENU_HINT}>
                    Its name, date and exposure printed on the picture
                  </span>
                </Menu.Item>
                {/* The two marks every published astrophoto carries — how big a
                    piece of sky this is, and which way round it is. The app
                    already draws them on screen, but a browser overlay doesn't
                    travel with the file, so the downloaded picture loses both.
                    Drawn from this run's own solve; a run that was never solved
                    simply gets the plain picture back. */}
                <Menu.Item leftSection={<IconPhotoDown size={16} />}
                  component="a"
                  href={api.stackArtifactUrl(
                    safe, pictureRun.id, "jpeg", false, false, false, true)}>
                  With scale &amp; compass
                  <span style={MENU_HINT}>
                    How big it is and which way is North, printed on the picture
                  </span>
                </Menu.Item>
                <Menu.Divider />
                <Menu.Label>Share</Menu.Label>
                <SharePictureButton
                  asMenuItem
                  url={api.stackArtifactUrl(safe, pictureRun.id, "jpeg")}
                  {...sharePictureText(
                    target.data?.name,
                    // The same date `LatestPictureCard`'s share text uses for the
                    // same picture — and it has to be the night the subs were
                    // *shot*, not the day the stack ran. This site was missed when
                    // the rest of the share sheet was fixed, so the app's most
                    // prominent picture went on announcing "captured <the day you
                    // pressed Process>": the same day only if you stack the night
                    // you shoot, and years out on a re-stack of a back catalogue.
                    // A run with no recorded window shares with no date at all.
                    captureLabel,
                  )}
                />
                {/* Share the *framed* variant. This is the one that matters on
                    Instagram or a printed 6×4: a share-sheet caption doesn't
                    travel with the file, so the plain share above arrives as an
                    unlabelled rectangle while this one carries its own story.
                    Same caption, but `filename` overrides the spread's so the
                    two shares can't land on top of each other in downloads.

                    It carries the *marks* too — the scale bar, the North/East
                    rose and the names of the catalog objects in the field. This
                    is the share meant for other people, and those three are what
                    make a picture read as a real astrophoto to someone who
                    wasn't there; the plain share above stays naked for anyone
                    who wants the bare picture. Every one of them is a clean
                    no-op server-side on a run that can't supply it (no solve, a
                    rotated or reshaped preview, an empty field), so this never
                    becomes a share that fails — it just carries less. */}
                <SharePictureButton
                  asMenuItem
                  label={<>
                    Share the keepsake
                    <span style={MENU_HINT}>
                      Framed, with its scale, which way is North, and what’s in it
                    </span>
                  </>}
                  ariaLabel="Share the framed keepsake"
                  url={api.stackArtifactUrl(
                    safe, pictureRun.id, "jpeg", false, false, true, true, true)}
                  {...sharePictureText(target.data?.name, captureLabel)}
                  filename={keepsakeFilename(
                    sharePictureText(target.data?.name).filename)}
                />
                {/* The QR opens in a modal owned by the page, not a popover owned
                    by this item — a menu closes on click, which would unmount its
                    own popover with it. */}
                <Menu.Item leftSection={<IconDeviceMobile size={16} />}
                  onClick={() => setToPhone(true)}>
                  To phone
                  <span style={MENU_HINT}>Scan a QR to open it on your phone</span>
                </Menu.Item>
                {/* Motion, for the places a still gets swiped past. Built and
                    cached server-side from this run's own preview, so it needs no
                    extra request to decide whether to offer it: every run with a
                    picture has one. */}
                <DownloadMenuItem
                  icon={<IconVideo size={16} />}
                  url={api.stackZoomClipUrl(safe, pictureRun.id)}
                  filename={`${pictureRun.output_basename || "stack"}_zoom.webp`}
                  label="Zoom clip"
                  hint="A few seconds gliding into your target — for posting"
                  busyHint="Building your clip — a few seconds the first time"
                  errorMessage="Couldn't build a zoom clip for this run."
                  hintStyle={MENU_HINT}
                />
                <Menu.Divider />
                <WallpaperMenuItems safe={safe} runId={pictureRun.id}
                  canNorthUp={wallpaperCanNorthUp} />
              </Menu.Dropdown>
            </Menu>
          ) : null}
          <Button component={Link} to={`/targets/${safe}/stack`}
            leftSection={<IconStack2 size={16} />} aria-label="Stack">
            Stack
          </Button>
        </Group>
      </Group>

      {/* What the user actually came for, above the fold (IA slice (c) of the
          owner's "the pages are extremely busy" item): the finished picture and
          — beside it, not below it — the one question a beginner opens this page
          with. Everything that *describes* the target (its catalog card and the
          insight tabs) now sits below the frames table, so the page opens onto
          content rather than analysis. Nothing was removed; it moved. */}
      <Grid gutter="xs">
        <Grid.Col span={{ base: 12, md: 7 }}>
          <LatestPictureCard safe={safe} name={target.data?.name} run={pictureRun}
            pinnedCover={showingOlderCover} />
          {/* Pre-stack reassurance: the sharpest sub, shown until a finished picture
              exists — then the real stack supersedes it. Deliberately *not* in a tab:
              it is the first-run guidance a brand-new target leans on. */}
          {!latestRun?.has_preview ? <FirstLookCard safe={safe} /> : null}
        </Grid.Col>
        {readiness ? (
          <Grid.Col span={{ base: 12, md: 5 }}>
            <Paper withBorder p="sm" radius="md">
              <Group gap="sm" wrap="nowrap" align="flex-start">
                <IconTargetArrow size={22} style={{ flexShrink: 0, marginTop: 2 }}
                  color={`var(--mantine-color-${readinessColor(readiness.level)}-5)`} />
                <Stack gap={6} style={{ flex: 1, minWidth: 0 }}>
                  <Group gap="xs" justify="space-between" wrap="nowrap">
                    <Text size="sm" fw={500}>Is it enough yet?</Text>
                    {editingGoal ? (
                      <Group gap={4} wrap="nowrap">
                        <NumberInput size="xs" w={78} min={0.25} max={1000} step={0.5}
                          suffix=" h" hideControls
                          aria-label="Integration goal (hours)"
                          value={goalHoursInput}
                          onChange={(v) =>
                            setGoalHoursInput(v === "" ? "" : Number(v))}
                        />
                        <Button size="compact-xs" variant="light" loading={setGoal.isPending}
                          onClick={() => {
                            const h = Number(goalHoursInput);
                            if (Number.isFinite(h) && h > 0) {
                              setGoal.mutate(Math.round(h * 3600));
                              setEditingGoal(false);
                            }
                          }}>Save</Button>
                        {goal.data?.goal_s != null ? (
                          <Button size="compact-xs" variant="subtle" color="gray"
                            onClick={() => {
                              setGoal.mutate(null);
                              setEditingGoal(false);
                            }}>Reset</Button>
                        ) : null}
                      </Group>
                    ) : (
                      <Text size="xs" c="dimmed"
                        style={{ whiteSpace: "nowrap", cursor: "pointer" }}
                        title="Set your own integration goal for this target"
                        onClick={() => {
                          setGoalHoursInput(Number(readiness.goalHours.toFixed(2)));
                          setEditingGoal(true);
                        }}>
                        {readiness.customGoal ? "your goal" : "goal"} ~{readiness.goalHours} h
                        {" "}✎
                      </Text>
                    )}
                  </Group>
                  <Progress value={readiness.fraction * 100}
                    color={readinessColor(readiness.level)} size="sm" radius="xl" />
                  <Text size="sm" c="dimmed">{readiness.verdict}</Text>
                  {/* "How many more clear nights?" — the goal gap projected forward at
                      this target's own recent pace, so "not yet" comes with a plan
                      rather than an open question. Self-hides when the goal is met or
                      there's too little history to judge a pace. */}
                  {clearNights ? (
                    <Text size="xs" c="dimmed">{clearNights.text}</Text>
                  ) : null}
                  {/* "Is more time worth it?" — answered from the measured grain of
                      this target's own deepest stack, which is strictly better than
                      the time-goal fraction above once a real picture exists: it can
                      say "already clean" where the goal says "keep going", or quote
                      the light this one actually still needs where the goal says
                      "plenty". Falls back to the goal-independent √N line whenever
                      there's no measured stack yet (and defers to the measured
                      plateau verdict when there is a trend to read). */}
                  {grain ? (
                    <Text size="xs" c="dimmed" data-testid="grain-projection">
                      {grain.sentence}
                    </Text>
                  ) : noiseReductionHint(target.data?.total_exposure_s ?? 0) ? (
                    <Text size="xs" c="dimmed">
                      {noiseReductionHint(target.data?.total_exposure_s ?? 0)}
                    </Text>
                  ) : null}
                </Stack>
              </Group>
            </Paper>
          </Grid.Col>
        ) : null}
      </Grid>

      <Grid>
        <Grid.Col span={{ base: 12, md: 7 }}>
          <Group mb="xs" gap="xs" align="flex-end">
            <Select size="xs" label="Reject worst by" w={150} value={rejectMetric}
              allowDeselect={false} data={REJECT_METRICS}
              onChange={(v) => setRejectMetric(v ?? "fwhm_px")} />
            <NumberInput size="xs" label="Percent" w={90} min={1} max={90} suffix="%"
              value={rejectPct} onChange={(v) => setRejectPct(Number(v) || 10)} />
            <Button size="xs" variant="light" color="red" loading={bulk.isPending}
              onClick={() => {
                const label = REJECT_METRICS.find((m) => m.value === rejectMetric)?.label;
                if (window.confirm(`Reject the worst ${rejectPct}% of accepted frames by ${label}?`)) {
                  bulk.mutate({ action: "reject_worst", metric: rejectMetric, fraction: rejectPct / 100 });
                }
              }}>
              Reject worst
            </Button>
            <Tooltip
              multiline w={280}
              label="Find statistical outliers across all quality metrics (trailed, cloud-hit, hazy subs) with a plain-language reason for each — preview first, then reject in one click."
            >
              <Button size="xs" variant="light" color="violet"
                leftSection={<IconSparkles size={14} />}
                onClick={() => setGradeOpen(true)}>
                Auto-grade
              </Button>
            </Tooltip>
          </Group>
          <AutoGradeModal
            safe={safe}
            opened={gradeOpen}
            onClose={() => setGradeOpen(false)}
            onApplied={(ids) => {
              qc.invalidateQueries({ queryKey: ["frames", safe] });
              qc.invalidateQueries({ queryKey: ["target", safe] });
              qc.invalidateQueries({ queryKey: ["reject-summary", safe] });
              qc.invalidateQueries({ queryKey: ["auto-grade", safe] });
              if (ids.length) setLastReject({ ids, label: "auto-grade" });
            }}
          />
          {/* The column headings explain themselves on hover — which is to say,
              not at all on a phone. One line until it's asked for. The keyboard
              shortcuts that used to sit above this line now live inside it: a
              permanent "Keys: j/k move · a accept · r reject" is an instruction
              for hardware a phone doesn't have, and this disclosure already
              carries the sibling sentence about tapping a heading to sort. */}
          <FrameColumnGuide />
          <Paper withBorder>
            <Table.ScrollContainer minWidth={620} mah="65vh">
              <Table stickyHeader highlightOnHover>
                <Table.Thead>
                  <Table.Tr>
                    <Table.Th w={40}></Table.Th>
                    {cols.map((c) => (
                      <Table.Th
                        key={c.key}
                        onClick={() => setSortCol(c.key)}
                        style={{ cursor: "pointer" }}
                      >
                        {c.hint ? (
                          <Tooltip multiline w={240} label={c.hint}>
                            <span style={{ textDecoration: "underline dotted" }}>{c.label}</span>
                          </Tooltip>
                        ) : c.label}
                        {sort === c.key ? (order === "asc" ? " ▲" : " ▼") : ""}
                      </Table.Th>
                    ))}
                    <Table.Th w={50}>OK</Table.Th>
                  </Table.Tr>
                </Table.Thead>
                <Table.Tbody>
                  {list.map((f: Frame) => (
                    <Table.Tr
                      key={f.id}
                      onClick={() => setSelected(f.id)}
                      bg={selectedFrame?.id === f.id ? "var(--mantine-color-violet-light)" : undefined}
                      opacity={f.accept ? 1 : 0.45}
                      style={{ cursor: "pointer" }}
                    >
                      <Table.Td>
                        {f.solved ? (
                          <Tooltip label="Plate solved">
                            <IconTelescope size={14} color="var(--mantine-color-teal-5)" />
                          </Tooltip>
                        ) : null}
                      </Table.Td>
                      <Table.Td>
                        <Group gap={6} wrap="nowrap">
                          <span>{f.timestamp_utc?.replace("T", " ").slice(0, 19) ?? "—"}</span>
                          {!f.accept && f.reject_reason ? (
                            <Tooltip label={`Rejected — ${rejectReasonLabel(f.reject_reason)}`}>
                              <Badge size="xs" color="gray" variant="light" style={{ flexShrink: 0 }}>
                                {rejectReasonLabel(f.reject_reason)}
                              </Badge>
                            </Tooltip>
                          ) : null}
                        </Group>
                      </Table.Td>
                      <Table.Td>{NUM(f.fwhm_px)}</Table.Td>
                      <Table.Td>{f.star_count ?? "—"}</Table.Td>
                      <Table.Td>{NUM(f.eccentricity_median)}</Table.Td>
                      <Table.Td><NumberFormatter value={f.sky_adu_median ?? 0} decimalScale={0} /></Table.Td>
                      <Table.Td>
                        {f.transparency_score == null
                          ? "—"
                          : <NumberFormatter value={f.transparency_score} decimalScale={0} />}
                      </Table.Td>
                      <Table.Td>
                        <ActionIcon
                          size="sm"
                          variant={f.accept ? "filled" : "subtle"}
                          color={f.accept ? "teal" : "red"}
                          aria-label={f.accept ? "Reject frame" : "Accept frame"}
                          onClick={(e) => {
                            e.stopPropagation();
                            patch.mutate({ id: f.id, body: { accept: !f.accept } });
                          }}
                        >
                          {f.accept ? <IconCheck size={14} /> : <IconX size={14} />}
                        </ActionIcon>
                      </Table.Td>
                    </Table.Tr>
                  ))}
                </Table.Tbody>
              </Table>
            </Table.ScrollContainer>
          </Paper>
        </Grid.Col>

        <Grid.Col span={{ base: 12, md: 5 }}>
          <Paper withBorder p="md">
            <Group justify="space-between" mb="sm">
              <Text fw={600}>Preview</Text>
              <Select
                size="xs"
                placeholder="Bayer"
                w={110}
                data={["RGGB", "BGGR", "GRBG", "GBRG"]}
                value={bayer ?? null}
                onChange={(v) => setBayer(v ?? undefined)}
                clearable
              />
            </Group>
            {selectedFrame ? (
              <Stack gap="xs">
                <Box style={{ background: "#000", borderRadius: 8, overflow: "hidden" }}>
                  <Image
                    src={api.framePreviewUrl(safe, selectedFrame.id, 700, bayer)}
                    alt={selectedFrame.name}
                    fallbackSrc=""
                  />
                </Box>
                <Text size="sm" fw={500}>{selectedFrame.name}</Text>
                <Group gap="lg">
                  <Text size="xs" c="dimmed">FWHM {NUM(selectedFrame.fwhm_px)}</Text>
                  <Text size="xs" c="dimmed">Stars {selectedFrame.star_count ?? "—"}</Text>
                  <Text size="xs" c="dimmed">Exp {NUM(selectedFrame.exposure_s, 0)}s</Text>
                </Group>
                {(selectedFrame.ra_hint_deg != null || selectedFrame.solved) ? (
                  <Group gap="lg">
                    {selectedFrame.ra_hint_deg != null ? (
                      <Text size="xs" c="dimmed">
                        Target {NUM(selectedFrame.ra_hint_deg, 3)}°, {NUM(selectedFrame.dec_hint_deg, 3)}°
                      </Text>
                    ) : null}
                    {selectedFrame.solved ? (
                      <Text size="xs" c="teal">
                        Solved {NUM(selectedFrame.ra_center_deg, 3)}°, {NUM(selectedFrame.dec_center_deg, 3)}°
                      </Text>
                    ) : null}
                  </Group>
                ) : null}
              </Stack>
            ) : (
              <Center h={240}>
                <IconPhoto size={48} color="var(--mantine-color-dark-3)" />
              </Center>
            )}
          </Paper>

          {target.data ? (
            <Box mt="md">
              <NotesPanel safe={safe} notes={target.data.notes} tags={target.data.tags} />
            </Box>
          ) : null}
        </Grid.Col>
      </Grid>

      {identity.data ? (
        <Box mt="xs">
          <ObjectInfoCard safe={safe} hideFraming={!!measuredFraming} />
        </Box>
      ) : null}

      {/* The page's analysis cards, grouped instead of stacked (IA slice (b) of the
          owner's "the pages are extremely busy" item) and now *below* the frames
          table rather than above it (slice (c)). Nine full cards used to sit one
          below another before the table; they are all still here, still one click
          away, but only one group is on screen at a time. A group whose cards have
          nothing to say gets no tab at all — see `InsightTabs`. A later analysis
          card should join a group here rather than add a tenth stacked card. */}
      <InsightTabs
        data-testid="target-insights"
        groups={[
          { key: "overview", label: "Overview", node: (
            <>
              <SessionRecapCard safe={safe} />
              <NightsCard safe={safe} />
            </>
          ) },
          { key: "quality", label: "Quality", node: (
            <>
              <FocusTrendCard safe={safe} />
              <TransparencyTrendCard safe={safe} />
              <StackHealthCard safe={safe} />
            </>
          ) },
          { key: "planning", label: "Planning", node: (
            <>
              {/* Forward-looking companion to "Is it enough yet?" (which stays
                  inline below — it answers the question the beginner came with):
                  when there's still a goal gap, join it with the night planner's
                  next dark window(s) for this object. Self-hides when the goal's
                  met or no window can be computed. */}
              {readiness ? (
                <NextSessionCard
                  safe={safe}
                  gapSeconds={Math.max(0, (readiness.goalHours - readiness.hours) * 3600)}
                  subExposureSeconds={
                    target.data && target.data.n_frames_accepted > 0
                      ? target.data.total_exposure_s / target.data.n_frames_accepted
                      : null
                  }
                  /* The nights-to-go figure the readiness card already derives
                     from this target's own pace — handed over so the card can
                     turn "2 more clear nights" into a date the planner can
                     actually vouch for. */
                  nightsToGo={clearNights?.nights ?? null}
                />
              ) : null}
              {/* Which months of the year this object is actually up. Self-hides
                  without a location/position. */}
              <BestMonthsStrip safe={safe} />
              {/* "Is the Moon going to wash this out tonight?" — a plain-language
                  Moon-interference readout so a beginner points at a bright target
                  instead of wasting a bright-Moon night. Self-hides without a
                  location/position. */}
              <MoonInterferenceCard safe={safe} />
            </>
          ) },
          { key: "story", label: "Story", node: (
            /* "Night after night" — the same target getting deeper across
               re-stacks (self-hides until there are ≥2 stacks to compare). */
            <DeepeningReelCard safe={safe} name={target.data?.name} />
          ) },
        ]}
      />

      {latestRun?.has_preview ? (
        <ScanToPhoneModal
          url={api.stackArtifactUrl(safe, latestRun.id, "jpeg")}
          opened={toPhone}
          onClose={() => setToPhone(false)}
        />
      ) : null}

    </Stack>
  );
}
