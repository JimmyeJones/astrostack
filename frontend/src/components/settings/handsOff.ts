/**
 * "How hands-off should AstroStack be?" and "When new photos land in your drop
 * folder" — slice 2 of the owner-approved Settings redesign
 * (`docs/design/settings-redesign.md`, sections 1–2).
 *
 * Three cards that set the six automatic steps for you, and the six steps
 * themselves as a numbered row, one switch each. This module is the data and
 * the arithmetic — which card the current switches add up to, what picking one
 * writes, and whether each step really runs on its own — kept free of React so
 * every answer can be pinned as a value. `HandsOff.tsx` draws it.
 *
 * **Every status this row shows was checked against the pipeline it describes**
 * (`webapp/pipeline.py::_pipeline_body`, `webapp/watcher.py`), and one of the
 * spec's sentences did not survive it. The mockup chains the six steps in a
 * line — *"Switch off a step and everything after it waits for you"* — but the
 * pipeline does not: with **Check** (`auto_qc`) off, placing and stacking still
 * run, because plate-solving is called with `run_qc=False, run_solve=True` and
 * auto-stack is its own pass that is "not gated on QC/solve being on". So each
 * step names the step it really needs (`needs` below), and the row says *"the
 * steps that need it"*, not *"everything after it"*. The others are true
 * chains: nothing runs on its own with **Notice** off (the watcher is what
 * starts a scan); a sub that was never **Sorted** into the library is not
 * there for the later steps to see; auto-stack only takes subs that have been
 * **Placed**; and **Finish** only ever runs on a picture auto-stack just made.
 */

export type SettingsForm = Record<string, unknown>;
export type SettingsPatch = Record<string, unknown>;

/** The six `Settings` fields the row drives, in the order a new sub meets them. */
export const PIPELINE_FIELDS = [
  "watcher_enabled",
  "auto_ingest",
  "auto_qc",
  "auto_solve",
  "auto_stack",
  "auto_edit_on_autostack",
] as const;

export type PipelineField = (typeof PIPELINE_FIELDS)[number];

export interface PipelineStep {
  field: PipelineField;
  /** One plain word, the step's name in the row. */
  title: string;
  /** What it does, in one sentence. `quiet` is the stored wait, as words. */
  desc: (quiet: string) => string;
  /** The label this switch had before the redesign. */
  was: string;
  /** The step this one can't run without, or null for the first. */
  needs: PipelineField | null;
}

export const PIPELINE_STEPS: PipelineStep[] = [
  {
    field: "watcher_enabled",
    title: "Notice",
    desc: (quiet) =>
      `Spots new files in your drop folder, then waits ${quiet} after copying stops so it never reads half a file.`,
    was: "Watch for new files automatically",
    needs: null,
  },
  {
    field: "auto_ingest",
    title: "Sort",
    desc: () => "Files each sub under the right target.",
    was: "Ingest",
    needs: "watcher_enabled",
  },
  {
    field: "auto_qc",
    title: "Check",
    desc: () =>
      "Measures stars, sharpness and sky brightness on every frame, so bad ones can be left out.",
    was: "QC",
    needs: "auto_ingest",
  },
  {
    // Not `auto_qc`: the pipeline places frames whether or not they were
    // checked (see the module comment), so switching Check off leaves this
    // step running and the row must not draw it as waiting.
    field: "auto_solve",
    title: "Place",
    desc: () => "Works out exactly where in the sky each frame points, so they can be lined up.",
    was: "Plate-solve",
    needs: "auto_ingest",
  },
  {
    field: "auto_stack",
    title: "Stack",
    desc: () => "Combines the placed frames into one deep, clean image.",
    was: "Auto-stack",
    needs: "auto_solve",
  },
  {
    field: "auto_edit_on_autostack",
    title: "Finish",
    desc: () => "Applies Auto, so you come back to a picture — not a dark, flat stack.",
    was: "Auto-edit the auto-stacked master into a finished picture",
    needs: "auto_stack",
  },
];

/**
 * Where one step stands with the switches as they are now.
 *
 * - `auto` — on, and everything it needs is running too: it happens by itself.
 * - `waiting` — on, but a step it needs is off, so it only runs once you do
 *   that step yourself (press **Scan incoming**, or upload from the browser).
 * - `manual` — off: you do this step yourself.
 */
export type StepState = "auto" | "waiting" | "manual";

export function stepState(form: SettingsForm, field: PipelineField): StepState {
  if (!form[field]) return "manual";
  const step = PIPELINE_STEPS.find((s) => s.field === field);
  if (!step || step.needs === null) return "auto";
  return stepState(form, step.needs) === "auto" ? "auto" : "waiting";
}

export function stepStatusText(state: StepState): string {
  if (state === "auto") return "Runs automatically";
  if (state === "waiting") return "Waiting for an earlier step";
  return "You do this yourself";
}

/** The three ready-made answers to "how hands-off?". */
export type HandsOffPresetId = "all" | "ready" | "manual";

export interface HandsOffPreset {
  id: HandsOffPresetId;
  title: string;
  desc: string;
  /** A short word on the card, so the three are told apart at a glance. */
  tag: string;
  /** What picking it writes — all six fields, every time. */
  values: Record<PipelineField, boolean>;
}

function pipelineValues(onThrough: number): Record<PipelineField, boolean> {
  const out = {} as Record<PipelineField, boolean>;
  PIPELINE_FIELDS.forEach((f, i) => (out[f] = i < onThrough));
  return out;
}

export const HANDS_OFF_PRESETS: HandsOffPreset[] = [
  {
    id: "all",
    title: "Do it all for me",
    desc: "New subs are sorted, checked, stacked and finished into a picture while you sleep.",
    tag: "Fully hands-off",
    values: pipelineValues(6),
  },
  {
    id: "ready",
    title: "Get them ready — I’ll stack",
    desc: "Subs are sorted, checked and placed in the sky. You press Stack when you’re happy.",
    tag: "You press Stack",
    values: pipelineValues(4),
  },
  {
    id: "manual",
    title: "Hands on",
    desc: "Nothing happens until you ask. Good for experimenting.",
    tag: "Most control",
    values: pipelineValues(0),
  },
];

/**
 * Which card the six switches add up to, or null for a hand-made mix
 * ("Custom" — no card is drawn as picked, and nothing is changed for you).
 */
export function handsOffPreset(form: SettingsForm): HandsOffPresetId | null {
  const hit = HANDS_OFF_PRESETS.find((p) =>
    PIPELINE_FIELDS.every((f) => Boolean(form[f]) === p.values[f]));
  return hit ? hit.id : null;
}

/** The patch that picking a card writes into the page's edit buffer. */
export function handsOffPatch(id: HandsOffPresetId): SettingsPatch {
  const p = HANDS_OFF_PRESETS.find((x) => x.id === id);
  return p ? { ...p.values } : {};
}

/**
 * Whether the six switches differ from what is saved — picking a card is a
 * preview until **Save settings**, like every other control on the page, so
 * the section says so rather than letting a picked card look already applied.
 */
export function pipelineUnsaved(form: SettingsForm, saved: SettingsForm): boolean {
  return PIPELINE_FIELDS.some((f) => Boolean(form[f]) !== Boolean(saved[f]));
}

/** `watch_quiet_period_s` as the words the Notice step uses. */
export function quietWords(seconds: unknown): string {
  const s = typeof seconds === "number" && Number.isFinite(seconds) && seconds > 0 ? seconds : 30;
  // A no-break space, so a narrow card never strands the unit on its own line.
  if (s < 60) return `${Math.round(s)}\u00a0s`;
  const m = Math.round(s / 6) / 10;
  return `${m}\u00a0min`;
}
