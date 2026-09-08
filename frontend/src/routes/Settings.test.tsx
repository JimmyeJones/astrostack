import { MantineProvider } from "@mantine/core";
import { Notifications } from "@mantine/notifications";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  autoCastSummaryText, autoHighlightSummaryText, dropEmptyFields, HINTS,
  Maintenance, reprocessNudgeText, SETTINGS_PAGE_SECTIONS, SettingsView,
  WALK_AWAY_KEYS, walkAwayEnabled, withWalkAway,
} from "./Settings";
import { SETTINGS_SECTIONS, settingsLink, type SettingsSection } from "../settingsSections";
import * as client from "../api/client";
import { stackPlacementMismatches } from "../test/stackOptionPlacement";

function renderMaintenance() {
  const qc = new QueryClient();
  return render(
    <MantineProvider>
      <Notifications />
      <QueryClientProvider client={qc}>
        <MemoryRouter>
          <Maintenance />
        </MemoryRouter>
      </QueryClientProvider>
    </MantineProvider>,
  );
}

// Maintenance now queries reprocess-status on mount; default it to "nothing
// outdated" so the existing button tests don't hit an unmocked fetch. Individual
// tests override it.
beforeEach(() => {
  vi.spyOn(client.api, "reprocessStatus").mockResolvedValue({
    current_version: "0.81.3", outdated: 0, up_to_date: 3, total_targets: 3,
  });
  // Maintenance also queries the auto-cast summary on mount; default to "nothing
  // measured yet" so the button tests don't hit an unmocked fetch.
  vi.spyOn(client.api, "autoCastSummary").mockResolvedValue({
    measured: 0, neutral: 0, cast: 0, by_cast: {}, median_deviation: null,
  });
  // …and its highlight sibling, for the same reason.
  vi.spyOn(client.api, "autoHighlightSummary").mockResolvedValue({
    measured: 0, blown: 0, median_strength: null,
    median_flat_fraction: null, max_flat_fraction: null,
  });
});

afterEach(() => vi.restoreAllMocks());

describe("dropEmptyFields", () => {
  it("omits emptied (\"\") fields so a cleared non-nullable numeric never 422s the whole save", () => {
    // Regression: clearing e.g. ASTAP FOV sent 0/"" which failed the backend's
    // ge= bound with a raw 422, discarding every other edit in the form. The
    // emptied field is now dropped (keeps its stored value); the rest still save.
    const out = dropEmptyFields({
      astap_fov_deg: "",
      watch_quiet_period_s: 45,
      auth_enabled: true,
    });
    expect(out).not.toHaveProperty("astap_fov_deg");
    expect(out.watch_quiet_period_s).toBe(45);
    expect(out.auth_enabled).toBe(true);
  });

  it("preserves an explicit null (a nullable field the user cleared) and falsy-but-valid values", () => {
    const out = dropEmptyFields({
      cpu_workers: null,     // "auto" — a real, intended value
      astap_timeout_s: 0,    // still sent (bounds-checked server-side), not ""
      watcher_enabled: false,
      seestar_known_ips: [],
    });
    expect(out.cpu_workers).toBeNull();
    expect(out.astap_timeout_s).toBe(0);
    expect(out.watcher_enabled).toBe(false);
    expect(out.seestar_known_ips).toEqual([]);
  });
});

describe("reprocessNudgeText", () => {
  it("returns null when nothing is outdated or status is missing", () => {
    expect(reprocessNudgeText(undefined)).toBeNull();
    expect(reprocessNudgeText({
      current_version: "0.81.3", outdated: 0, up_to_date: 4, total_targets: 4,
    })).toBeNull();
  });

  it("names a single outdated target with the running version", () => {
    const msg = reprocessNudgeText({
      current_version: "0.81.3", outdated: 1, up_to_date: 2, total_targets: 3,
    });
    expect(msg).toContain("1 target was");
    expect(msg).toContain("v0.81.3");
    expect(msg).toContain("non-destructive");
  });

  it("pluralises multiple outdated targets", () => {
    const msg = reprocessNudgeText({
      current_version: "0.81.3", outdated: 3, up_to_date: 0, total_targets: 3,
    });
    expect(msg).toContain("3 targets were");
    expect(msg).toContain("Reprocess them");
  });
});

describe("autoCastSummaryText", () => {
  it("returns null when nothing has been measured or the summary is missing", () => {
    expect(autoCastSummaryText(undefined)).toBeNull();
    expect(autoCastSummaryText({
      measured: 0, neutral: 0, cast: 0, by_cast: {}, median_deviation: null,
    })).toBeNull();
  });

  it("reports an all-neutral result cleanly", () => {
    const msg = autoCastSummaryText({
      measured: 5, neutral: 5, cast: 0, by_cast: {}, median_deviation: 0.004,
    });
    expect(msg).toContain("neutral on all 5 auto-edited results");
    expect(msg).toContain("landing clean");
  });

  it("splits neutral vs cast and names the dominant tints commonest-first", () => {
    const msg = autoCastSummaryText({
      measured: 10, neutral: 7, cast: 3,
      by_cast: { magenta: 1, green: 2 }, median_deviation: 0.018,
    });
    expect(msg).toContain("neutral on 7 of 10 auto-edited results");
    expect(msg).toContain("3 carried a slight cast");
    // Green (2) is listed before magenta (1).
    expect(msg).toMatch(/2 green, 1 magenta/);
  });

  it("uses the singular for a single measured result", () => {
    const msg = autoCastSummaryText({
      measured: 1, neutral: 0, cast: 1,
      by_cast: { green: 1 }, median_deviation: 0.02,
    });
    expect(msg).toContain("neutral on 0 of 1 auto-edited result;");
  });
});

describe("Auto-stack hint", () => {
  // The hands-off stack makes two choices the user never sees a form for
  // (`auto_reject` and `quality_weighted`, both injected in
  // `webapp/pipeline.py::_stack_target` on the `auto` path). If the copy doesn't
  // say so, the app is silently changing how the picture is combined — so the
  // wording is pinned here rather than left to drift.
  it("says what a hands-off stack decides on your behalf", () => {
    expect(HINTS.auto_stack).toMatch(/removes outliers/i);
    expect(HINTS.auto_stack).toMatch(/sharper/i);
  });

  it("says those choices only apply when you haven't made one yourself", () => {
    expect(HINTS.auto_stack).toMatch(/only apply when you haven't picked/i);
    expect(HINTS.auto_stack).toMatch(/Stack form is never touched/i);
  });

  // v0.391.0 flipped the shipped default to on. That reaches a *fresh* install
  // only — an existing config.json keeps whatever it stored (AGENTS.md §9) — and
  // the switch is the same switch it always was, so the copy has to be honest
  // about both halves or an owner upgrading will expect a change that isn't
  // coming.
  it("says the default is on for new installs and unchanged for existing ones", () => {
    expect(HINTS.auto_stack).toMatch(/on for new installs/i);
    expect(HINTS.auto_stack).toMatch(/keeps whatever you last set/i);
  });

  // The three guards that made turning it on by default defensible. If the copy
  // doesn't name them, "it stacks on its own now" reads as a risk rather than a
  // feature.
  it("names the guards that keep a hands-off stack from publishing rubbish", () => {
    expect(HINTS.auto_stack).toMatch(/waits for the night to settle/i);
    expect(HINTS.auto_stack).toMatch(/too few located subs/i);
    expect(HINTS.auto_stack).toMatch(/never replaces a good picture with a thinner one/i);
  });
});

// v0.394.0 flipped auto_edit_on_autostack's shipped default to on, with the
// owner's condition ("easy to override with manual settings") shipping alongside
// it rather than after it. The copy has to carry both halves — the same
// fresh-install-only caveat auto_stack's does, and where to find the override —
// because he has been bitten by an on-by-default reframing before (v0.226.0's
// auto-crop) and the switch must be findable *before* the first surprise.
describe("Settings — auto-edit the walk-away picture", () => {
  it("says the default is on for new installs and unchanged for existing ones", () => {
    expect(HINTS.auto_edit_on_autostack).toMatch(/on for new installs/i);
    expect(HINTS.auto_edit_on_autostack).toMatch(/keeps whatever you last set/i);
  });

  it("names every way out, so nothing it does is a thing you cannot undo", () => {
    expect(HINTS.auto_edit_on_autostack).toMatch(/one Reset from the plain stack/i);
    expect(HINTS.auto_edit_on_autostack).toMatch(/never written over/i);
    expect(HINTS.auto_edit_on_autostack)
      .toMatch(/leave that one target's pictures alone/i);
  });
});

describe("Walk-away mode", () => {
  it("is off unless every one of the bundled switches is on", () => {
    expect(walkAwayEnabled({})).toBe(false);
    // All but one on → still off (the master switch mirrors the real state).
    const allButOne: Record<string, unknown> = {};
    WALK_AWAY_KEYS.forEach((k) => (allButOne[k] = true));
    allButOne[WALK_AWAY_KEYS[0]] = false;
    expect(walkAwayEnabled(allButOne)).toBe(false);
  });

  it("is on exactly when all bundled switches are on", () => {
    const all: Record<string, unknown> = {};
    WALK_AWAY_KEYS.forEach((k) => (all[k] = true));
    expect(walkAwayEnabled(all)).toBe(true);
  });

  it("turning it on sets every bundled switch true without touching others", () => {
    const before = { auto_qc: true, keep_streaked_frames: false };
    const after = withWalkAway(before, true);
    WALK_AWAY_KEYS.forEach((k) => expect(after[k]).toBe(true));
    // Unrelated settings are preserved untouched.
    expect(after.auto_qc).toBe(true);
    expect(after.keep_streaked_frames).toBe(false);
    // Input is not mutated (returns a fresh object).
    expect(before).not.toHaveProperty("auto_stack");
  });

  it("turning it off clears every bundled switch", () => {
    const on: Record<string, unknown> = { auto_qc: true };
    WALK_AWAY_KEYS.forEach((k) => (on[k] = true));
    const after = withWalkAway(on, false);
    WALK_AWAY_KEYS.forEach((k) => expect(after[k]).toBe(false));
    expect(after.auto_qc).toBe(true);
  });

  it("bundles the five hands-off pipeline switches", () => {
    expect([...WALK_AWAY_KEYS]).toEqual([
      "auto_stack",
      "auto_edit_on_autostack",
      "auto_bind_calibration",
      "auto_grade_frames",
      "mixed_pointing_guard",
    ]);
  });
});

describe("Maintenance — Auto colour self-check", () => {
  it("shows the sky-cast read-out once auto-edited runs are measured", async () => {
    vi.spyOn(client.api, "autoCastSummary").mockResolvedValue({
      measured: 4, neutral: 3, cast: 1, by_cast: { green: 1 }, median_deviation: 0.012,
    });
    renderMaintenance();
    await waitFor(() =>
      expect(screen.getByText(/neutral on 3 of 4 auto-edited results/))
        .toBeInTheDocument());
  });

  it("shows no read-out before any auto-edited run is measured", async () => {
    renderMaintenance();
    await waitFor(() =>
      expect(screen.getByRole("button", { name: /Reprocess .* targets/ }))
        .toBeInTheDocument());
    expect(screen.queryByText(/auto-edited result/)).toBeNull();
  });
});

describe("autoHighlightSummaryText", () => {
  it("returns null when nothing has been measured or the summary is missing", () => {
    expect(autoHighlightSummaryText(undefined)).toBeNull();
    expect(autoHighlightSummaryText({
      measured: 0, blown: 0, median_strength: null,
      median_flat_fraction: null, max_flat_fraction: null,
    })).toBeNull();
  });

  it("reassures when every measured run came out with its highlights held", () => {
    // The whole reason the null reading is stamped rather than left absent: a
    // library of clean cores must read as "measured and fine", not as silence.
    const msg = autoHighlightSummaryText({
      measured: 6, blown: 0, median_strength: null,
      median_flat_fraction: null, max_flat_fraction: null,
    });
    expect(msg).toContain("None of the 6 auto-edited results");
    expect(msg).toContain("holding your highlights");
  });

  it("counts the blown ones and names the strength that would reopen them", () => {
    const msg = autoHighlightSummaryText({
      measured: 8, blown: 3, median_strength: 0.6,
      median_flat_fraction: 0.24, max_flat_fraction: 0.55,
    });
    expect(msg).toContain("3 of 8 auto-edited results");
    expect(msg).toContain("Hold back highlights");
    expect(msg).toContain("60%");
    expect(msg).toContain("them");
  });

  it("stays honest when only one run is blown and no strength is known", () => {
    const msg = autoHighlightSummaryText({
      measured: 1, blown: 1, median_strength: null,
      median_flat_fraction: null, max_flat_fraction: null,
    });
    expect(msg).toContain("1 of 1 auto-edited result");
    expect(msg).not.toContain("Hold back highlights");
  });
});

describe("Maintenance — Auto highlight self-check", () => {
  it("shows the read-out once auto-edited runs are measured", async () => {
    vi.spyOn(client.api, "autoHighlightSummary").mockResolvedValue({
      measured: 4, blown: 1, median_strength: 0.4,
      median_flat_fraction: 0.2, max_flat_fraction: 0.2,
    });
    renderMaintenance();
    await waitFor(() =>
      expect(screen.getByText(/1 of 4 auto-edited results came out with a washed-out/))
        .toBeInTheDocument());
  });

  it("shows no read-out before any auto-edited run is measured", async () => {
    renderMaintenance();
    await waitFor(() =>
      expect(screen.getByRole("button", { name: /Reprocess .* targets/ }))
        .toBeInTheDocument());
    expect(screen.queryByText(/washed-out bright core/)).toBeNull();
  });
});

describe("Maintenance — outdated-images nudge", () => {
  it("shows the nudge Alert when targets are outdated", async () => {
    vi.spyOn(client.api, "reprocessStatus").mockResolvedValue({
      current_version: "0.81.3", outdated: 2, up_to_date: 1, total_targets: 3,
    });
    renderMaintenance();
    await waitFor(() =>
      expect(screen.getByText(/2 targets were last stacked with an older/))
        .toBeInTheDocument());
    expect(screen.getByText("Some images are out of date")).toBeInTheDocument();
  });

  it("shows no nudge when everything is up to date", async () => {
    renderMaintenance();
    // Let the (mocked) status query settle, then assert the nudge is absent.
    await waitFor(() =>
      expect(screen.getByRole("button", { name: /Reprocess .* targets/ }))
        .toBeInTheDocument());
    expect(screen.queryByText("Some images are out of date")).toBeNull();
  });
});

describe("Maintenance — reprocess everything", () => {
  it("does nothing when the confirm is declined", () => {
    vi.spyOn(window, "confirm").mockReturnValue(false);
    const call = vi.spyOn(client.api, "reprocessAll");

    renderMaintenance();
    fireEvent.click(screen.getByRole("button", { name: /Reprocess .* targets/ }));

    expect(call).not.toHaveBeenCalled();
  });

  it("defaults to reprocessing only outdated targets (stale_only=true)", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    const call = vi
      .spyOn(client.api, "reprocessAll")
      .mockResolvedValue({ job_id: "job-9", already_running: false });

    renderMaintenance();
    // The default button names the "outdated" scope, matching the default toggle.
    fireEvent.click(screen.getByRole("button", { name: /Reprocess outdated targets/ }));

    // Default: outdated-only on, deep rescan off, auto-edit off.
    await waitFor(() => expect(call).toHaveBeenCalledWith(true, false, false));
    await waitFor(() =>
      expect(screen.getByText(/Reprocessing targets/)).toBeInTheDocument());
  });

  it("reprocesses every target when the outdated-only toggle is turned off", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    const call = vi
      .spyOn(client.api, "reprocessAll")
      .mockResolvedValue({ job_id: "job-9", already_running: false });

    renderMaintenance();
    fireEvent.click(screen.getByLabelText(/Only targets not already stacked on this version/));
    fireEvent.click(screen.getByRole("button", { name: /Reprocess all targets/ }));

    await waitFor(() => expect(call).toHaveBeenCalledWith(false, false, false));
  });

  it("passes deep_rescan when the QC/solve/grade toggle is turned on", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    const call = vi
      .spyOn(client.api, "reprocessAll")
      .mockResolvedValue({ job_id: "job-9", already_running: false });

    renderMaintenance();
    fireEvent.click(screen.getByLabelText(/re-run QC, plate-solving & grading/));
    fireEvent.click(screen.getByRole("button", { name: /Reprocess .* targets/ }));

    // Still outdated-only by default, now with the deep rescan opted in.
    await waitFor(() => expect(call).toHaveBeenCalledWith(true, true, false));
  });

  it("passes auto_edit when the auto-edit toggle is turned on", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    const call = vi
      .spyOn(client.api, "reprocessAll")
      .mockResolvedValue({ job_id: "job-9", already_running: false });

    renderMaintenance();
    fireEvent.click(screen.getByLabelText(/auto-edit each result into a finished picture/));
    fireEvent.click(screen.getByRole("button", { name: /Reprocess .* targets/ }));

    // Still outdated-only by default, now with the auto-edit opted in.
    await waitFor(() => expect(call).toHaveBeenCalledWith(true, false, true));
  });

  it("surfaces the already-running case", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    vi.spyOn(client.api, "reprocessAll")
      .mockResolvedValue({ job_id: "job-9", already_running: true });

    renderMaintenance();
    fireEvent.click(screen.getByRole("button", { name: /Reprocess .* targets/ }));

    await waitFor(() =>
      expect(screen.getByText(/already running/)).toBeInTheDocument());
  });

  it("shows an error notification when the request fails", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    vi.spyOn(client.api, "reprocessAll").mockRejectedValue(new Error("boom"));

    renderMaintenance();
    fireEvent.click(screen.getByRole("button", { name: /Reprocess .* targets/ }));

    await waitFor(() => expect(screen.getByText("boom")).toBeInTheDocument());
  });
});

// --- Automated stacking defaults: the pick-time weighting caution -----------
// The defaults grid is descriptor-driven with no cross-field logic, so the one
// self-cancelling pair (min/max rejection + quality weighting) had no warning on
// the very screen a walk-away user sets it from.

const STACK_FIELDS = [
  { key: "min_max_reject", label: "Min/max rejection", type: "bool", group: "simple",
    default: false, min: null, max: null, step: null, options: null, help: null,
    depends_on: null },
  { key: "quality_weighted", label: "Quality weighting", type: "bool", group: "simple",
    default: false, min: null, max: null, step: null, options: null, help: null,
    depends_on: null },
  { key: "drizzle", label: "Drizzle", type: "bool", group: "simple",
    default: false, min: null, max: null, step: null, options: null, help: null,
    depends_on: null },
] as client.StackOptionField[];

// The fixtures above must place their controls where the engine does: Settings
// renders them through the same `StackOptionControl` as the Stack form, so a
// fixture that gets `group`/`type`/`depends_on` wrong tests a screen the user
// never sees (see `stackOptionPlacement.ts`).
it("places its stack-option fixtures where the engine does", () => {
  expect(stackPlacementMismatches(STACK_FIELDS)).toEqual([]);
});

function renderSettingsWith(
  stackDefaults: Record<string, unknown>,
  // Settings is split into sections at `/settings/<section>`; the stacking
  // defaults live on this one. `null` renders the bare `/settings` landing.
  section: SettingsSection | null = "stacking",
  // Extra saved settings for a test that needs real values in the form (the
  // folder fields, say). Omitted, the fixture is exactly what it always was.
  extraSettings: Record<string, unknown> = {},
) {
  vi.spyOn(client.api, "getSettings").mockResolvedValue({
    default_stack_options: stackDefaults, ...extraSettings,
  } as never);
  vi.spyOn(client.api, "getSystem").mockResolvedValue({
    version: "0.0.0", data_root: "/data", cpu_count: 4, cpu_workers: 3,
    gpu_available: false,
    astap: { found: true, path: "/usr/bin/astap", star_db_found: true },
    disk: {}, memory: {}, watcher_enabled: false,
  } as never);
  vi.spyOn(client.api, "optionsSchema").mockResolvedValue(STACK_FIELDS);
  vi.spyOn(client.api, "authStatus").mockResolvedValue({ enabled: false } as never);
  const qc = new QueryClient();
  return render(
    <MantineProvider>
      <Notifications />
      <QueryClientProvider client={qc}>
        {/* Rendered through the real routes so `useParams` sees the section,
            exactly as the app does. */}
        <MemoryRouter initialEntries={[section ? `/settings/${section}` : "/settings"]}>
          <Routes>
            <Route path="/settings" element={<SettingsView />} />
            <Route path="/settings/:section" element={<SettingsView />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>
    </MantineProvider>,
  );
}

// --- The page's sections ----------------------------------------------------
// Settings was the app's tallest page by a factor of two (5827 px on a phone),
// with seven full-width blocks stacked one below another and half the app's
// settings filed under a card called "Watched folders". It is now one section
// per URL. The risk that buys is a *deep link that lands on a hidden control* —
// several screens send the user here to fix one specific thing — so each of
// those is pinned below.

describe("Settings sections", () => {
  it("renders exactly the sections the rest of the app links to", () => {
    // `settingsSections.ts` is what "Fix in Settings" and friends point at; if a
    // section is renamed on one side only, those links land on a fallback.
    expect(SETTINGS_PAGE_SECTIONS.map((s) => s.key)).toEqual([...SETTINGS_SECTIONS]);
  });

  it("shows one section at a time, with the others still mounted", async () => {
    renderSettingsWith({}, "folders");

    await waitFor(() =>
      expect(screen.getByText("Watched folders")).toBeVisible());
    // Nothing was removed — every other section is in the DOM, one click away.
    expect(screen.getByText("Automatic pipeline")).toBeInTheDocument();
    expect(screen.getByText("Automatic pipeline")).not.toBeVisible();
    expect(screen.getByText("Reprocess everything")).toBeInTheDocument();
    expect(screen.getByText("Reprocess everything")).not.toBeVisible();
  });

  it("opens the first section for a bare /settings", async () => {
    renderSettingsWith({}, null);
    await waitFor(() => expect(screen.getByText("Watched folders")).toBeVisible());
  });

  it("lands the app's star-database link on a VISIBLE ASTAP control", async () => {
    // The Dashboard's "Plate-solving isn't set up yet" alert, the Target page's
    // solve-failure note and a stack's health card all send the user to
    // `settingsLink("plate-solving")` — landing them on a tab where the control
    // is hidden would be worse than the long page was.
    expect(settingsLink("plate-solving")).toBe("/settings/plate-solving");
    renderSettingsWith({}, "plate-solving");

    await waitFor(() => expect(screen.getByLabelText(/ASTAP path/)).toBeVisible());
    expect(screen.getByLabelText(/ASTAP FOV/)).toBeVisible();
  });

  it("lands the Tonight planner's location link on a VISIBLE latitude field", async () => {
    expect(settingsLink("observing-site")).toBe("/settings/observing-site");
    renderSettingsWith({}, "observing-site");

    await waitFor(() => expect(screen.getByLabelText(/Latitude/)).toBeVisible());
    expect(screen.getByLabelText(/Minimum target altitude/)).toBeVisible();
  });

  it("lands the Dashboard's folder warning on a VISIBLE data-root field", async () => {
    expect(settingsLink("folders")).toBe("/settings/folders");
    renderSettingsWith({}, "folders");

    await waitFor(() => expect(screen.getByLabelText(/Data root/)).toBeVisible());
  });

  it("files the mis-homed settings where their section name predicts", async () => {
    // These three used to live inside a card titled "Watched folders", which is
    // the one place a beginner would never look for them.
    renderSettingsWith({}, "observing-site");
    await waitFor(() => expect(screen.getByLabelText(/Latitude/)).toBeVisible());
    expect(screen.getByLabelText(/Data root/)).not.toBeVisible();

    cleanup();
    renderSettingsWith({}, "stacking");
    await waitFor(() =>
      expect(screen.getByLabelText(/Stack memory budget/)).toBeVisible());

    cleanup();
    renderSettingsWith({}, "maintenance");
    await waitFor(() =>
      expect(screen.getByLabelText(/Job history to keep/)).toBeVisible());
  });

  it("keeps an unsaved edit when you move to another section and save from there", async () => {
    // The sections share one edit buffer; a save from any of them sends the lot,
    // so a value typed on one tab is not lost by pressing Save on another.
    const put = vi.spyOn(client.api, "putSettings").mockResolvedValue({} as never);
    renderSettingsWith({}, "folders");

    await waitFor(() => expect(screen.getByLabelText(/Data root/)).toBeVisible());
    fireEvent.change(screen.getByLabelText(/Data root/), { target: { value: "/mnt/new" } });

    fireEvent.click(screen.getByRole("tab", { name: "This device" }));
    await waitFor(() =>
      expect(screen.getByLabelText(/Enable Seestar integration/)).toBeVisible());
    fireEvent.click(screen.getByLabelText(/Enable Seestar integration/));
    fireEvent.click(screen.getAllByRole("button", { name: "Save settings" })[0]);

    await waitFor(() => expect(put).toHaveBeenCalled());
    const patch = put.mock.calls[0][0] as Record<string, unknown>;
    expect(patch.data_root).toBe("/mnt/new");
    expect(patch.seestar_enabled).toBe(true);
  });
});

describe("Automated stacking defaults — min/max vs quality weighting", () => {
  it("warns when both defaults are on, worded for an unknown frame count", async () => {
    renderSettingsWith({ min_max_reject: true, quality_weighted: true, drizzle: false });

    await waitFor(() =>
      expect(screen.getByText(/On any stack of 3 or more subs/)).toBeInTheDocument());
    expect(screen.getByRole("button", { name: "Turn off quality weighting" }))
      .toBeInTheDocument();
  });

  it("stays quiet when only one of the two is on", async () => {
    renderSettingsWith({ min_max_reject: true, quality_weighted: false, drizzle: false });

    await waitFor(() =>
      expect(screen.getByText("Automated stacking defaults")).toBeInTheDocument());
    expect(screen.queryByText(/don't combine/)).toBeNull();
  });

  it("stays quiet on the drizzle path, where the weights still apply", async () => {
    renderSettingsWith({ min_max_reject: true, quality_weighted: true, drizzle: true });

    await waitFor(() =>
      expect(screen.getByText("Automated stacking defaults")).toBeInTheDocument());
    expect(screen.queryByText(/don't combine/)).toBeNull();
  });

  it("clears the conflict in place when the fix button is pressed", async () => {
    renderSettingsWith({ min_max_reject: true, quality_weighted: true, drizzle: false });

    await waitFor(() =>
      expect(screen.getByText(/On any stack of 3 or more subs/)).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: "Turn off quality weighting" }));

    await waitFor(() => expect(screen.queryByText(/don't combine/)).toBeNull());
  });
});

// The ASTAP timeout bounds ONE solve attempt, not one frame: the solver runs a
// 3-rung ladder and a timeout on a rung falls through to the next, so an
// unsolvable frame can take up to ~3× the setting. The hint must say so rather
// than claim "a single frame", or a user under-sets it expecting a per-frame cap.
describe("astap_timeout_s hint honesty", () => {
  it("describes the timeout as per-attempt, not per-frame", () => {
    const hint = HINTS.astap_timeout_s;
    expect(hint).toMatch(/each solve attempt/i);
    expect(hint).toMatch(/3/); // names the up-to-3× multiplier
    expect(hint).not.toMatch(/solving a single frame after/i); // the old, misleading wording
  });
});

// Pointing the library (or the data root, which carries state/config.json) at
// somewhere inside `incoming/` is the one layout the app must never accept: every
// clean-up it does is correctly scoped to its own tree, which is exactly why
// nesting one inside the other would make a correct `rmtree` resolve inside the
// owner's only copy of their raw subs. The server refuses that save and stays the
// authority; this is the same question asked while the user types, so the answer
// lands beside the field instead of arriving as a red toast reading "422: …".
describe("folder conflict, while you type", () => {
  it("marks the offending field and holds Save", async () => {
    renderSettingsWith({}, "folders", {
      data_root: "/data", incoming_dir: "/data/incoming", library_root: "/data/library",
    });

    await waitFor(() =>
      expect(screen.getByText("Watched folders")).toBeVisible());
    const save = screen.getAllByRole("button", { name: "Save settings" })[0];
    expect(save).not.toBeDisabled();

    fireEvent.change(screen.getByLabelText(/Library root/), {
      target: { value: "/data/incoming/library" },
    });

    await waitFor(() => expect(
      screen.getByText(/would sit inside the incoming folder/)).toBeVisible());
    expect(screen.getAllByRole("button", { name: "Save settings" })[0]).toBeDisabled();
  });

  it("lets go the moment the folder is moved back out", async () => {
    renderSettingsWith({}, "folders", {
      data_root: "/data", incoming_dir: "/data/incoming",
      library_root: "/data/incoming/library",
    });

    await waitFor(() => expect(
      screen.getByText(/would sit inside the incoming folder/)).toBeVisible());

    fireEvent.change(screen.getByLabelText(/Library root/), {
      target: { value: "/data/library" },
    });

    await waitFor(() => expect(
      screen.queryByText(/would sit inside the incoming folder/)).toBeNull());
    expect(screen.getAllByRole("button", { name: "Save settings" })[0]).not.toBeDisabled();
  });

  it("stays out of the way of a layout it cannot judge", async () => {
    // A relative path resolves against the server's working directory, which a
    // browser cannot know — so the client says nothing and lets the server, which
    // can, decide. Being quieter than the guard is allowed; being louder is not.
    renderSettingsWith({}, "folders", {
      data_root: "/data", incoming_dir: "incoming", library_root: "incoming/library",
    });

    await waitFor(() =>
      expect(screen.getByText("Watched folders")).toBeVisible());
    expect(screen.queryByText(/would sit inside the incoming folder/)).toBeNull();
    expect(screen.getAllByRole("button", { name: "Save settings" })[0]).not.toBeDisabled();
  });
});

// A method saved once is a decision made at one depth and applied to every night
// after it — and sigma clipping, the one most owners save, cannot pick out a lone
// satellite trail below about 11 subs. `auto_reject_on_unattended` is the opt-in
// that hands that choice back to the app on hands-off stacks only.
describe("Automatic pipeline — let AstroStack pick outlier removal", () => {
  const LABEL = /Let AstroStack pick outlier removal on hands-off stacks/;

  it("is off for an install that has never set it", async () => {
    renderSettingsWith({}, "automation");
    const sw = await screen.findByLabelText(LABEL);
    expect(sw).not.toBeChecked();
  });

  it("reads the saved value back", async () => {
    renderSettingsWith({}, "automation", { auto_reject_on_unattended: true });
    await waitFor(() => expect(screen.getByLabelText(LABEL)).toBeChecked());
  });

  it("is not bundled into Walk-away mode", () => {
    // Walk-away turns the unattended pipeline *on*; it must not also overrule a
    // rejection method the owner deliberately saved. That stays its own choice.
    expect([...WALK_AWAY_KEYS]).not.toContain("auto_reject_on_unattended");
  });
});

// --- the walk-away settle window (v0.390.1) ---------------------------------

describe("Automatic pipeline — wait for the night to settle", () => {
  const SETTLE = /wait for the night to settle/i;

  it("shows the window with the rest of the Auto-stack group", async () => {
    renderSettingsWith({}, "automation", { auto_stack: true, auto_stack_settle_min: 20 });
    const field = await screen.findByLabelText(SETTLE);
    await waitFor(() => expect(field).toHaveValue("20"));
    expect(field).not.toBeDisabled();
  });

  it("is greyed out while auto-stack is off, like the rest of the group", async () => {
    renderSettingsWith({}, "automation", { auto_stack: false });
    await waitFor(() => expect(screen.getByLabelText(SETTLE)).toBeDisabled());
  });

  it("explains, in plain language, why waiting is the point", async () => {
    renderSettingsWith({}, "automation", { auto_stack: true });
    await screen.findByLabelText(SETTLE);
    // The hint has to answer "why is my picture not updating yet?" without the
    // reader knowing what a poll or a scan is.
    const hint = HINTS.auto_stack_settle_min;
    expect(hint).toMatch(/while you're still shooting/i);
    expect(hint).toMatch(/Nothing is ever skipped/i);
    expect(hint).toMatch(/Set to 0/i);
  });
});
