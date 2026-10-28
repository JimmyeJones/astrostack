import {
  Accordion, Alert, Anchor, Badge, Button, Center, Code, Collapse, CopyButton, Divider,
  FileButton, Group, Loader, NumberInput, Paper, Radio, SimpleGrid, Stack, Switch,
  TagsInput, Text, TextInput, Title,
} from "@mantine/core";
import {
  IconDeviceFloppy, IconDownload, IconInfoCircle, IconPlus, IconRefresh,
  IconTelescope, IconTrash, IconUpload,
} from "@tabler/icons-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState, type ReactNode } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { notifications } from "@mantine/notifications";
import {
  api, type AutoCastSummary, type AutoHighlightSummary, type ReprocessStatus,
} from "../api/client";
import { dependencyMet } from "../api/depends";
import { compassPoint } from "../tonight";
import { RefinishPicturesCard } from "../components/RefinishPicturesCard";
import { UpdatesCard } from "../components/UpdatesCard";
import { HintLabel, StackOptionControl } from "../components/StackOptionControl";
import { AmbientSettings } from "../components/AmbientSettings";
import { NightSkySettings } from "../components/NightSkySettings";
import { SkylineEditor } from "../components/SkylineEditor";
import { SectionTabs, type PageSection } from "../components/SectionTabs";
import { MoreSettingsSection } from "../components/settings/MoreSettings";
import { FramePickySection } from "../components/settings/FramePicky";
import { HandsOffSection } from "../components/settings/HandsOff";
import { NasSection } from "../components/settings/NasSection";
import { PicturesSection } from "../components/settings/PicturesMade";
import {
  ObservingSiteSection, PLAN_SITE_QUERY_KEY,
} from "../components/settings/ObservingSite";
import { settingsLink, type SettingsSection } from "../settingsSections";
import { minMaxIgnoresWeightingHint } from "../weightingHint";
import { folderConflict, settingsErrorMessage } from "../settingsFolders";
import { readonlyCurlExample, readonlyTokenBlurb } from "../readonlyToken";
import { formatDiskSize } from "../format";

// Hover hints for every setting (shown via an info icon next to the label).
// Exported so the copy that explains a *silent* decision — one the app makes on
// the user's behalf when they aren't there to make it — can be pinned by a test
// rather than quietly drifting away from what the pipeline actually does.
export const HINTS: Record<string, string> = {
  data_root: "Root folder on the mounted dataset. Holds incoming/, library/ and state/.",
  incoming_dir: "Folder watched for new Seestar data. Blank = <data root>/incoming.",
  library_root: "Where organised per-target projects and stacks are stored. Blank = <data root>/library.",
  watcher_enabled: "Automatically detect and process new files dropped into the incoming folder.",
  watch_quiet_period_s:
    "A file must stay unchanged this many seconds before it's read, so half-copied frames arriving over SMB/NFS aren't read mid-write.",
  watch_poll_interval_s:
    "How often to re-scan the incoming folder as a safety net, for when filesystem change events aren't delivered (common on network mounts).",
  auto_ingest: "On new files: register them into the library, grouped per target.",
  auto_qc: "On new files: compute quality metrics (FWHM, star count, eccentricity, sky level).",
  auto_solve: "On new files: plate-solve with ASTAP so frames can be aligned and placed on the sky.",
  auto_stack: "On new files: also stack each touched target automatically (uses the defaults below, or a target's saved defaults). On for new installs — it's what makes \"drop your subs in and come back to a picture\" actually happen; if you've had AstroStack a while it keeps whatever you last set here. Because you're not there to choose, a hands-off stack makes two decisions for you: it removes outliers (satellite and plane trails) automatically, and it leans on your sharper, clearer subs rather than treating a soft or hazy one as equal. Both only apply when you haven't picked for yourself — anything you set below, or saved as a target's defaults, is used exactly as you left it, and the Stack form is never touched. It waits for the night to settle first, holds back a target with too few located subs, and never replaces a good picture with a thinner one.",
  auto_edit_on_autostack: "After an automatic stack, also auto-edit the master into a finished picture (the same one-click Auto processing), so an unattended run comes back to a great image, not a flat linear master. On for new installs — it's the last step of \"drop your subs in and come back to a picture\"; if you've had AstroStack a while it keeps whatever you last set here. Nothing is done to you that you can't undo: the picture is one Reset from the plain stack in the editor, an edit you save yourself is never written over, and under any picture it finished you'll find a link to leave that one target's pictures alone from now on. Needs Auto-stack on.",
  auto_stack_settle_min: "How long a target must go without a new sub before a hands-off auto-stack will make its picture. While you're still shooting, every batch of subs that arrives would otherwise re-stack the whole target — all of it, every night — only to be replaced by the next batch a few minutes later, so the box stacks all night and the picture you come back to is of a night that wasn't over. Waiting 20 minutes means one stack, of the whole night, once you've stopped. Nothing is ever skipped: a target that's still receiving subs simply waits, and stacks on the first check after they stop. Set to 0 to stack after every batch. The Stack form and Process-target button are unaffected.",
  auto_stack_min_frames: "How many of a target's subs must be located (plate-solved) before a hands-off auto-stack will make a picture. A faint field where ASTAP can only locate one or two subs would otherwise auto-stack a single frame — pure colour noise. Below this floor the target waits (\"held for more located subs\") and stacks itself the moment enough subs solve. 3 is a good default; set to 1 to stack from the very first located sub. The Stack form and Process-target button are unaffected.",
  auto_reject_on_unattended: "On hands-off stacks (auto-stack and Process target), let AstroStack choose how to remove satellite and plane trails — even for a target whose saved defaults already name a method. It picks per stack, from how many subs actually land on each spot: min/max on a small stack, sigma clipping once there are enough subs for it to bite. Worth turning on if you once saved sigma clipping: on its own, sigma clipping can't pick out a lone trail below about 11 subs, so short nights (and every panel of a mosaic) keep the trail. Off by default, and it never touches the Stack form — a stack you set up by hand always uses exactly what you picked.",
  auto_drizzle: "On hands-off stacks (auto-stack and Process target), let AstroStack use super-resolution (drizzle) when your subs can actually pay for it — you come back to a picture bigger, and genuinely sharper, than a single frame. It only does it when the target is deep: about 200 subs on each patch of sky (on a mosaic that means each patch, not the total), and only when your subs moved slightly between frames, which is what gives a finer grid something extra to pick up. Thin targets, undithered ones, and canvases too big for the stack memory budget are stacked exactly as before, and every picture says in its History panel which it was and why. A target where you ticked (or cleared) Drizzle yourself always keeps your choice, the Stack form is never touched, and \"Reprocess everything\" re-makes each picture the way it was made before.",
  auto_crop_border: "When the one-click Auto edit finishes a mosaic or dithered stack, trim the ragged, uneven edge away so the picture is cleanly framed. Turn this off to keep the whole frame exactly as it was stacked — nothing else about Auto changes, and the editor's \"Trim border\" button still crops by hand whenever you want it. Applies to Auto-process in the editor and to the hands-off chains (Process target, auto-edit, Reprocess everything).",
  auto_bind_calibration: "When a hands-off stack (auto-stack, Process target, or Reprocess everything) has no calibration masters chosen, automatically use the library's best matching master dark/flat/bias for it — so a stack you didn't set up by hand is still calibrated. Only a confident match is used (a dark whose exposure matches your subs within 25%); if nothing matches, the stack is left uncalibrated as before. The Stack form is unaffected — it always uses exactly what you pick.",
  mixed_pointing_guard: "Before a hands-off stack (auto-stack or Process target), check whether the target's solved frames actually point at one object. If they look like two different targets accidentally dropped in one folder (a mosaic never trips it), skip the stack with a message instead of silently combining only one pointing and wasting the run. Open the Frames table and reject the odd-target frames, then stack. The Stack form is unaffected — it already warns you before you stack.",
  copy_to_cache: "Copy each frame into a fast local cache before processing. Helps with slow or network-mounted sources.",
  keep_streaked_frames: "Don't auto-reject a whole frame when QC finds a satellite/plane trail — keep it (flagged) so a stack with sigma-clip or drizzle rejection removes just the streak and keeps the frame's good signal. Only turn on if you stack with rejection enabled.",
  auto_grade_frames: "After QC, automatically reject frames that are clear statistical outliers versus the rest of the target (trailed, cloud-hit or hazy subs), each with a plain-language reason. The same grading is available manually via Auto-grade on a target's page. Frames you graded yourself are never touched.",
  auto_grade_sensitivity: "How strict auto-grading is. Balanced suits most data; Conservative only drops gross outliers; Aggressive cuts deeper into marginal frames.",
  astap_path: "Path to the ASTAP executable. Blank = auto-detect (bundled binary → $SEESTACK_ASTAP_PATH → PATH).",
  astap_fov_deg: "Approximate field of view in degrees, used as a solving hint only when a frame's own header doesn't say — normally it does, and the app reads the real field from each frame (a Seestar S30 sees about 2.1°, an S50 about 1.3°). Leave it alone unless solving keeps failing.",
  astap_timeout_s: "Give up on each solve attempt after this many seconds. The solver tries up to 3 strategies per frame, so a frame that never solves can take up to about 3× this before it's set aside (and retried on the next scan).",
  cpu_workers: "CPU workers for QC / solve / stack. Blank = all cores.",
  max_stack_memory_gb: "Working-memory cap for a single stack. Blank = auto (~70% of RAM). Raise it on a big box to allow larger drizzle/mosaic canvases; lower it to leave more headroom. The ASTROSTACK_MAX_STACK_GB env var, if set, overrides this.",
  job_history_limit: "How many finished jobs to keep in the Jobs history (the jobs.sqlite database retains about 10× this). Higher keeps more history at the cost of a slightly larger DB. Takes effect immediately. Default 200.",
  astap_use_solve_hints: "Use each frame's telescope target RA/Dec (from its FITS header) to localise ASTAP's search — faster, more reliable solving. Turn off if your frames lack/contain wrong coordinates.",
  astap_bootstrap_solve: "On a faint or star-poor target, a single 10s sub often can't be located in the sky, so most subs are left out and your picture stays noisy. With this on, the app quietly combines the un-located subs into one deeper image, locates that, and copies the position back to each sub — so the whole night can stack. Off by default; turn it on if faint targets keep coming out noisy with 'not located yet' subs.",
  seestar_enabled: "Discover and monitor Seestar telescopes on the LAN via their unofficial local API (port 4700). The container must be able to reach the scope (Station mode).",
  seestar_control_enabled: "Allow sending commands (goto / start / stop / park) to the scope. Off = monitoring only, so watching can never disturb a session.",
  seestar_scan_subnet: "CIDR to scan for scopes, e.g. 192.168.1.0/24. Blank = auto-detect from the container's network.",
  seestar_known_ips: "Pin specific Seestar IPs that auto-discovery can't reach.",
  seestar_scan_interval_s: "How often to re-scan the network for devices.",
  seestar_poll_interval_s: "How often to poll each connected scope for telemetry.",
  site_lat: "Your observing latitude in degrees (north positive). Used by the Tonight planner. Leave blank to read it automatically from a plate-solved Seestar frame.",
  site_lon: "Your observing longitude in degrees (east positive). Used by the Tonight planner. Leave blank to read it automatically from a plate-solved Seestar frame.",
  site_elevation_m: "Your elevation above sea level in metres (a small refinement to the Tonight planner; 0 is fine for most).",
  min_target_altitude_deg: "How high a target must climb to count as usable in the Tonight planner. 30° is a good default; lower it for an open horizon, raise it if trees/buildings block low altitudes.",
  horizon_profile: "Optional: map where trees, buildings or the house block your low sky, so the Tonight planner only counts a target as usable while it's actually clear of them. Drag the skyline up where the sky is blocked, or type the numbers yourself under “Fine-tune exact points”: each point is a compass direction (azimuth: 0°=N, 90°=E, 180°=S, 270°=W) and the minimum altitude that's unobstructed there; the planner interpolates between points. Leave it flat for an open horizon.",
};

// Walk-away mode: one beginner-facing toggle that drives the whole unattended
// "drop your subs in, come back to a finished picture" bundle, instead of five
// separate advanced switches a non-expert never finds. It is pure UI convenience
// over the *existing* settings — flipping it on/off sets/clears these five, and
// every one stays individually editable below. No new persisted field, so an
// upgraded install with these untouched behaves exactly as before.
export const WALK_AWAY_KEYS = [
  "auto_stack",
  "auto_edit_on_autostack",
  "auto_bind_calibration",
  "auto_grade_frames",
  "mixed_pointing_guard",
] as const;

export function walkAwayEnabled(form: Record<string, unknown>): boolean {
  return WALK_AWAY_KEYS.every((k) => Boolean(form[k]));
}

export function withWalkAway(
  form: Record<string, unknown>,
  on: boolean,
): Record<string, unknown> {
  const next = { ...form };
  for (const k of WALK_AWAY_KEYS) next[k] = on;
  return next;
}

/**
 * Settings whose stored value is *meaningfully* blank.
 *
 * `dropEmptyFields` below drops an emptied box so a cleared numeric can't 422
 * the whole save — but these three are strings whose blank is a real answer
 * ("the standard folder under the data root"; "work the subnet out for me"),
 * and dropping their `""` took away the only way back from a custom value:
 * clearing **Incoming dir** and pressing Save kept the old path, silently, for
 * ever. `data_root` is deliberately *not* here — it has no blank meaning, so an
 * emptied one must keep the installed path rather than repoint the app at
 * nothing. `astap_path` isn't either: its own control already sends `null`.
 */
export const BLANKABLE_FIELDS = new Set([
  "incoming_dir",
  "library_root",
  "seestar_scan_subnet",
]);

// Drop keys the user emptied out (value === "") before PUTting the settings
// patch. A cleared *non-nullable* numeric field (quiet period, ASTAP FOV, …)
// would otherwise be sent as 0 or "" and fail the backend's ge= bounds with a
// raw 422 — losing every *other* edit in the form behind a pydantic toast.
// Omitting the emptied field instead keeps its stored value and lets the rest
// save. Nullable fields the user explicitly clears send `null` (not ""), so
// they are preserved here and still cleared server-side — as are the fields
// above, for which blank is the value rather than the absence of one.
export function dropEmptyFields(
  patch: Record<string, unknown>,
): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  for (const [k, v] of Object.entries(patch)) {
    if (v === "" && !BLANKABLE_FIELDS.has(k)) continue;
    out[k] = v;
  }
  return out;
}

/**
 * The Settings page's sections, in the order a beginner meets them.
 *
 * Each is named for what it holds, so "which page is that setting on?" is
 * answerable from the tab label alone — the test the information-architecture
 * overhaul sets. Exported so a test can read the page's shape (and check every
 * section the app links to really exists) without rendering it.
 */
export const SETTINGS_PAGE_SECTIONS: { key: SettingsSection; label: string }[] = [
  { key: "folders", label: "Folders" },
  { key: "automation", label: "Automation" },
  { key: "plate-solving", label: "Plate solving" },
  { key: "observing-site", label: "Observing site" },
  { key: "stacking", label: "Stacking" },
  { key: "telescope", label: "This device" },
  { key: "maintenance", label: "Maintenance" },
  { key: "more", label: "More settings" },
];

type HorizonPoint = [number, number];

// Editor for the Tonight planner's horizon / tree-cover mask: a small list of
// (azimuth, min-clear-altitude) points. Empty = a flat, unobstructed horizon.
function HorizonProfileEditor(
  { value, onChange }: { value: HorizonPoint[]; onChange: (v: HorizonPoint[]) => void },
) {
  const points = Array.isArray(value) ? value : [];
  const setPoint = (i: number, j: 0 | 1, v: number) => {
    const next = points.map((p) => [...p] as HorizonPoint);
    next[i][j] = v;
    onChange(next);
  };
  const addPoint = () => onChange([...points, [0, 20]]);
  const removePoint = (i: number) => onChange(points.filter((_, k) => k !== i));

  return (
    <Stack gap="xs">
      {points.length === 0 ? (
        <Text size="xs" c="dimmed">
          No horizon mask — the planner treats the whole sky above your minimum
          altitude as open. Add points to mark where trees or buildings block it.
        </Text>
      ) : (
        points.map((p, i) => (
          <Group key={i} gap="xs" align="flex-end" wrap="nowrap">
            <NumberInput label={i === 0 ? "Azimuth (°)" : undefined} value={p[0]}
              min={0} max={360} step={5} clampBehavior="strict" w={130}
              rightSection={<Text size="xs" c="dimmed" pr={6}>{compassPoint(p[0])}</Text>}
              onChange={(v) => setPoint(i, 0, v === "" ? 0 : Number(v))} />
            <NumberInput label={i === 0 ? "Min altitude (°)" : undefined} value={p[1]}
              min={0} max={90} step={1} clampBehavior="strict" w={130}
              onChange={(v) => setPoint(i, 1, v === "" ? 0 : Number(v))} />
            <Button variant="subtle" color="red" size="compact-sm"
              leftSection={<IconTrash size={14} />} onClick={() => removePoint(i)}>
              Remove
            </Button>
          </Group>
        ))
      )}
      <Group gap="xs">
        <Button variant="light" size="compact-sm" leftSection={<IconPlus size={14} />}
          onClick={addPoint}>
          Add horizon point
        </Button>
        {points.length > 0 && (
          <Button variant="subtle" color="gray" size="compact-sm" onClick={() => onChange([])}>
            Clear mask
          </Button>
        )}
      </Group>
    </Stack>
  );
}

function BackupRestore() {
  const qc = useQueryClient();
  const restore = useMutation({
    mutationFn: (config: Record<string, unknown>) => api.importSettings(config),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["settings"] });
      notifications.show({ color: "teal", message: "Settings restored from backup." });
    },
    onError: (e: Error) =>
      notifications.show({ color: "red", title: "Restore failed", message: e.message }),
  });

  const onFile = (file: File | null) => {
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => {
      try {
        const parsed = JSON.parse(String(reader.result));
        if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) {
          throw new Error("not a settings object");
        }
        restore.mutate(parsed as Record<string, unknown>);
      } catch {
        notifications.show({
          color: "red", title: "Restore failed",
          message: "That file isn't a valid AstroStack settings backup.",
        });
      }
    };
    reader.readAsText(file);
  };

  return (
    <Paper withBorder p="lg">
      <Stack>
        <Text fw={600}>Backup &amp; restore</Text>
        <Text size="sm" c="dimmed">
          Download all your settings as a JSON file, or restore them from a
          previous backup. Passwords and machine-specific paths (data root,
          incoming/library folders, ASTAP path) are never included, so a backup
          is safe to share and restores cleanly on any install.
        </Text>
        <Group>
          <Button
            component="a"
            href={api.settingsExportUrl()}
            variant="default"
            leftSection={<IconDownload size={16} />}
          >
            Export settings
          </Button>
          <FileButton onChange={onFile} accept="application/json,.json">
            {(props) => (
              <Button
                {...props}
                variant="default"
                loading={restore.isPending}
                leftSection={<IconUpload size={16} />}
              >
                Import settings…
              </Button>
            )}
          </FileButton>
        </Group>
      </Stack>
    </Paper>
  );
}

// Proactive nudge text: after an in-place upgrade, tell the user how many targets'
// images are stale so they don't have to remember to reprocess. Null when nothing
// is outdated (or the status hasn't loaded), so no nudge is shown.
export function reprocessNudgeText(status: ReprocessStatus | undefined): string | null {
  if (!status || status.outdated <= 0) return null;
  const n = status.outdated;
  const subj = n === 1 ? "1 target was" : `${n} targets were`;
  return (
    `${subj} last stacked with an older AstroStack version than the one now `
    + `running (v${status.current_version}). Reprocess ${n === 1 ? "it" : "them"} `
    + `to apply the latest stacking improvements — it's non-destructive, so your `
    + `existing images aren't overwritten.`
  );
}

/**
 * Which targets a reprocess batch is about.
 *
 * One question with three answers rather than a switch per filter: they are
 * mutually exclusive descriptions of one set, and as switches the two that
 * existed could be combined into a batch nobody meant. `new-light` is the
 * owner's actual cadence (many targets, auto-stack off — after a night's
 * capture some pictures are behind the light he owns); `stale` is the one after
 * an upgrade; `all` is the big hammer. Nothing was taken away when this replaced
 * the "only outdated" switch — every scope that switch could express is still
 * one click, and there is now a third that no combination of switches could.
 */
export type ReprocessScope = "new-light" | "stale" | "all";

/**
 * How many targets a batch in this scope would restack, and how many of them
 * currently show a finished picture — or `null` for either where the backend
 * hasn't said.
 *
 * The pair is computed in one place because the dialog must never quote a
 * number bigger than the batch will touch, and each scope has its own.
 */
export function reprocessScopeCounts(
  status: ReprocessStatus | undefined,
  scope: ReprocessScope,
): { targets: number | null; finished: number | null; handFinished: number | null } {
  if (!status) return { targets: null, finished: null, handFinished: null };
  const n = (v: number | null | undefined) =>
    (v != null && Number.isFinite(v) ? v : null);
  if (scope === "new-light") {
    return {
      targets: n(status.new_light),
      finished: n(status.finished_pictures_new_light_only),
      handFinished: n(status.hand_finished_new_light_only),
    };
  }
  if (scope === "stale") {
    return {
      // `outdated` counts targets with an existing image on another version; a
      // never-stacked target is restacked by this scope too but is in neither
      // version count, so this is a floor, not the batch size. It is only used
      // to *describe* the scope, never to promise a number.
      targets: n(status.outdated),
      finished: n(status.finished_pictures_stale_only),
      handFinished: n(status.hand_finished_stale_only),
    };
  }
  return {
    targets: n(status.total_targets),
    finished: n(status.finished_pictures),
    handFinished: n(status.hand_finished),
  };
}

/**
 * What a reprocess run does to the finished pictures on the wall — or null when
 * there is nothing worth saying.
 *
 * Every restack is saved as a new result, and the picture a target shows is its
 * newest result, so an unedited restack used to quietly become the picture on
 * the Library wall, the life list, the wishlist and the sky map (issue #903: 44
 * pictures at once). The batch now keeps that from happening on its own: a
 * picture the app finished (Auto) is re-finished on the fresh result, and a
 * picture the owner finished *by hand* stays on the wall — pinned as the cover,
 * with the deeper restack waiting in History — whatever the auto-edit switch
 * says. So the sentence here is no longer a warning about a flat stack; it is
 * the promise, with the count, so nobody wonders why those cards did not change.
 *
 * `scope` picks the count that matches the scope the user chose, so the
 * sentence can never quote a number bigger than the batch will touch. Null when
 * no target in that scope shows a hand-finished picture, and on an older
 * backend that doesn't send the counts.
 */
export function reprocessPictureWarning(
  status: ReprocessStatus | undefined,
  opts: { scope: ReprocessScope; autoEdit: boolean },
): string | null {
  if (!status) return null;
  const n = reprocessScopeCounts(status, opts.scope).handFinished;
  if (n == null || n <= 0) return null;
  const subj = n === 1
    ? "1 of these targets shows a picture you finished yourself"
    : `${n} of these targets show pictures you finished yourself`;
  const it = n === 1 ? "It stays" : "They stay";
  const its = n === 1 ? "its" : "their";
  const auto = opts.autoEdit
    ? " (auto-editing the new result doesn't replace your own work)"
    : "";
  return (
    `${subj}. ${it} on the wall exactly as ${n === 1 ? "it is" : "they are"}${auto}, `
    + `and ${its} deeper restack waits in History — the target's page will offer `
    + `it as a cleaner cover when it is one. Pictures the app finished for you are `
    + `re-finished on the new result automatically.`
  );
}

// Read-only self-check on Auto's colour path: every unattended auto-edit stamps
// its finished sky-background cast, and this turns that per-run signal into one
// plain library-wide answer — of the auto-edited results, how many landed neutral
// vs carried a residual cast, and which tint dominated when they didn't. Null
// until any auto-edited run is measured, so no line is shown on a fresh install.
export function autoCastSummaryText(summary: AutoCastSummary | undefined): string | null {
  if (!summary || summary.measured <= 0) return null;
  const { measured, neutral, cast, by_cast } = summary;
  const runs = measured === 1 ? "auto-edited result" : "auto-edited results";
  if (cast <= 0) {
    return (
      `Auto's background came out neutral on all ${measured} ${runs} so far — `
      + `its colour path is landing clean on your data.`
    );
  }
  // Name the tints that actually appeared, commonest first, so the owner sees
  // which way Auto skews when it isn't neutral.
  const tints = Object.entries(by_cast)
    .sort((a, b) => b[1] - a[1])
    .map(([name, n]) => `${n} ${name}`)
    .join(", ");
  const skew = tints ? ` (${tints})` : "";
  return (
    `Auto's background came out neutral on ${neutral} of ${measured} ${runs}; `
    + `${cast} carried a slight cast${skew}. A run or two off-neutral is normal; a `
    + `consistent tint would be worth a look at the colour steps.`
  );
}

// The highlight sibling of the colour self-check above: every unattended
// auto-edit asks the editor's own "Hold back highlights" solver what it would
// offer on the picture it just made, and this turns those readings into one
// plain answer — how often Auto's stretch leaves a bright core washed out, and
// how strong the fix would be. Null until any auto-edited run is measured, so
// nothing is shown on a fresh install.
export function autoHighlightSummaryText(
  summary: AutoHighlightSummary | undefined,
): string | null {
  if (!summary || summary.measured <= 0) return null;
  const { measured, blown, median_strength: strength } = summary;
  const runs = measured === 1 ? "auto-edited result" : "auto-edited results";
  if (blown <= 0) {
    return (
      `None of the ${measured} ${runs} so far came out with a washed-out bright `
      + `core — Auto's stretch is holding your highlights.`
    );
  }
  // Name the strength that would reopen them, because that is the knob the
  // owner would actually reach for in the editor ("Hold back highlights").
  const fix = strength != null
    ? ` "Hold back highlights" at about ${Math.round(strength * 100)}% would `
      + `reopen ${blown === 1 ? "it" : "them"}.`
    : "";
  return (
    `${blown} of ${measured} ${runs} came out with a washed-out bright core.${fix}`
    + ` A bright galaxy or nebula core doing this now and then is normal.`
  );
}

/**
 * The "Bring my pictures up to date" scope in one sentence: what it would queue,
 * in the two numbers the owner has to weigh before spending a NAS's evening on
 * it. Null when the backend hasn't said (an older build), so the option can
 * describe itself without inventing a count.
 */
export function newLightScopeText(status: ReprocessStatus | undefined): string | null {
  const targets = reprocessScopeCounts(status, "new-light").targets;
  if (targets == null) return null;
  if (targets <= 0) {
    return "Nothing is waiting — every picture already includes all the light "
      + "you've shot.";
  }
  const subs = status?.new_light_subs;
  const waiting = subs != null && Number.isFinite(subs) && subs > 0
    ? ` — ${subs} ${subs === 1 ? "sub" : "subs"} of yours that aren't in a `
      + "picture yet"
    : "";
  return (
    `Re-stacks the ${targets} ${targets === 1 ? "target" : "targets"} whose `
    + `${targets === 1 ? "picture is" : "pictures are"} missing subs you already `
    + `have${waiting}. Every other target is left alone.`
  );
}

export function Maintenance() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  // Which targets the batch is about. Default "stale" — after an upgrade the
  // user wants the images that would actually change, not the whole library —
  // unless the Dashboard's "you've shot more of these" note sent them here, in
  // which case they already picked the scope on the way in and it would be rude
  // to make them pick it again.
  const [scope, setScope] = useState<ReprocessScope>(
    () => (searchParams.get("scope") === "new-light" ? "new-light" : "stale"),
  );
  // Off by default: the common case is a plain restack with the new engine. A deep
  // rescan (re-QC / re-solve / re-grade every frame first) is much slower and only
  // pays off when QC/solving/grading improved too, so make it an explicit opt-in.
  const [deepRescan, setDeepRescan] = useState(false);
  // Off by default for the two engine scopes: it seeds an editor recipe on every
  // restacked run at once, so it's an explicit opt-in there. **On** by default
  // when someone arrives on "Bring my pictures up to date": that scope exists so
  // a night's new subs end up in a *picture* with one click, and a flat linear
  // stack is not the picture a beginner came for. It is a default for this
  // visit only — nothing in Settings is written — and the switch stays in view
  // to turn off. Pictures the owner finished himself are kept either way.
  const [autoEdit, setAutoEdit] = useState(
    () => searchParams.get("scope") === "new-light",
  );
  const status = useQuery({
    queryKey: ["reprocess-status"],
    queryFn: api.reprocessStatus,
    staleTime: 60_000,
  });
  const nudge = reprocessNudgeText(status.data);
  const newLightText = newLightScopeText(status.data);
  const newLightTargets = reprocessScopeCounts(status.data, "new-light").targets;
  // Nothing to bring up to date is not an error, it is the good state — so the
  // scope stays visible and says so, and only the button that would queue an
  // empty batch stands down.
  const nothingWaiting = scope === "new-light" && newLightTargets === 0;
  // What the batch does with the finished pictures on the wall, in the scope
  // actually chosen: the hand-finished ones are kept. Self-hides when no target
  // in that scope shows one, and on a backend that doesn't send the counts.
  const pictureWarning = reprocessPictureWarning(status.data, { scope, autoEdit });
  const castSummary = useQuery({
    queryKey: ["auto-cast-summary"],
    queryFn: api.autoCastSummary,
    staleTime: 60_000,
  });
  const castText = autoCastSummaryText(castSummary.data);
  const highlightSummary = useQuery({
    queryKey: ["auto-highlight-summary"],
    queryFn: api.autoHighlightSummary,
    staleTime: 60_000,
  });
  const highlightText = autoHighlightSummaryText(highlightSummary.data);
  const reprocess = useMutation({
    mutationFn: (opts: { scope: ReprocessScope; deepRescan: boolean; autoEdit: boolean }) =>
      api.reprocessAll(opts.scope === "stale", opts.deepRescan, opts.autoEdit,
                       opts.scope === "new-light"),
    onSuccess: (res) => {
      notifications.show({
        color: "teal",
        message: res.already_running
          ? "A reprocess-everything batch is already running — watch it on the Jobs page."
          : "Reprocessing targets — watch progress on the Jobs page.",
      });
      navigate("/jobs");
    },
    onError: (e: Error) =>
      notifications.show({ color: "red", title: "Couldn't start reprocess", message: e.message }),
  });

  const onClick = () => {
    const scopeText = scope === "new-light"
      ? "Bring your pictures up to date?\n\n"
        + `(${newLightText ?? "Only the targets whose pictures are missing subs "
          + "you already have are restacked."})\n\n`
      : scope === "stale"
        ? "Restack every target that hasn't already been stacked with the current "
          + "version?\n\n(Targets already up to date on this version are skipped.)\n\n"
        : "Restack EVERY target with the current engine?\n\n";
    const rescanNote = deepRescan
      ? "Each target's frames are also re-checked (QC), re-plate-solved and "
        + "re-graded before restacking — slower, but picks up quality/solving "
        + "improvements too. Your manual accept/reject choices are kept.\n\n"
      : "";
    const editNote = (autoEdit
      ? "Each fresh result is also auto-edited (the one-click Auto look) so it "
        + "opens as a finished picture, not a flat linear stack. This only sets "
        + "the new results' edits — your existing edits are untouched, and every "
        + "auto-edit is reversible in the editor.\n\n"
      // Switch off: his own saved edit is copied onto the fresh result (saved,
      // not rendered). With it on, Auto's finish is that result's edit instead.
      : "Where you saved your own edit, it is copied onto the fresh result, so "
        + "the editor opens with your look on the deeper stack. The picture on "
        + "the wall doesn't change until you export it.\n\n")
      // What happens to the pictures already on the wall: the ones you finished
      // yourself stay, the ones the app finished are re-finished. Said in the
      // dialog too, because it is the one consequence the rest of it doesn't
      // state — every other sentence is about what is *kept* on disk.
      + (pictureWarning ? `${pictureWarning}\n\n` : "");
    if (
      window.confirm(
        scopeText
        + rescanNote
        + editNote
        + "Each target is reprocessed one at a time, reusing its last stack "
        + "settings. This is non-destructive: every restack is saved as a NEW "
        + "result alongside the existing one (nothing is deleted or overwritten), "
        + "so you can compare them in History. A large library can take a while.",
      )
    ) {
      reprocess.mutate({ scope, deepRescan, autoEdit });
    }
  };

  return (
    <Paper withBorder p="lg">
      <Stack>
        <Text fw={600}>Reprocess everything</Text>
        <Text size="sm" c="dimmed">
          Restack your targets with the current engine, reusing each target's last
          stack settings. Handy after an upgrade so all your final images benefit
          from the newest stacking improvements, and after a night's capture to
          fold your newest subs into the pictures that are missing them. Targets
          are processed one at a time; each restack is saved as a new result
          alongside the old one, so nothing is ever lost.
        </Text>
        {nudge && (
          <Alert
            color="grape"
            variant="light"
            icon={<IconRefresh size={16} />}
            title="Some images are out of date"
          >
            {nudge}
          </Alert>
        )}
        <Radio.Group
          value={scope}
          onChange={(v) => setScope(v as ReprocessScope)}
          label="Which targets?"
          data-testid="reprocess-scope"
        >
          <Stack gap="xs" mt="xs">
            <Radio
              value="new-light"
              label="Only targets whose picture is missing subs you have"
              description={newLightText
                ?? "Restacks just the targets you've shot more of since their "
                   + "pictures were made."}
            />
            <Radio
              value="stale"
              label="Only targets not already stacked on this version"
              description="Skips targets whose latest stack was already made with the current version, so a large library isn't reprocessed wholesale."
            />
            <Radio
              value="all"
              label="Every target"
              description="Restacks your whole library with the current engine, whether or not anything about it has changed."
            />
          </Stack>
        </Radio.Group>
        <Switch
          checked={deepRescan}
          onChange={(e) => setDeepRescan(e.currentTarget.checked)}
          label="Also re-run QC, plate-solving & grading first"
          description="Re-checks every frame (quality, plate-solve, auto-grade) before restacking, so improvements to those steps apply too — not just the stacker. Slower, and keeps your manual accept/reject choices."
        />
        <Switch
          checked={autoEdit}
          onChange={(e) => setAutoEdit(e.currentTarget.checked)}
          label="Also auto-edit each result into a finished picture"
          description="Applies the one-click Auto look to every restacked result so it opens as a finished picture instead of a flat linear stack. Only sets the new results' edits; your existing edits are untouched and every auto-edit is reversible. Either way, a picture you finished yourself stays on the wall and its deeper restack waits in History."
        />
        {pictureWarning && (
          <Text size="xs" c="dimmed" mt={-8}>
            {pictureWarning}
          </Text>
        )}
        <Group>
          <Button
            color="grape"
            variant="light"
            leftSection={<IconRefresh size={16} />}
            loading={reprocess.isPending}
            disabled={nothingWaiting}
            onClick={onClick}
          >
            {scope === "new-light"
              ? "Bring my pictures up to date…"
              : scope === "stale"
                ? "Reprocess outdated targets…"
                : "Reprocess all targets…"}
          </Button>
        </Group>
        {castText && (
          <Text size="xs" c="dimmed" mt={4}>
            {castText}
          </Text>
        )}
        {highlightText && (
          <Text size="xs" c="dimmed">
            {highlightText}
          </Text>
        )}
      </Stack>
    </Paper>
  );
}


function AccessControl() {
  const qc = useQueryClient();
  const status = useQuery({ queryKey: ["auth-status"], queryFn: api.authStatus });
  const [username, setUsername] = useState("admin");
  const [password, setPassword] = useState("");

  useEffect(() => {
    if (status.data?.username) setUsername(status.data.username);
  }, [status.data?.username]);

  const enabled = status.data?.enabled ?? false;

  const setPw = useMutation({
    mutationFn: () => api.setAuthPassword({ password, username }),
    onSuccess: (r) => {
      notifications.show({
        message: r.enabled
          ? "Password set — you'll be asked to sign in on the next request."
          : "Access control disabled.",
        color: "teal",
      });
      setPassword("");
      qc.invalidateQueries({ queryKey: ["auth-status"] });
    },
    onError: (e: Error) => notifications.show({ message: e.message, color: "red" }),
  });

  const disable = useMutation({
    mutationFn: () => api.setAuthPassword({ password: "" }),
    onSuccess: () => {
      notifications.show({ message: "Access control disabled.", color: "teal" });
      qc.invalidateQueries({ queryKey: ["auth-status"] });
    },
    onError: (e: Error) => notifications.show({ message: e.message, color: "red" }),
  });

  // The read-only token. Held in component state only: the server keeps a hash,
  // so this is the one and only moment it is readable, and a refetch can never
  // bring it back. Cleared whenever the token is replaced or removed, so a stale
  // secret is never left on screen next to a badge saying something else.
  const [mintedToken, setMintedToken] = useState<string | null>(null);
  const roEnabled = status.data?.readonly_enabled ?? false;
  const roUsername = status.data?.readonly_username ?? "readonly";

  const mintToken = useMutation({
    mutationFn: () => api.mintReadonlyToken(),
    onSuccess: (r) => {
      setMintedToken(r.token);
      qc.invalidateQueries({ queryKey: ["auth-status"] });
    },
    onError: (e: Error) => notifications.show({ message: e.message, color: "red" }),
  });

  const removeToken = useMutation({
    mutationFn: () => api.clearReadonlyToken(),
    onSuccess: () => {
      setMintedToken(null);
      notifications.show({ message: "Read-only token removed.", color: "teal" });
      qc.invalidateQueries({ queryKey: ["auth-status"] });
    },
    onError: (e: Error) => notifications.show({ message: e.message, color: "red" }),
  });

  return (
    <Paper withBorder p="lg">
      <Stack>
        <Group gap={6}>
          <Text fw={600}>Access control</Text>
          <Badge variant="light" color={enabled ? "teal" : "gray"}>
            {enabled ? "password protected" : "open"}
          </Badge>
        </Group>
        <Text size="sm" c="dimmed">
          Optionally require a username and password (HTTP Basic) to reach AstroStack.
          Leave it off on a trusted LAN; turn it on if the app is exposed beyond your
          network. Best paired with HTTPS so credentials aren't sent in the clear.
        </Text>
        <Group align="flex-end" gap="sm" wrap="wrap">
          <TextInput label="Username" value={username} w={160}
            onChange={(e) => setUsername(e.currentTarget.value)} />
          <TextInput label={enabled ? "New password" : "Password"} type="password"
            placeholder="At least 4 characters" value={password} style={{ flex: 1, minWidth: 180 }}
            onChange={(e) => setPassword(e.currentTarget.value)} />
          <Button onClick={() => setPw.mutate()} loading={setPw.isPending}
            disabled={password.length < 4}>
            {enabled ? "Update" : "Enable"}
          </Button>
          {enabled ? (
            <Button color="red" variant="light" loading={disable.isPending}
              onClick={() => {
                if (window.confirm("Disable access control? The app will be open to anyone who can reach it, and the read-only token is removed too (anything signing in with it, such as a monitoring helper, stops working; create a new one after turning the password back on).")) {
                  disable.mutate();
                }
              }}>
              Disable
            </Button>
          ) : null}
        </Group>

        <Divider />

        <Group gap={6}>
          <Text fw={600} size="sm">Read-only token</Text>
          <Badge variant="light" color={roEnabled ? "teal" : "gray"}>
            {roEnabled ? "active" : "none"}
          </Badge>
        </Group>
        <Text size="sm" c="dimmed">{readonlyTokenBlurb()}</Text>
        {enabled ? (
          <>
            <Group align="center" gap="sm" wrap="wrap">
              <Button variant="light" loading={mintToken.isPending}
                onClick={() => {
                  if (roEnabled && !window.confirm(
                    "Replace the read-only token? The current one stops working straight away.",
                  )) return;
                  setMintedToken(null);
                  mintToken.mutate();
                }}>
                {roEnabled ? "Replace the token" : "Create a token"}
              </Button>
              {roEnabled ? (
                <Button color="red" variant="subtle" loading={removeToken.isPending}
                  onClick={() => removeToken.mutate()}>
                  Remove
                </Button>
              ) : null}
              {roEnabled && !mintedToken ? (
                <Text size="xs" c="dimmed">
                  Sign in as <Text span fw={500} c="inherit">{roUsername}</Text> with the
                  token you saved. Lost it? Replace it — the token itself is never stored,
                  only a check of it.
                </Text>
              ) : null}
            </Group>
            {mintedToken ? (
              <Alert color="teal" variant="light" icon={<IconInfoCircle size={16} />}
                title="Copy this now — it isn't shown again">
                <Stack gap={6}>
                  <Group gap="xs" wrap="nowrap" align="center">
                    <Code style={{ flex: 1, wordBreak: "break-all" }}>{mintedToken}</Code>
                    <CopyButton value={mintedToken}>
                      {({ copied, copy }) => (
                        <Button size="xs" variant={copied ? "filled" : "light"}
                          color={copied ? "teal" : "gray"} onClick={copy}>
                          {copied ? "Copied" : "Copy"}
                        </Button>
                      )}
                    </CopyButton>
                  </Group>
                  <Text size="xs">
                    Use it as the password, with the username{" "}
                    <Text span fw={500}>{roUsername}</Text>. To check it works:
                  </Text>
                  <Code block>{readonlyCurlExample(roUsername, window.location.origin)}</Code>
                </Stack>
              </Alert>
            ) : null}
          </>
        ) : (
          <Text size="xs" c="dimmed">
            Turn on the password above first. With no password set the app is already
            open to anyone on your network, so a read-only token wouldn't add anything.
          </Text>
        )}
      </Stack>
    </Paper>
  );
}

export function SettingsView() {
  const qc = useQueryClient();
  // Which section the URL asks for (`/settings/<section>`); undefined on a bare
  // `/settings`, which lands on the first one.
  const { section } = useParams<{ section?: string }>();
  const settings = useQuery({ queryKey: ["settings"], queryFn: api.getSettings });
  const system = useQuery({ queryKey: ["system"], queryFn: api.getSystem });
  const stackSchema = useQuery({ queryKey: ["schema"], queryFn: api.optionsSchema });
  const [form, setForm] = useState<Record<string, unknown>>({});
  // The full stacking-defaults list sits folded under the picture cards
  // (slice 5): one click away, as the spec asks, not removed.
  const [showAllStack, setShowAllStack] = useState(false);

  useEffect(() => {
    if (settings.data) setForm(settings.data);
  }, [settings.data]);

  const astapTest = useMutation({ mutationFn: () => api.astapTest() });

  const save = useMutation({
    mutationFn: (patch: Record<string, unknown>) => api.putSettings(dropEmptyFields(patch)),
    onSuccess: () => {
      notifications.show({ message: "Settings saved", color: "teal" });
      qc.invalidateQueries({ queryKey: ["settings"] });
      qc.invalidateQueries({ queryKey: ["system"] });
      qc.invalidateQueries({ queryKey: PLAN_SITE_QUERY_KEY });
    },
    onError: (e: Error) => notifications.show({
      // The guards on this page already write a plain-language reason; the API
      // client's `422: ` prefix in front of one is just a status code in the
      // user's face. Dropped only when the detail really is a sentence.
      message: `Save failed: ${settingsErrorMessage(e.message)}`, color: "red",
    }),
  });

  // The one folder layout the app must never be pointed at, answered while you
  // type instead of as a red toast after Save. Advisory: the server guard
  // (`nested_incoming_conflict`) stays the authority, and anything a browser
  // can't judge — a relative path, a symlink, a case-insensitive mount — falls
  // through to the save rather than blocking it.
  const conflict = folderConflict(
    (form.incoming_dir as string) ?? "",
    (form.library_root as string) ?? "",
    (form.data_root as string) ?? "",
  );

  if (settings.isError) {
    return <Alert color="red" m="md" title="Could not load settings">{(settings.error as Error)?.message}</Alert>;
  }
  if (settings.isLoading || !settings.data) {
    return <Center h={300}><Loader /></Center>;
  }

  const set = (k: string, v: unknown) => setForm((p) => ({ ...p, [k]: v }));
  const bool = (k: string) => Boolean(form[k]);
  const walkAway = walkAwayEnabled(form);
  const setWalkAway = (on: boolean) => setForm((p) => withWalkAway(p, on));
  const num = (k: string) => (form[k] === null || form[k] === undefined ? "" : (form[k] as number));
  // `data-setting` is how "nothing was removed" stays checkable: `HINTS` is the
  // page's own register of every labelled setting, and this stamps the key of
  // each one onto the DOM, so a redesign slice that rehomes a control is fine
  // and one that drops it fails a test (see "Settings — nothing was removed").
  const lbl = (k: string, label: string) => (
    <span data-setting={k}><HintLabel label={label} hint={HINTS[k]} /></span>
  );

  // Auto-stack defaults (global). Per-target "Save as defaults" overrides these.
  const stackOpts = (form.default_stack_options as Record<string, unknown>) ?? {};
  const setStackOpt = (k: string, v: unknown) =>
    set("default_stack_options", { ...stackOpts, [k]: v });
  const fields = stackSchema.data ?? [];
  const simple = fields.filter((f) => f.group === "simple");
  const advanced = fields.filter((f) => f.group === "advanced");
  const optVal = (k: string) => (k in stackOpts ? stackOpts[k] : fields.find((f) => f.key === k)?.default);

  // The defaults grid is descriptor-driven and has no cross-field logic, so the
  // one pairing that cancels itself out — min/max rejection with quality
  // weighting — would go unmentioned on the very screen a walk-away user sets it
  // from. Same shared wording as the per-target Stack form, worded conditionally
  // here because these defaults apply to whatever a future run brings (no frame
  // count to gate on). Advisory only; it never blocks the save.
  const stackDefaultsWeightingHint = stackSchema.isLoading ? null : minMaxIgnoresWeightingHint({
    minMaxReject: Boolean(optVal("min_max_reject")),
    qualityWeighted: Boolean(optVal("quality_weighted")),
    drizzle: Boolean(optVal("drizzle")),
    frames: null,
  });

  // Every section that edits server settings ends with the same button, and each
  // one saves the *whole* form — the sections share one edit buffer and stay
  // mounted, so an edit made in one section is never lost by saving from another.
  const saveRow = (variant?: string) => (
    <Group justify="flex-end">
      <Button variant={variant} leftSection={<IconDeviceFloppy size={16} />}
        onClick={() => save.mutate(form)} loading={save.isPending}
        disabled={conflict !== null}>
        Save settings
      </Button>
    </Group>
  );

  // What each section holds. The order and the labels live in
  // `SETTINGS_PAGE_SECTIONS` above; keys are typed against
  // `settingsSections.ts`, which is also what the app's "Fix in Settings" links
  // point at, so a renamed section can't quietly strand one of them.
  const nodes: Record<SettingsSection, ReactNode> = {
    folders: (
      <Paper withBorder p="lg">
        <Stack>
          <Text fw={600}>Watched folders</Text>
          <TextInput label={lbl("data_root", "Data root")} value={(form.data_root as string) ?? ""}
            error={conflict?.field === "data_root" ? conflict.message : undefined}
            onChange={(e) => set("data_root", e.currentTarget.value)} />
          <SimpleGrid cols={{ base: 1, xs: 2 }}>
            <TextInput label={lbl("incoming_dir", "Incoming dir")}
              value={(form.incoming_dir as string) ?? ""}
              placeholder={settings.data.resolved_incoming_dir}
              onChange={(e) => set("incoming_dir", e.currentTarget.value)} />
            <TextInput label={lbl("library_root", "Library root")}
              value={(form.library_root as string) ?? ""}
              placeholder={settings.data.resolved_library_root}
              error={conflict?.field === "library_root" ? conflict.message : undefined}
              onChange={(e) => set("library_root", e.currentTarget.value)} />
          </SimpleGrid>

          <Divider label="Watcher" />
          <Switch label={lbl("watcher_enabled", "Watch for new files automatically")}
            checked={bool("watcher_enabled")}
            onChange={(e) => set("watcher_enabled", e.currentTarget.checked)} />
          <SimpleGrid cols={{ base: 1, xs: 2 }}>
            <NumberInput label={lbl("watch_quiet_period_s", "Quiet period (s)")}
              value={num("watch_quiet_period_s")} min={5}
              onChange={(v) => set("watch_quiet_period_s", v === "" ? "" : Number(v))} />
            <NumberInput label={lbl("watch_poll_interval_s", "Poll interval (s)")}
              value={num("watch_poll_interval_s")} min={2}
              onChange={(v) => set("watch_poll_interval_s", v === "" ? "" : Number(v))} />
          </SimpleGrid>
          {saveRow()}
        </Stack>
      </Paper>
    ),
    automation: (
      <Paper withBorder p="lg">
        <Stack>
          {/* Sections 1–2 of the approved redesign: the three "how hands-off?"
              cards over the six steps a new sub goes through. They replace the
              row of bare switches (Ingest / QC / Plate-solve / Auto-stack), the
              auto-edit switch and the two stack-trigger boxes that used to open
              this tab — same fields, same edit buffer, each still stamped
              `data-setting` for the "nothing was removed" guard. */}
          <HandsOffSection form={form} saved={settings.data} labelFor={lbl}
            onPatch={(patch) => setForm((p) => ({ ...p, ...patch }))} />

          {/* Section 3: "How picky?" — replaces the auto-grade switch, its
              Sensitivity select and the trails switch that sat at the foot of
              this tab. */}
          <Divider />
          <FramePickySection form={form} labelFor={lbl}
            onPatch={(patch) => setForm((p) => ({ ...p, ...patch }))} />

          <Divider label="More for hands-off nights" />
          <Switch
            size="md"
            checked={walkAway}
            onChange={(e) => setWalkAway(e.currentTarget.checked)}
            label={<Text fw={600}>Walk-away mode</Text>}
            description={
              "Recommended for a hands-off night. Turns on the whole unattended "
              + "pipeline at once — stack each target automatically, use your saved "
              + "calibration masters, drop obviously-bad subs, skip a batch that "
              + "looks like two different targets, and finish the picture for you — "
              + "so you can drop your subs in and come back to a calibrated, edited "
              + "image. You can still fine-tune any of the individual switches on this tab "
              + "and under Stacking → How pictures are made."
            }
          />
          {/* Outlier removal, drizzle, the border trim and calibration moved
              to Stacking's "How pictures are made" cards (slice 5). */}
          <Text size="sm" c="dimmed">
            How each hands-off picture is stacked and finished — removing
            satellites, drizzle, trimming a mosaic's edge, darks and flats — is
            under{" "}
            <Anchor component={Link} to={settingsLink("stacking")}>Stacking → How pictures are made</Anchor>.
          </Text>
          <Switch label={lbl("copy_to_cache", "Copy frames into local cache")}
            checked={bool("copy_to_cache")}
            onChange={(e) => set("copy_to_cache", e.currentTarget.checked)} />
          {saveRow()}
        </Stack>
      </Paper>
    ),
    "plate-solving": (
      <Paper withBorder p="lg">
        <Stack>
          <Text fw={600}>Plate solving &amp; compute</Text>
          <Text size="sm" c="dimmed">
            Plate solving (ASTAP) is how AstroStack works out which patch of sky
            each sub shows, so it can line them all up. It needs the ASTAP
            program and a star database; the panel at the top of this page says
            whether both were found.
          </Text>
          <TextInput label={lbl("astap_path", "ASTAP path")}
            value={(form.astap_path as string) ?? ""}
            placeholder="auto-detect"
            onChange={(e) => set("astap_path", e.currentTarget.value || null)} />
          <SimpleGrid cols={{ base: 1, xs: 2 }}>
            <NumberInput label={lbl("astap_fov_deg", "ASTAP FOV (deg)")} value={num("astap_fov_deg")}
              step={0.1} min={0.1} onChange={(v) => set("astap_fov_deg", v === "" ? "" : Number(v))} />
            <NumberInput label={lbl("astap_timeout_s", "ASTAP timeout (s)")} value={num("astap_timeout_s")}
              min={5} onChange={(v) => set("astap_timeout_s", v === "" ? "" : Number(v))} />
          </SimpleGrid>
          <Switch label={lbl("astap_use_solve_hints", "Use telescope target as solve hint")}
            checked={bool("astap_use_solve_hints")}
            onChange={(e) => set("astap_use_solve_hints", e.currentTarget.checked)} />
          <Switch label={lbl("astap_bootstrap_solve", "Rescue faint fields with a deep-image solve")}
            checked={bool("astap_bootstrap_solve")}
            onChange={(e) => set("astap_bootstrap_solve", e.currentTarget.checked)} />
          {saveRow()}
        </Stack>
      </Paper>
    ),
    "observing-site": (
      <Paper withBorder p="lg">
        <Stack>
          {/* Section 4 of the approved redesign: read it from my photos or
              type it in, and the lowest altitude as a slider over a horizon
              drawing. Replaces the bare latitude / longitude / elevation /
              minimum-altitude boxes — same fields, same edit buffer. */}
          <ObservingSiteSection form={form} labelFor={lbl}
            onPatch={(patch) => setForm((p) => ({ ...p, ...patch }))} />

          <Divider />
          <div data-setting="horizon_profile">
            <HintLabel label="Your skyline" hint={HINTS.horizon_profile} />
            <Text size="xs" c="dimmed" mb="xs">
              Draw where trees or buildings block your low sky, and the planner
              will only count a target while it's actually clear of them. Leave it
              flat if nothing is in the way.
            </Text>
            <SkylineEditor
              value={(form.horizon_profile as HorizonPoint[]) ?? []}
              onChange={(v) => set("horizon_profile", v)} />
            <Accordion variant="separated" mt="sm">
              <Accordion.Item value="horizon-points">
                <Accordion.Control>Fine-tune exact points</Accordion.Control>
                <Accordion.Panel>
                  <Text size="xs" c="dimmed" mb="xs">
                    The same skyline as numbers, if you'd rather type bearings.
                    Azimuth is a compass bearing (0°=N, 90°=E, 180°=S, 270°=W) and
                    the altitude is the lowest clear sky at that bearing.
                  </Text>
                  <HorizonProfileEditor
                    value={(form.horizon_profile as HorizonPoint[]) ?? []}
                    onChange={(v) => set("horizon_profile", v)} />
                </Accordion.Panel>
              </Accordion.Item>
            </Accordion>
          </div>
          {saveRow()}
        </Stack>
      </Paper>
    ),
    stacking: (
      <Stack>
        {/* Section 5 of the approved redesign: the four picture cards. They
            replace the four bare switches that sat at the foot of Automation. */}
        <Paper withBorder p="lg">
          <Stack>
            <PicturesSection form={form} labelFor={lbl}
              onPatch={(patch) => setForm((p) => ({ ...p, ...patch }))} />
            {saveRow()}
          </Stack>
        </Paper>
        <Paper withBorder p="lg">
          <Stack>
            <Group gap={6}>
              <Text fw={600}>Automated stacking defaults</Text>
              <Badge variant="light" color={bool("auto_stack") ? "teal" : "gray"}>
                {bool("auto_stack") ? "active" : "auto-stack off"}
              </Badge>
            </Group>
            <Text size="sm" c="dimmed">
              Options used when <b>Auto-stack</b> stacks a target automatically. A target's own
              “Save as defaults” (from its Stack page) takes precedence over these.
            </Text>
            <Button variant="default" size="sm" mih={44} style={{ alignSelf: "flex-start" }}
              aria-expanded={showAllStack} aria-controls="all-stacking-options"
              onClick={() => setShowAllStack((v) => !v)}>
              {showAllStack ? "Hide stacking options"
                : fields.length ? `Show all ${fields.length} stacking options` : "Show all stacking options"}
            </Button>
            <Collapse in={showAllStack} id="all-stacking-options">
            {stackSchema.isLoading ? <Loader size="sm" /> : (
              <Stack>
                {simple.map((f) => (
                  <StackOptionControl
                    key={f.key} field={f} value={optVal(f.key)}
                    disabled={!dependencyMet(f.depends_on, optVal)}
                    onChange={(v) => setStackOpt(f.key, v)}
                  />
                ))}
                <Accordion variant="separated" mt="xs">
                  <Accordion.Item value="adv">
                    <Accordion.Control>Advanced options</Accordion.Control>
                    <Accordion.Panel>
                      <Stack>
                        {advanced.map((f) => (
                          <StackOptionControl
                            key={f.key} field={f} value={optVal(f.key)}
                            disabled={!dependencyMet(f.depends_on, optVal)}
                            onChange={(v) => setStackOpt(f.key, v)}
                          />
                        ))}
                      </Stack>
                    </Accordion.Panel>
                  </Accordion.Item>
                </Accordion>
              </Stack>
            )}
            </Collapse>
            {stackDefaultsWeightingHint ? (
              <Alert color="yellow" variant="light" py={6} px="sm">
                <Text size="xs">{stackDefaultsWeightingHint}</Text>
                <Button size="compact-xs" variant="light" mt={6}
                  onClick={() => setStackOpt("quality_weighted", false)}>
                  Turn off quality weighting
                </Button>
              </Alert>
            ) : null}
            {saveRow("default")}
          </Stack>
        </Paper>

        {/* Section 6 of the approved redesign: memory as a bar, the memory
            limit and cores cards, and an exact-figure box. Replaces the
            "Memory" card that stood here, keeping both of its advisories. */}
        <Paper withBorder p="lg">
          <Stack>
            <NasSection form={form} labelFor={lbl} memory={system.data?.memory}
              ctx={{ cpuCount: system.data?.cpu_count ?? null }}
              onPatch={(patch) => setForm((p) => ({ ...p, ...patch }))} />
            {saveRow()}
          </Stack>
        </Paper>
      </Stack>
    ),
    telescope: (
      <Stack>
        <Paper withBorder p="lg">
          <Stack>
            <Group gap={6}>
              <IconTelescope size={18} />
              <Text fw={600}>Telescope (Seestar)</Text>
              <Badge variant="light" color={bool("seestar_enabled") ? "teal" : "gray"}>
                {bool("seestar_enabled") ? "on" : "off"}
              </Badge>
            </Group>
            <Text size="sm" c="dimmed">
              Monitor Seestar scopes over the LAN (battery, temperature, stacking progress) and
              optionally control them. This uses an unofficial, firmware-dependent API — see the
              Telescope page for caveats.
            </Text>
            <Group>
              <Switch label={lbl("seestar_enabled", "Enable Seestar integration")}
                checked={bool("seestar_enabled")}
                onChange={(e) => set("seestar_enabled", e.currentTarget.checked)} />
              <Switch label={lbl("seestar_control_enabled", "Allow control commands")}
                checked={bool("seestar_control_enabled")} disabled={!bool("seestar_enabled")}
                onChange={(e) => set("seestar_control_enabled", e.currentTarget.checked)} />
            </Group>
            <TextInput label={lbl("seestar_scan_subnet", "Scan subnet (CIDR)")}
              value={(form.seestar_scan_subnet as string) ?? ""} placeholder="auto-detect"
              onChange={(e) => set("seestar_scan_subnet", e.currentTarget.value)} />
            <TagsInput label={lbl("seestar_known_ips", "Known device IPs")}
              placeholder="e.g. 192.168.1.50"
              value={(form.seestar_known_ips as string[]) ?? []}
              onChange={(v) => set("seestar_known_ips", v)} />
            <SimpleGrid cols={{ base: 1, xs: 2 }}>
              <NumberInput label={lbl("seestar_scan_interval_s", "Scan interval (s)")}
                value={num("seestar_scan_interval_s")} min={30}
                onChange={(v) => set("seestar_scan_interval_s", v === "" ? "" : Number(v))} />
              <NumberInput label={lbl("seestar_poll_interval_s", "Poll interval (s)")}
                value={num("seestar_poll_interval_s")} min={2}
                onChange={(v) => set("seestar_poll_interval_s", v === "" ? "" : Number(v))} />
            </SimpleGrid>
            {saveRow()}
          </Stack>
        </Paper>

        <AmbientSettings />
        <NightSkySettings />
      </Stack>
    ),
    maintenance: (
      <Stack>
        {/* Section 7 of the approved redesign: the upkeep cards, unchanged,
            under one heading that says what they are for. */}
        <Stack gap={4}>
          <Title order={3}>Updates &amp; upkeep</Title>
          <Text size="sm" c="dimmed">
            Keeping AstroStack itself up to date, re-making pictures after an
            improvement, and how much of its own history it keeps. Nothing here
            touches your raw subs.
          </Text>
        </Stack>
        <UpdatesCard />
        <Maintenance />
        <RefinishPicturesCard />
        <Paper withBorder p="lg">
          <Stack>
            <Text fw={600}>Job history</Text>
            <NumberInput label={lbl("job_history_limit", "Job history to keep")}
              value={num("job_history_limit")} min={10} max={100000} step={50}
              allowDecimal={false} w={{ base: "100%", xs: 260 }}
              onChange={(v) => set("job_history_limit", v === "" ? 200 : Number(v))} />
            {saveRow()}
          </Stack>
        </Paper>
        <BackupRestore />
        <AccessControl />
      </Stack>
    ),
    // Slice 1 of the approved Settings redesign. Additive on purpose: every
    // control it holds also still sits on the section above that has always
    // held it, and both edit this one `form`, so the two can never disagree
    // and nothing has been taken away while the later slices rebuild the rest.
    more: (
      <MoreSettingsSection
        form={form}
        onPatch={(p) => setForm((prev) => ({ ...prev, ...p }))}
        ctx={{ cpuCount: system.data?.cpu_count ?? null }}
        conflict={conflict}
        resolvedIncoming={settings.data.resolved_incoming_dir}
        resolvedLibrary={settings.data.resolved_library_root}
        saveRow={saveRow()}
      />
    ),
  };

  const sections: PageSection[] = SETTINGS_PAGE_SECTIONS.map(
    (s) => ({ ...s, node: nodes[s.key] }),
  );

  return (
    <Stack maw={680}>
      <Title order={2}>Settings</Title>

      {system.data ? (() => {
        const astap = system.data.astap;
        const cannotRun = astap.found && astap.runs === false;
        const solveReady = astap.found && astap.star_db_found !== false && !cannotRun;
        return (
          <Alert icon={<IconInfoCircle size={16} />} color={solveReady ? "teal" : "yellow"}>
            <Stack gap={6}>
              <Group gap="lg">
                <Text size="sm">Data root: <b>{system.data.data_root}</b></Text>
                <Text size="sm">CPUs: <b>{system.data.cpu_count}</b></Text>
                <Badge color={astap.found && !cannotRun ? "teal" : "red"}>
                  ASTAP {cannotRun ? "can't start" : astap.found ? "found" : "missing"}
                </Badge>
                {astap.found ? (
                  <Badge color={astap.star_db_found ? "teal" : "red"}>
                    star DB {astap.star_db_found ? `${astap.star_db_count} files` : "missing"}
                  </Badge>
                ) : null}
                {system.data.gpu_available ? <Badge color="violet">GPU</Badge> : null}
                {system.data.disk.free_bytes != null ? (
                  <Text size="sm">
                    Free: <b>{formatDiskSize(system.data.disk.free_bytes)}</b>
                  </Text>
                ) : system.data.disk.free_gb ? (
                  <Text size="sm">Free: <b>{system.data.disk.free_gb} GB</b></Text>
                ) : null}
              </Group>
              {astap.version ? <Text size="xs" c="dimmed">{astap.version}</Text> : null}
              {astap.hint ? <Text size="sm" c="yellow">{astap.hint}</Text> : null}
              {cannotRun && astap.error ? <Text size="xs" c="dimmed">{astap.error}</Text> : null}
              <Group gap="xs" align="center">
                <Button size="xs" variant="light" loading={astapTest.isPending}
                  disabled={!astap.found} onClick={() => astapTest.mutate()}>
                  Test solve on a real frame
                </Button>
                {astapTest.data ? (
                  <Text size="xs" c={astapTest.data.ok ? "teal" : "red"}>
                    {astapTest.data.ok
                      ? `Solved ${astapTest.data.frame} in ${astapTest.data.elapsed_s}s`
                      : `Failed: ${astapTest.data.detail}`}
                  </Text>
                ) : null}
              </Group>
            </Stack>
          </Alert>
        );
      })() : null}

      <SectionTabs basePath="/settings" active={section} sections={sections}
        data-testid="settings-sections" />
    </Stack>
  );
}
