import {
  ActionIcon, Alert, Badge, Box, Button, Center, Grid, Group, HoverCard, Image,
  Loader, Menu, Modal, NumberFormatter, NumberInput, Paper, Progress, Select, Stack,
  Table, TagsInput, Text, Textarea, Title, Tooltip,
} from "@mantine/core";
import {
  IconAlertTriangle, IconArrowBackUp, IconCheck, IconDeviceFloppy, IconHistory,
  IconNotes, IconPhoto, IconPhotoDown, IconSparkles, IconStack2, IconTelescope,
  IconTargetArrow, IconWand, IconX,
} from "@tabler/icons-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { notifications } from "@mantine/notifications";
import { api, type Frame } from "../api/client";
import { formatIntegration } from "../format";
import { integrationReadiness, readinessColor, noiseReductionHint } from "../readiness";
import { QueryError } from "../components/QueryError";
import { ObjectInfoCard, describeObject } from "../components/ObjectInfoCard";
import { NightsCard } from "../components/NightsCard";
import { FocusTrendCard } from "../components/FocusTrendCard";
import { TransparencyTrendCard } from "../components/TransparencyTrendCard";
import { NextSessionCard } from "../components/NextSessionCard";
import { DeepeningReelCard } from "../components/DeepeningReelCard";
import { SessionRecapCard } from "../components/SessionRecapCard";
import { StackHealthCard } from "../components/StackHealthCard";
import { StackNoiseBadge } from "../components/StackNoiseBadge";
import { FirstLookCard } from "../components/FirstLookCard";
import { WallpaperMenu } from "../components/WallpaperMenu";
import { SharePictureButton } from "../components/SharePictureButton";
import { sharePictureText } from "../share";
import { detectSolveSetupProblem } from "../components/target/solveSetup";
import { RejectionBreakdown } from "../components/target/RejectionBreakdown";
import { thinStackWarning } from "../components/target/thinStack";
import { detectMixedPointings } from "../components/target/mixedPointings";

// Re-exported for existing tests that import it from this route module.
export { describeObject };

const NUM = (v: number | null, digits = 2) =>
  v === null || v === undefined ? "—" : v.toFixed(digits);

type SortKey = "id" | "timestamp_utc" | "fwhm_px" | "star_count" | "eccentricity_median" | "sky_adu_median" | "transparency_score";

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
  const frames = useQuery({
    queryKey: ["frames", safe, sort, order],
    queryFn: () => api.listFrames(safe, sort, order),
  });
  const runs = useQuery({ queryKey: ["runs", safe], queryFn: () => api.listStackRuns(safe) });
  const latestRun = runs.data?.[0];  // listStackRuns returns newest first
  // Honest heads-up when the newest stack combined very few frames — it will
  // look noisy (a stack only smooths noise as it combines more subs), so say so
  // rather than presenting a single-sub result as a finished picture.
  const thinStack = useMemo(
    () => thinStackWarning(latestRun?.n_frames_used),
    [latestRun],
  );

  const patch = useMutation({
    mutationFn: ({ id, body }: { id: number; body: Record<string, unknown> }) =>
      api.patchFrame(safe, id, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["frames", safe] });
      qc.invalidateQueries({ queryKey: ["target", safe] });
    },
  });

  const bulk = useMutation({
    mutationFn: (body: Record<string, unknown>) => api.bulkFrames(safe, body),
    onSuccess: (r, body) => {
      notifications.show({ message: `Updated ${r.changed} frames`, color: "violet" });
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

  const cols: { key: SortKey; label: string; hint?: string }[] = [
    { key: "timestamp_utc", label: "Time (UTC)" },
    {
      key: "fwhm_px", label: "FWHM",
      hint: "Full-width-half-maximum: how many pixels wide the stars are. "
        + "Lower = sharper. Rises with poor seeing, focus drift or clouds.",
    },
    {
      key: "star_count", label: "Stars",
      hint: "Number of stars detected in the frame. Drops on hazy or "
        + "cloud-affected subs. Higher is generally better.",
    },
    {
      key: "eccentricity_median", label: "Ecc.",
      hint: "Median star eccentricity (elongation): 0 = perfectly round, "
        + "closer to 1 = trailed. High values flag tracking error, wind or a "
        + "mount bump on that whole sub. Lower is better.",
    },
    {
      key: "sky_adu_median", label: "Sky",
      hint: "Median sky-background level of the frame. Rises with moonlight, "
        + "light pollution or thin cloud. Lower is darker (better).",
    },
    {
      key: "transparency_score", label: "Transp.",
      hint: "Transparency: median brightness of the frame's brightest stars. "
        + "Higher = clearer sky; low values flag haze or thin cloud. Relative, "
        + "comparable across this target's frames.",
    },
  ];

  return (
    <Stack>
      {solveSetup ? (
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
              component={Link} to="/settings">
              Open Settings
            </Button>
          </Group>
        </Alert>
      ) : null}
      {needsProcessing ? (
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
      ) : null}
      {newSubsSinceStack > 0 ? (
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
      ) : null}
      {qcUncheckable > 0 ? (
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
      ) : null}
      {mixedRejected !== null ? (
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
      ) : mixedPointings ? (
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
      ) : null}
      {thinStack ? (
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
      ) : null}
      {/* The concrete "stacking cut your noise ~N×" payoff, right where a beginner
          lands on the finished picture (self-hides for a thin/unmeasurable stack). */}
      {latestRun?.has_preview ? (
        <StackNoiseBadge safe={safe} runId={latestRun.id}
          nFrames={latestRun.n_frames_used ?? null} />
      ) : null}
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
                  color={unsolvedCount > 0 && rejectedCount === 0 ? "orange" : "gray"}
                  style={{ cursor: "help" }}
                >
                  {unsolvedCount > 0 && rejectedCount === 0
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
          </Button>
          <Button
            variant="default"
            leftSection={<IconTelescope size={16} />}
            onClick={() => qcSolve.mutate()}
            loading={qcSolve.isPending}
            aria-label="Re-run QC and Solve"
          >
            <Box visibleFrom="sm">Re-run QC + Solve</Box>
          </Button>
          <Button component={Link} to={`/targets/${safe}/history`} variant="default"
            leftSection={<IconHistory size={16} />} aria-label="History">
            <Box visibleFrom="sm">History</Box>
          </Button>
          {latestRun ? (
            <Button component={Link} to={`/targets/${safe}/edit/${latestRun.id}`} variant="default"
              leftSection={<IconWand size={16} />} aria-label="Edit latest stack">
              <Box visibleFrom="sm">Edit</Box>
            </Button>
          ) : null}
          {latestRun?.has_preview ? (
            <Menu shadow="md" position="bottom-end" withinPortal>
              <Menu.Target>
                <Tooltip label="Download the latest finished picture (PNG or JPEG)">
                  <Button variant="default" leftSection={<IconPhotoDown size={16} />}
                    aria-label="Download latest picture">
                    <Box visibleFrom="sm">Picture</Box>
                  </Button>
                </Tooltip>
              </Menu.Target>
              <Menu.Dropdown>
                <Menu.Item component="a" href={api.stackArtifactUrl(safe, latestRun.id, "preview")}>
                  PNG (best quality)
                </Menu.Item>
                <Menu.Item component="a" href={api.stackArtifactUrl(safe, latestRun.id, "jpeg")}>
                  JPEG (smaller — best for sharing)
                </Menu.Item>
              </Menu.Dropdown>
            </Menu>
          ) : null}
          {latestRun?.has_preview ? (
            <SharePictureButton
              url={api.stackArtifactUrl(safe, latestRun.id, "jpeg")}
              variant="default"
              {...sharePictureText(
                target.data?.name,
                new Date(latestRun.timestamp_utc).toLocaleDateString(),
              )}
            />
          ) : null}
          {latestRun?.has_preview ? (
            <WallpaperMenu safe={safe} runId={latestRun.id} size="sm" variant="default" />
          ) : null}
          <Button component={Link} to={`/targets/${safe}/stack`}
            leftSection={<IconStack2 size={16} />} aria-label="Stack">
            <Box visibleFrom="sm">Stack</Box>
          </Button>
        </Group>
      </Group>

      {identity.data ? (
        <Box mt="xs"><ObjectInfoCard safe={safe} /></Box>
      ) : null}

      <SessionRecapCard safe={safe} />

      <NightsCard safe={safe} />

      <FocusTrendCard safe={safe} />

      <TransparencyTrendCard safe={safe} />

      <StackHealthCard safe={safe} />

      {/* "Night after night" — the same target getting deeper across re-stacks
          (self-hides until there are ≥2 stacks to compare). */}
      <DeepeningReelCard safe={safe} name={target.data?.name} />

      {/* Pre-stack reassurance: the sharpest sub, shown until a finished picture
          exists — then the real stack supersedes it. */}
      {!latestRun?.has_preview ? <FirstLookCard safe={safe} /> : null}

      {readiness ? (
        <Paper withBorder p="sm" radius="md" mt="xs">
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
              {/* The honest √N diminishing-returns figure: how much more a single
                  extra hour would cut background noise, so "keep shooting?" gets a
                  physics-based answer, not just a goal-fraction. */}
              {noiseReductionHint(target.data?.total_exposure_s ?? 0) ? (
                <Text size="xs" c="dimmed">
                  {noiseReductionHint(target.data?.total_exposure_s ?? 0)}
                </Text>
              ) : null}
            </Stack>
          </Group>
        </Paper>
      ) : null}

      {/* Forward-looking companion to "Is it enough yet?": when there's still a
          goal gap, join it with the night planner's next dark window(s) for this
          object. Self-hides when the goal's met or no window can be computed. */}
      {readiness ? (
        <NextSessionCard
          safe={safe}
          gapSeconds={Math.max(0, (readiness.goalHours - readiness.hours) * 3600)}
          subExposureSeconds={
            target.data && target.data.n_frames_accepted > 0
              ? target.data.total_exposure_s / target.data.n_frames_accepted
              : null
          }
        />
      ) : null}

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
          <Text size="xs" c="dimmed" mb={4}>
            Keys: <b>j</b>/<b>k</b> move · <b>a</b> accept · <b>r</b> reject
          </Text>
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
    </Stack>
  );
}
