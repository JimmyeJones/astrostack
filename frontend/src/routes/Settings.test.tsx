import { MantineProvider } from "@mantine/core";
import { Notifications } from "@mantine/notifications";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  autoCastSummaryText, autoHighlightSummaryText, dropEmptyFields, HINTS,
  Maintenance, newLightScopeText, reprocessNudgeText, reprocessPictureWarning,
  reprocessScopeCounts,
  SETTINGS_PAGE_SECTIONS, SettingsView,
  WALK_AWAY_KEYS, walkAwayEnabled, withWalkAway,
} from "./Settings";
import { SETTINGS_SECTIONS, settingsLink, type SettingsSection } from "../settingsSections";
import * as client from "../api/client";
import { stackPlacementMismatches } from "../test/stackOptionPlacement";

function renderMaintenance(entry = "/settings/maintenance") {
  const qc = new QueryClient();
  return render(
    <MantineProvider>
      <Notifications />
      <QueryClientProvider client={qc}>
        {/* The card reads `?scope=` so the Dashboard note can send someone here
            with their answer already given; every existing caller lands on the
            bare path and gets the default. */}
        <MemoryRouter initialEntries={[entry]}>
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

  it("sends the blank for the three fields whose blank IS the value", () => {
    // Regression: these are the only way back from a custom folder or subnet —
    // blank means "the standard folder under the data root" / "work the subnet
    // out for me". Dropping their "" made clearing the box a no-op that said
    // "Settings saved", so a custom Incoming dir could never be undone.
    const out = dropEmptyFields({
      incoming_dir: "", library_root: "", seestar_scan_subnet: "",
      data_root: "",          // no blank meaning — still dropped
      astap_fov_deg: "",      // a cleared numeric — still dropped
    });
    expect(out.incoming_dir).toBe("");
    expect(out.library_root).toBe("");
    expect(out.seestar_scan_subnet).toBe("");
    expect(out).not.toHaveProperty("data_root");
    expect(out).not.toHaveProperty("astap_fov_deg");
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

describe("reprocessPictureWarning", () => {
  // Observer issue #903, closed from the other side (2026-09-30 audit, C-F4):
  // the batch now keeps a picture the owner finished by hand on the wall and
  // re-finishes the app-finished ones, so this sentence is the *promise* with
  // its count, not a warning about a flat stack that will not happen.
  const base = {
    current_version: "0.447.1", outdated: 3, up_to_date: 1, total_targets: 5,
    finished_pictures: 4, finished_pictures_stale_only: 2,
    hand_finished: 3, hand_finished_stale_only: 1,
  };

  it("still speaks when the results will be auto-edited — his own work is kept either way", () => {
    const msg = reprocessPictureWarning(base, { scope: "stale" as const, autoEdit: true });
    expect(msg).toContain("1 of these targets shows a picture you finished yourself");
    expect(msg).toContain("doesn't replace your own work");
  });

  it("says nothing when no target shows a hand-finished picture", () => {
    expect(reprocessPictureWarning(
      { ...base, hand_finished: 0, hand_finished_stale_only: 0 },
      { scope: "all" as const, autoEdit: false },
    )).toBeNull();
  });

  it("stays silent on a backend that doesn't send the counts", () => {
    expect(reprocessPictureWarning(
      { current_version: "0.1.0", outdated: 3, up_to_date: 1, total_targets: 5,
        finished_pictures: 4 },
      { scope: "all" as const, autoEdit: false },
    )).toBeNull();
    expect(reprocessPictureWarning(undefined, { scope: "all" as const, autoEdit: false }))
      .toBeNull();
  });

  it("quotes the hand-finished count for the scope the user actually chose", () => {
    const all = reprocessPictureWarning(base, { scope: "all" as const, autoEdit: false });
    expect(all).toContain("3 of these targets show pictures you finished yourself");
    const stale = reprocessPictureWarning(base, { scope: "stale" as const, autoEdit: false });
    expect(stale).toContain("1 of these targets shows a picture you finished yourself");
    const light = reprocessPictureWarning(
      { ...base, hand_finished_new_light_only: 2 },
      { scope: "new-light" as const, autoEdit: false });
    expect(light).toContain("2 of these targets show pictures you finished yourself");
  });

  it("names what happens to them, where the deeper result goes, and what Auto's pictures get", () => {
    const msg = reprocessPictureWarning(base, { scope: "all" as const, autoEdit: false });
    expect(msg).toContain("stay on the wall exactly as they are");
    expect(msg).toContain("History");
    expect(msg).toContain("re-finished on the new result automatically");
    expect(msg).not.toContain("flat, unstretched stack");
  });

  it("reads naturally for a single target", () => {
    const msg = reprocessPictureWarning(
      { ...base, hand_finished: 1 }, { scope: "all" as const, autoEdit: false },
    );
    expect(msg).toContain("It stays on the wall exactly as it is");
    expect(msg).toContain("its deeper restack waits in History");
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

// v0.395.0 flipped auto_edit_on_autostack's shipped default to on, with the
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

describe("Maintenance — the wall-picture promise (#903)", () => {
  // A restack is saved as a new result and the newest result is the picture
  // every wall shows. The batch keeps a hand-finished picture on the wall and
  // re-finishes Auto's, so the panel and the confirm dialog both say so — with
  // the count for the scope the toggle is set to.
  const withFinished = {
    current_version: "0.81.3", outdated: 3, up_to_date: 0, total_targets: 3,
    finished_pictures: 3, finished_pictures_stale_only: 2,
    hand_finished: 3, hand_finished_stale_only: 2,
  };

  it("says it in the panel, in the scope the toggle is set to", async () => {
    vi.spyOn(client.api, "reprocessStatus").mockResolvedValue(withFinished);
    renderMaintenance();
    // Outdated-only is the default scope → the stale-only count.
    await waitFor(() =>
      expect(screen.getByText(/2 of these targets show pictures you finished yourself/))
        .toBeInTheDocument());
    fireEvent.click(screen.getByLabelText(/Every target/));
    await waitFor(() =>
      expect(screen.getByText(/3 of these targets show pictures you finished yourself/))
        .toBeInTheDocument());
  });

  it("keeps saying it once the auto-edit switch is on — his work is kept either way", async () => {
    vi.spyOn(client.api, "reprocessStatus").mockResolvedValue(withFinished);
    renderMaintenance();
    await waitFor(() =>
      expect(screen.getByText(/pictures you finished yourself/)).toBeInTheDocument());
    fireEvent.click(screen.getByLabelText(/auto-edit each result into a finished picture/));
    await waitFor(() =>
      expect(screen.getByText(/doesn't replace your own work/)).toBeInTheDocument());
  });

  it("puts the promise in the confirm dialog too", async () => {
    vi.spyOn(client.api, "reprocessStatus").mockResolvedValue(withFinished);
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);
    renderMaintenance();
    await waitFor(() =>
      expect(screen.getByText(/pictures you finished yourself/)).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: /Reprocess .* targets/ }));

    expect(confirm).toHaveBeenCalled();
    const text = String(confirm.mock.calls[0][0]);
    expect(text).toContain("stay on the wall exactly as they are");
    expect(text).not.toContain("flat, unstretched stack");
    // …and the promises it already made are still there, not replaced.
    expect(text).toContain("nothing is deleted or overwritten");
  });

  it("says nothing on a library with no hand-finished pictures", async () => {
    renderMaintenance();  // the default mock sends no hand_finished at all
    await waitFor(() =>
      expect(screen.getByRole("button", { name: /Reprocess .* targets/ }))
        .toBeInTheDocument());
    expect(screen.queryByText(/of these targets/)).toBeNull();
  });
});

describe("Maintenance — arriving on \"Bring my pictures up to date\"", () => {
  it("defaults the auto-edit switch on for that scope only, and still sends what is chosen", async () => {
    vi.spyOn(client.api, "reprocessStatus").mockResolvedValue({
      current_version: "0.81.3", outdated: 0, up_to_date: 3, total_targets: 3,
      new_light: 2, new_light_subs: 40,
    });
    vi.spyOn(window, "confirm").mockReturnValue(true);
    const call = vi
      .spyOn(client.api, "reprocessAll")
      .mockResolvedValue({ job_id: "job-9", already_running: false });

    renderMaintenance("/settings/maintenance?scope=new-light");
    const toggle = await screen.findByLabelText(/auto-edit each result into a finished picture/);
    expect(toggle).toBeChecked();
    fireEvent.click(await screen.findByRole("button", { name: /Bring my pictures up to date/ }));
    // stale_only off, deep rescan off, auto-edit ON, new-light on.
    await waitFor(() => expect(call).toHaveBeenCalledWith(false, false, true, true));
  });

  it("can be turned off for this visit like any other switch", async () => {
    vi.spyOn(client.api, "reprocessStatus").mockResolvedValue({
      current_version: "0.81.3", outdated: 0, up_to_date: 3, total_targets: 3,
      new_light: 2, new_light_subs: 40,
    });
    vi.spyOn(window, "confirm").mockReturnValue(true);
    const call = vi
      .spyOn(client.api, "reprocessAll")
      .mockResolvedValue({ job_id: "job-9", already_running: false });

    renderMaintenance("/settings/maintenance?scope=new-light");
    fireEvent.click(await screen.findByLabelText(/auto-edit each result into a finished picture/));
    fireEvent.click(await screen.findByRole("button", { name: /Bring my pictures up to date/ }));
    await waitFor(() => expect(call).toHaveBeenCalledWith(false, false, false, true));
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

    // Default: outdated-only on, deep rescan off, auto-edit off, new-light off.
    await waitFor(() => expect(call).toHaveBeenCalledWith(true, false, false, false));
    await waitFor(() =>
      expect(screen.getByText(/Reprocessing targets/)).toBeInTheDocument());
  });

  it("reprocesses every target when that scope is picked", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    const call = vi
      .spyOn(client.api, "reprocessAll")
      .mockResolvedValue({ job_id: "job-9", already_running: false });

    renderMaintenance();
    fireEvent.click(screen.getByLabelText(/Every target/));
    fireEvent.click(screen.getByRole("button", { name: /Reprocess all targets/ }));

    await waitFor(() => expect(call).toHaveBeenCalledWith(false, false, false, false));
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
    await waitFor(() => expect(call).toHaveBeenCalledWith(true, true, false, false));
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
    await waitFor(() => expect(call).toHaveBeenCalledWith(true, false, true, false));
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

// --- "Bring my pictures up to date": the new-light scope (v0.492.0) ---------
//
// The owner shoots many targets across many nights with auto-stack off, so after
// a night's capture his pictures are behind the light he owns. The app named
// those targets on the Dashboard and the batch stacker existed, but its only
// scope asked whether the *engine* had changed — so the in-between his cadence
// needs (strictly less work than the reprocess he already runs, aimed only at
// pictures that would change) could not be expressed.

const withNewLight = {
  current_version: "0.492.0", outdated: 1, up_to_date: 4, total_targets: 5,
  finished_pictures: 4, finished_pictures_stale_only: 1,
  finished_pictures_new_light_only: 2,
  hand_finished: 2, hand_finished_stale_only: 0, hand_finished_new_light_only: 1,
  new_light: 3, new_light_subs: 128,
};

describe("newLightScopeText", () => {
  it("names the targets and the subs, so the cost is visible before the click", () => {
    const msg = newLightScopeText(withNewLight);
    expect(msg).toContain("3 targets");
    expect(msg).toContain("128 subs");
    // The reassurance that makes it safe to press: it is the *small* batch.
    expect(msg).toContain("Every other target is left alone");
  });

  it("reads naturally for one target and one sub", () => {
    const msg = newLightScopeText({ ...withNewLight, new_light: 1, new_light_subs: 1 });
    expect(msg).toContain("1 target whose picture is missing subs you already have");
    expect(msg).toContain("1 sub");
    expect(msg).not.toContain("1 subs");
  });

  it("never says the subs were shot *since* the picture — some were handed back", () => {
    // The scope counts every sub a picture is missing, which includes one the app
    // set aside while the picture was being made and has since put back (see
    // `webapp.routers.newsubs.new_light_since_picture`). Such a sub was shot on
    // the very night the picture is made of, so "you've shot more of these since"
    // would be false of it. The wording has to hold for both kinds.
    const msg = String(newLightScopeText(withNewLight));
    expect(msg).toContain("missing subs you already have");
    expect(msg).not.toMatch(/shot more of since/);
  });

  it("says the good state plainly on a fully caught-up library", () => {
    const msg = newLightScopeText({ ...withNewLight, new_light: 0, new_light_subs: 0 });
    expect(msg).toContain("Nothing is waiting");
  });

  it("invents no count on a backend that doesn't send one", () => {
    expect(newLightScopeText(undefined)).toBeNull();
    expect(newLightScopeText({
      current_version: "0.1.0", outdated: 1, up_to_date: 1, total_targets: 2,
    })).toBeNull();
  });
});

describe("reprocessScopeCounts", () => {
  it("gives each scope its own pair, never another scope's", () => {
    expect(reprocessScopeCounts(withNewLight, "new-light"))
      .toEqual({ targets: 3, finished: 2, handFinished: 1 });
    expect(reprocessScopeCounts(withNewLight, "stale"))
      .toEqual({ targets: 1, finished: 1, handFinished: 0 });
    expect(reprocessScopeCounts(withNewLight, "all"))
      .toEqual({ targets: 5, finished: 4, handFinished: 2 });
  });

  it("answers null rather than zero when the backend is silent", () => {
    // Zero means "measured, and it is none"; null means "not said". Rendering a
    // silent backend as 0 would disable the button on a library that has work.
    expect(reprocessScopeCounts(undefined, "new-light"))
      .toEqual({ targets: null, finished: null, handFinished: null });
    expect(reprocessScopeCounts({
      current_version: "0.1.0", outdated: 1, up_to_date: 1, total_targets: 2,
    }, "new-light")).toEqual({ targets: null, finished: null, handFinished: null });
  });
});

describe("Maintenance — the new-light scope", () => {
  it("sends new_light_only when that scope is picked", async () => {
    vi.spyOn(client.api, "reprocessStatus").mockResolvedValue(withNewLight);
    vi.spyOn(window, "confirm").mockReturnValue(true);
    const call = vi
      .spyOn(client.api, "reprocessAll")
      .mockResolvedValue({ job_id: "job-9", already_running: false });

    renderMaintenance();
    fireEvent.click(screen.getByLabelText(/Only targets whose picture is missing subs/));
    fireEvent.click(
      await screen.findByRole("button", { name: /Bring my pictures up to date/ }));

    // stale_only off (it asks a different question), new_light_only on.
    await waitFor(() => expect(call).toHaveBeenCalledWith(false, false, false, true));
  });

  it("arrives pre-scoped when the Dashboard note sent them here", async () => {
    vi.spyOn(client.api, "reprocessStatus").mockResolvedValue(withNewLight);
    renderMaintenance("/settings/maintenance?scope=new-light");
    expect(await screen.findByRole("button", { name: /Bring my pictures up to date/ }))
      .toBeInTheDocument();
  });

  it("quotes the new-light scope's own hand-finished count, not the library's",
    async () => {
      vi.spyOn(client.api, "reprocessStatus").mockResolvedValue(withNewLight);
      renderMaintenance("/settings/maintenance?scope=new-light");
      // 1, the count for this scope — never 2 (every target) or 0 (stale).
      await waitFor(() =>
        expect(screen.getByText(/1 of these targets shows a picture you finished yourself/))
          .toBeInTheDocument());
    });

  it("won't queue a batch with nothing in it", async () => {
    vi.spyOn(client.api, "reprocessStatus")
      .mockResolvedValue({ ...withNewLight, new_light: 0, new_light_subs: 0 });
    renderMaintenance("/settings/maintenance?scope=new-light");
    await waitFor(() =>
      expect(screen.getByRole("button", { name: /Bring my pictures up to date/ }))
        .toBeDisabled());
    // …and the scope still says why, rather than vanishing.
    expect(screen.getByText(/Nothing is waiting/)).toBeInTheDocument();
  });

  it("puts the cost in the confirm dialog before it queues hours of CPU", async () => {
    vi.spyOn(client.api, "reprocessStatus").mockResolvedValue(withNewLight);
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);
    renderMaintenance("/settings/maintenance?scope=new-light");
    // The scope comes from the URL, so the button is there before the counts
    // are; wait for the numbers themselves, which is what this is about.
    await screen.findByText(/3 targets whose pictures are missing subs/);
    fireEvent.click(
      screen.getByRole("button", { name: /Bring my pictures up to date/ }));

    const text = String(confirm.mock.calls[0][0]);
    expect(text).toContain("3 targets");
    expect(text).toContain("128 subs");
    // The #903 promise and the non-destructive promise both still ride along —
    // and, arriving on this scope, the auto-edit switch is on, so its note too.
    expect(text).toContain("finished yourself");
    expect(text).toContain("also auto-edited");
    expect(text).toContain("nothing is deleted or overwritten");
  });

  it("keeps every scope the switch used to express, one click away", async () => {
    vi.spyOn(client.api, "reprocessStatus").mockResolvedValue(withNewLight);
    renderMaintenance();
    await waitFor(() =>
      expect(screen.getByLabelText(/Only targets not already stacked on this version/))
        .toBeChecked());
    expect(screen.getByLabelText(/Every target/)).toBeInTheDocument();
    expect(screen.getByLabelText(/Only targets whose picture is missing subs/)).toBeInTheDocument();
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
  // What `/api/auth/status` answers. Defaults to the open install every existing
  // caller assumed, so they are unchanged; the access-control tests pass their
  // own (a spy set *before* this helper would be overwritten by it).
  authStatus: Record<string, unknown> = { enabled: false },
  // What `/api/system` reports for memory. `{}` is the old fixture — no RAM
  // figures and no budget — so every existing caller is unchanged; the memory
  // tests pass the fields the endpoint really serves.
  memory: Record<string, unknown> = {},
  // What `GET /api/plan/site` answers. The default is an empty library, so
  // neither the photos nor Settings know where the owner is — the case the
  // Tonight planner links here for.
  site: Record<string, unknown> = {
    location_source: "none", location_reason: "no-frames", observer: null,
    from_photos: null, photos_reason: "no-frames",
  },
) {
  vi.spyOn(client.api, "getSettings").mockResolvedValue({
    default_stack_options: stackDefaults, ...extraSettings,
  } as never);
  vi.spyOn(client.api, "getSystem").mockResolvedValue({
    version: "0.0.0", data_root: "/data", cpu_count: 4, cpu_workers: 3,
    gpu_available: false,
    astap: { found: true, path: "/usr/bin/astap", star_db_found: true },
    disk: {}, memory, watcher_enabled: false,
  } as never);
  vi.spyOn(client.api, "optionsSchema").mockResolvedValue(STACK_FIELDS);
  vi.spyOn(client.api, "authStatus").mockResolvedValue(authStatus as never);
  vi.spyOn(client.api, "getSite").mockResolvedValue(site as never);
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
    // (The Automation tab opens with the redesign's hands-off cards since v0.497.0.)
    const handsOff = "How hands-off should AstroStack be?";
    expect(screen.getByText(handsOff)).toBeInTheDocument();
    expect(screen.getByText(handsOff)).not.toBeVisible();
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
    expect(screen.getByRole("slider", { name: "Lowest altitude to suggest" })).toBeVisible();
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
      expect(screen.getByLabelText(/Exact memory limit/)).toBeVisible());

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
// The conflict is reported on the offending field, and that field now exists in
// two places: the Folders section and the "More settings" folders card (both
// edit the one form, so both must mark it). These assertions are scoped to the
// *visible* tab panel so they test the section they are about rather than
// counting how many sections render the same correct message.
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

    await waitFor(() => expect(within(screen.getByRole("tabpanel"))
      .getByText(/would sit inside the incoming folder/)).toBeVisible());
    expect(screen.getAllByRole("button", { name: "Save settings" })[0]).toBeDisabled();
  });

  it("lets go the moment the folder is moved back out", async () => {
    renderSettingsWith({}, "folders", {
      data_root: "/data", incoming_dir: "/data/incoming",
      library_root: "/data/incoming/library",
    });

    await waitFor(() => expect(within(screen.getByRole("tabpanel"))
      .getByText(/would sit inside the incoming folder/)).toBeVisible());

    fireEvent.change(screen.getByLabelText(/Library root/), {
      target: { value: "/data/library" },
    });

    await waitFor(() => expect(
      screen.queryAllByText(/would sit inside the incoming folder/)).toHaveLength(0));
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

// --- the read-only token (v0.441.0) -----------------------------------------
//
// The app's only second credential, and the whole point of it is that its limits
// can be trusted — the owner hands it to a monitoring script or an assistant. So
// what the screen *says* about it is part of the feature, not decoration.

describe("Access control — the read-only token", () => {
  function withAuth(status: Record<string, unknown>) {
    return renderSettingsWith({}, "maintenance", {}, status);
  }

  it("offers nothing to create while the app has no password", async () => {
    withAuth({ enabled: false });
    await screen.findByText(/Turn on the password above first/i);
    expect(screen.queryByRole("button", { name: /Create a token/i })).toBeNull();
    expect(screen.queryByRole("button", { name: /^Remove$/i })).toBeNull();
  });

  it("offers one once a password is set, and says what it can't do", async () => {
    withAuth({ enabled: true, username: "admin", readonly_enabled: false });
    expect(await screen.findByRole("button", { name: /Create a token/i })).toBeInTheDocument();
    expect(screen.getByText(/cannot stack/i)).toBeInTheDocument();
    expect(screen.queryByText(/Turn on the password above first/i)).toBeNull();
  });

  it("shows the token once, with the username to use it under", async () => {
    withAuth({ enabled: true, username: "admin", readonly_enabled: false });
    const mint = vi.spyOn(client.api, "mintReadonlyToken").mockResolvedValue({
      token: "tok-abc123", username: "readonly", readonly_enabled: true,
    } as never);

    fireEvent.click(await screen.findByRole("button", { name: /Create a token/i }));
    await screen.findByText("tok-abc123");
    expect(mint).toHaveBeenCalled();
    // The one warning that matters: a hash is all the server keeps.
    expect(screen.getByText(/isn't shown again/i)).toBeInTheDocument();
    // And how to actually use it — the username, and a command against a path
    // the token is allowed to read.
    expect(screen.getByText(/curl -u readonly:YOUR_TOKEN/)).toBeInTheDocument();
  });

  it("does not show a stale token next to a badge saying it was replaced", async () => {
    // Replacing revokes the old one immediately, so the old string on screen
    // would be a secret that no longer works, shown as though it does.
    withAuth({ enabled: true, username: "admin", readonly_enabled: true });
    vi.spyOn(client.api, "mintReadonlyToken").mockResolvedValue({
      token: "tok-first", username: "readonly", readonly_enabled: true,
    } as never);
    vi.spyOn(window, "confirm").mockReturnValue(true);

    fireEvent.click(await screen.findByRole("button", { name: /Replace the token/i }));
    await screen.findByText("tok-first");

    const removed = vi.spyOn(client.api, "clearReadonlyToken")
      .mockResolvedValue({ readonly_enabled: false } as never);
    fireEvent.click(screen.getByRole("button", { name: /^Remove$/i }));
    await waitFor(() => expect(removed).toHaveBeenCalled());
    await waitFor(() => expect(screen.queryByText("tok-first")).toBeNull());
  });

  it("asks before replacing a token that is already in use", async () => {
    withAuth({ enabled: true, username: "admin", readonly_enabled: true });
    const mint = vi.spyOn(client.api, "mintReadonlyToken");
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);

    fireEvent.click(await screen.findByRole("button", { name: /Replace the token/i }));
    expect(confirm).toHaveBeenCalled();
    expect(mint).not.toHaveBeenCalled();   // declined → the live token survives
  });

  it("degrades cleanly against a backend that has never heard of it", async () => {
    // `readonly_enabled` is additive, so an older backend simply omits it. That
    // has to read as "no token", not as an error or an active one.
    withAuth({ enabled: true, username: "admin" });
    expect(await screen.findByRole("button", { name: /Create a token/i })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^Remove$/i })).toBeNull();
  });
});

// --- The Memory card says which budget is actually in force ------------------
// The box shows one number and a placeholder. What decides a stack is a
// three-step precedence the browser cannot see, so the server reports it; these
// pin the two cases that change what the owner should do.

// Every assertion below that names a *number* or an advisory waits with `findBy`
// rather than reading with `getBy`. The card's own chrome ("Memory", the field)
// renders off `getSettings`/`optionsSchema`; the figures and both advisories come
// from `getSystem`. Those are separate queries, so the heading is on screen while
// the figures are still in flight, and a synchronous read after waiting only for
// the heading is a race that the CI runner lost on 2026-09-30 (run 36749881941,
// on a head whose `frontend/` bytes were identical to the one that had just
// passed). Reproduced deterministically by resolving `getSystem` 25 ms late.
describe("Settings → Stacking → Memory", () => {
  it("says a blank budget is priced against whatever RAM is free, and varies", async () => {
    renderSettingsWith({}, "stacking", {}, { enabled: false },
      { total_gb: 16, available_gb: 6, stack_budget_gb: 4.1, stack_budget_source: "available" });

    await waitFor(() =>
      expect(screen.getByRole("heading", { name: "How hard your NAS works" })).toBeVisible());
    // `findBy`, not `getBy`: the RAM figures come from `getSystem`, a *different*
    // query from the ones that render this card, so the "Memory" heading above is
    // on screen before they arrive. See the note on this describe block.
    expect(await screen.findByText(/about 4.1 GB right now/)).toBeVisible();
    expect(screen.getByText(/busy day than on a quiet one/)).toBeVisible();
  });

  it("stands the over-RAM advisory down where the env override is what runs", async () => {
    // The advisory compares the *field* against this box's RAM. With
    // ASTROSTACK_MAX_STACK_GB set, the field is not the number any stack will be
    // priced against, so warning about it sends the owner to change nothing.
    renderSettingsWith({}, "stacking", { max_stack_memory_gb: 64 }, { enabled: false },
      { total_gb: 16, available_gb: 6, stack_budget_gb: 3, stack_budget_source: "env" });

    await waitFor(() =>
      expect(screen.getByRole("heading", { name: "How hard your NAS works" })).toBeVisible());
    // Awaiting the override notice is what makes the `queryByText` below mean
    // anything: before `getSystem` resolves the advisory is absent because
    // nothing has loaded, which is not the fact this test is about.
    expect(await screen.findByText(/This field is being overridden/)).toBeVisible();
    expect(
      screen.queryByText(/Budget is higher than this machine's available RAM/),
    ).toBeNull();
  });

  it("still warns about an over-RAM budget that IS what runs", async () => {
    renderSettingsWith({}, "stacking", { max_stack_memory_gb: 64 }, { enabled: false },
      { total_gb: 16, available_gb: 6, stack_budget_gb: 64, stack_budget_source: "setting" });

    await waitFor(() =>
      expect(screen.getByRole("heading", { name: "How hard your NAS works" })).toBeVisible());
    expect(
      await screen.findByText(/Budget is higher than this machine's available RAM/),
    ).toBeVisible();
  });
});

// --- "More settings" (the redesign's first slice) ---------------------------
// The owner's words were that the old labels are "very confusing and can seem
// scary to mess with to the average person", and then: "I want the expert
// settings dumbed down so that an average user can adjust all settings as
// needed. They should be warned of any unexpected consequences." So the two
// things worth pinning are that a card is *silent* until you change it, and
// that the moment you do it says what that costs and offers the way back.

describe("More settings", () => {
  it("is a section of its own, with an address like the others", async () => {
    renderSettingsWith({}, "more");
    await waitFor(() => expect(screen.getByRole("heading", { name: "More settings" })).toBeVisible());
    // Scoped to the open tab: the cores and memory cards are also drawn on
    // Stacking's "How hard your NAS works" (v0.499.0), which stays mounted.
    const more = within(screen.getByRole("tabpanel"));
    expect(more.getByText("Where your photos and library live")).toBeVisible();
    expect(more.getByText("Memory limit for stacking")).toBeVisible();
  });

  it("prints the name each setting used to have, so it is still findable by it", async () => {
    renderSettingsWith({}, "more");
    await waitFor(() => expect(screen.getByRole("heading", { name: "More settings" })).toBeVisible());
    const more = within(screen.getByRole("tabpanel"));
    expect(more.getByText("Was: Stack memory budget (GB)")).toBeVisible();
    expect(more.getByText("Was: Quiet period (s)")).toBeVisible();
    expect(more.getByText("Was: Scan subnet (CIDR), Known device IPs, Scan interval (s)"))
      .toBeVisible();
  });

  it("says nothing alarming on an install that has changed nothing", async () => {
    renderSettingsWith({}, "more", {
      copy_to_cache: false, job_history_limit: 200, watch_quiet_period_s: 30,
      watch_poll_interval_s: 300, astap_fov_deg: 1.3, astap_timeout_s: 60,
      astap_use_solve_hints: true, astap_bootstrap_solve: false,
      cpu_workers: null, max_stack_memory_gb: null, auto_reject_on_unattended: false,
      seestar_enabled: false, seestar_control_enabled: false,
      incoming_dir: "", library_root: "", seestar_known_ips: [],
    });
    await waitFor(() => expect(screen.getByRole("heading", { name: "More settings" })).toBeVisible());
    expect(screen.queryByText("Heads up")).toBeNull();
  });

  it("warns the moment a value leaves its default, and offers the way back", async () => {
    renderSettingsWith({}, "more", { copy_to_cache: true });
    await waitFor(() => expect(screen.getByRole("heading", { name: "More settings" })).toBeVisible());

    // The warning is driven by the form buffer, which a post-render effect seeds
    // from the settings query — a beat after the heading renders. Wait for the
    // state this test is about, not just for the page to exist, or the assertion
    // races the seed (green locally, flaky under CI load).
    await waitFor(() =>
      expect(screen.getByText(/you need about as much free space again/)).toBeVisible());
    const back = screen.getByRole("button", { name: "Back to default (Off)" });
    fireEvent.click(back);

    await waitFor(() =>
      expect(screen.queryByText(/you need about as much free space again/)).toBeNull());
    expect(screen.getByLabelText("Make a working copy of each photo first"))
      .not.toBeChecked();
  });

  it("edits the same buffer as the old control, so the two can never disagree", async () => {
    // Every control here also still lives on the section it always did. Both
    // read and write the page's one shared form, which is what makes "nothing
    // was removed" safe rather than two switches arguing.
    renderSettingsWith({}, "more", { copy_to_cache: true });
    await waitFor(() => expect(screen.getByRole("heading", { name: "More settings" })).toBeVisible());
    // The old control's checked state comes from the shared form buffer, seeded
    // a beat after the heading by a post-render effect — wait for it rather than
    // racing the seed.
    await waitFor(() =>
      expect(screen.getByLabelText(/Copy frames into local cache/)).toBeChecked());

    fireEvent.click(screen.getByRole("button", { name: "Back to default (Off)" }));

    await waitFor(() =>
      expect(screen.getByLabelText(/Copy frames into local cache/)).not.toBeChecked());
  });

  it("goes back to the standard folders by clearing them, and saves the blank", async () => {
    const put = vi.spyOn(client.api, "putSettings").mockResolvedValue({} as never);
    renderSettingsWith({}, "more", { incoming_dir: "/elsewhere/incoming", library_root: "" });
    await waitFor(() => expect(screen.getByRole("heading", { name: "More settings" })).toBeVisible());

    // The off-default warning depends on the form buffer the settings query
    // seeds a beat after the heading; wait for it instead of racing the seed.
    await waitFor(() =>
      expect(screen.getByText(/your library will look empty until you move the files/))
        .toBeVisible());
    fireEvent.click(
      screen.getByRole("button", { name: "Back to default (Standard (set when installed))" }));

    await waitFor(() =>
      expect(screen.queryByText(/your library will look empty/)).toBeNull());
    fireEvent.click(screen.getAllByRole("button", { name: /Save settings/ })[0]);
    await waitFor(() => expect(put).toHaveBeenCalled());
    // The blank has to survive `dropEmptyFields` or the card's one-click way
    // back is a button that does nothing.
    expect(put.mock.calls[0][0]).toMatchObject({ incoming_dir: "" });
  });

  it("finds a card by the name it used to have", async () => {
    renderSettingsWith({}, "more");
    await waitFor(() => expect(screen.getByRole("heading", { name: "More settings" })).toBeVisible());

    fireEvent.change(screen.getByLabelText("Find a setting"), { target: { value: "CIDR" } });

    const more = within(screen.getByRole("tabpanel"));
    expect(more.getByText("How to find the Seestar")).toBeVisible();
    expect(more.queryByText("Memory limit for stacking")).toBeNull();
  });

  it("shows a stored value it has no button for, rather than overwriting it", async () => {
    renderSettingsWith({}, "more", { cpu_workers: 3 });
    await waitFor(() => expect(screen.getByRole("heading", { name: "More settings" })).toBeVisible());
    // `findBy`: the chip reads the form, which `SettingsView` seeds in an effect
    // a beat after the heading renders (the race v0.497.1 fixed for its
    // neighbours; CI lost it here once Stacking also drew this card, v0.499.0).
    const chip = await within(screen.getByRole("tabpanel"))
      .findByRole("button", { name: "Currently 3" });
    expect(chip).toBeVisible();
    expect(chip).toBeDisabled();
  });
});

describe("Settings — nothing was removed", () => {
  it("still renders every setting the page carried before the redesign", async () => {
    // The owner's one hard constraint (AGENTS.md §1): "don't get rid of
    // features, just move them to a more organized layout". `HINTS` is the
    // page's own register of every labelled setting, and `lbl()` stamps each
    // one onto the DOM — so this fails the moment a slice of the redesign
    // drops one on the floor instead of rehoming it.
    const { container } = renderSettingsWith({}, "more");
    await waitFor(() => expect(screen.getByRole("heading", { name: "More settings" })).toBeVisible());

    const missing = Object.keys(HINTS).filter((k) =>
      !container.querySelector(`[data-setting="${k}"], [data-settings~="${k}"]`));
    expect(missing).toEqual([]);
  });
});

// --- Settings redesign slice 2: hands-off cards + the six-step row (v0.497.0) --

describe("Automation — how hands-off should AstroStack be?", () => {
  // The owner's live setup (AGENTS.md §1): auto-stack and auto-edit off, the
  // rest on — exactly the middle card.
  const OWNER = {
    watcher_enabled: true, auto_ingest: true, auto_qc: true, auto_solve: true,
    auto_stack: false, auto_edit_on_autostack: false,
  };

  it("shows the owner's setup as the middle card, picked and marked as saved", async () => {
    renderSettingsWith({}, "automation", OWNER);
    const ready = await screen.findByRole("button", { name: /Get them ready/ });
    await waitFor(() => expect(ready).toHaveAttribute("aria-pressed", "true"));
    expect(within(ready).getByText("Your saved setup")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Do it all for me/ }))
      .toHaveAttribute("aria-pressed", "false");
    expect(screen.queryByTestId("hands-off-unsaved")).toBeNull();
  });

  it("previews a picked card until Save, then saves all six steps", async () => {
    const put = vi.spyOn(client.api, "putSettings").mockResolvedValue({} as never);
    renderSettingsWith({}, "automation", OWNER);
    const all = await screen.findByRole("button", { name: /Do it all for me/ });
    fireEvent.click(all);

    await waitFor(() => expect(all).toHaveAttribute("aria-pressed", "true"));
    expect(screen.getByTestId("hands-off-unsaved")).toHaveTextContent(/Not saved yet/);
    expect(screen.getByLabelText("Stack automatically")).toBeChecked();
    expect(screen.getByLabelText("Finish automatically")).toBeChecked();
    expect(put).not.toHaveBeenCalled();

    fireEvent.click(screen.getAllByRole("button", { name: "Save settings" })[0]);
    await waitFor(() => expect(put).toHaveBeenCalled());
    const patch = put.mock.calls[0][0] as Record<string, unknown>;
    for (const k of Object.keys(OWNER)) expect(patch[k]).toBe(true);
  });

  it("shows a hand-made mix as Custom, with no card picked", async () => {
    renderSettingsWith({}, "automation", { ...OWNER, auto_qc: false });
    await screen.findByTestId("hands-off-custom");
    for (const name of [/Do it all for me/, /Get them ready/, /Hands on/]) {
      expect(screen.getByRole("button", { name })).toHaveAttribute("aria-pressed", "false");
    }
  });

  it("draws the steps after a switched-off one as waiting — but not past Check", async () => {
    renderSettingsWith({}, "automation", { ...OWNER, auto_stack: true, auto_qc: false });
    const step = (field: string) =>
      document.querySelector(`li[data-setting="${field}"]`) as HTMLElement;
    await waitFor(() => expect(step("auto_qc")).toHaveAttribute("data-step-state", "manual"));
    expect(within(step("auto_qc")).getByText("You do this yourself")).toBeInTheDocument();
    // Placing and stacking run whether or not frames were checked.
    expect(step("auto_solve")).toHaveAttribute("data-step-state", "auto");
    expect(step("auto_stack")).toHaveAttribute("data-step-state", "auto");
    expect(step("auto_edit_on_autostack")).toHaveAttribute("data-step-state", "manual");

    fireEvent.click(screen.getByLabelText("Notice automatically"));
    await waitFor(() =>
      expect(within(step("auto_solve")).getByText("Waiting for an earlier step")).toBeInTheDocument());
    expect(step("auto_stack")).toHaveAttribute("data-step-state", "waiting");
  });

  it("keeps each step's old name on a Was: line", async () => {
    renderSettingsWith({}, "automation", OWNER);
    await screen.findByText("Was: Plate-solve");
    expect(screen.getByText("Was: QC")).toBeInTheDocument();
    expect(screen.getByText("Was: Auto-edit the auto-stacked master into a finished picture"))
      .toBeInTheDocument();
  });
});

// --- Settings redesign slice 3: "Leaving out bad frames" (How picky?) ----------

describe("Automation — leaving out bad frames", () => {
  const picky = () => screen.getByRole("group", { name: "How picky?" });

  it("shows grading off as Keep all, with the trail tile left out", async () => {
    renderSettingsWith({}, "automation", { auto_qc: true, auto_grade_frames: false });
    await waitFor(() =>
      expect(within(picky()).getByRole("button", { name: "Keep all" }))
        .toHaveAttribute("aria-pressed", "true"));
    expect(screen.getByTestId("picky-note")).toHaveTextContent(/No frame is left out/);
    const leftOut = [...document.querySelectorAll('[data-left-out="true"]')]
      .map((el) => el.getAttribute("data-frame-kind"));
    expect(leftOut).toEqual(["trail"]);
  });

  it("reads a stored sensitivity back as its level", async () => {
    renderSettingsWith({}, "automation",
      { auto_qc: true, auto_grade_frames: true, auto_grade_sensitivity: "aggressive" });
    await waitFor(() =>
      expect(within(picky()).getByRole("button", { name: "Strict" }))
        .toHaveAttribute("aria-pressed", "true"));
    expect(within(picky()).getByRole("button", { name: "Keep all" }))
      .toHaveAttribute("aria-pressed", "false");
  });

  it("saves a picked level as the two old fields, and Keep all leaves the sensitivity alone", async () => {
    const put = vi.spyOn(client.api, "putSettings").mockResolvedValue({} as never);
    renderSettingsWith({}, "automation",
      { auto_qc: true, auto_grade_frames: false, auto_grade_sensitivity: "balanced" });
    // Wait for the edit buffer to be seeded (auto_qc alone on reads as Custom),
    // or the seed would land after the click and overwrite it.
    await screen.findByTestId("hands-off-custom");
    const gentle = screen.getByRole("button", { name: "Gentle" });
    fireEvent.click(gentle);
    await waitFor(() => expect(gentle).toHaveAttribute("aria-pressed", "true"));
    // The illustration redraws with the choice.
    expect(document.querySelector('[data-frame-kind="cloud"]'))
      .toHaveAttribute("data-left-out", "true");
    expect(document.querySelector('[data-frame-kind="soft"]'))
      .toHaveAttribute("data-left-out", "false");

    fireEvent.click(screen.getAllByRole("button", { name: "Save settings" })[0]);
    await waitFor(() => expect(put).toHaveBeenCalled());
    let patch = put.mock.calls[0][0] as Record<string, unknown>;
    expect(patch.auto_grade_frames).toBe(true);
    expect(patch.auto_grade_sensitivity).toBe("conservative");

    fireEvent.click(screen.getByRole("button", { name: "Keep all" }));
    fireEvent.click(screen.getAllByRole("button", { name: "Save settings" })[0]);
    await waitFor(() => expect(put).toHaveBeenCalledTimes(2));
    patch = put.mock.calls[1][0] as Record<string, unknown>;
    expect(patch.auto_grade_frames).toBe(false);
    expect(patch.auto_grade_sensitivity).toBe("conservative");
  });

  it("flips the trails switch, its note and the trail tile together", async () => {
    renderSettingsWith({}, "automation", { auto_qc: true, keep_streaked_frames: false });
    await screen.findByTestId("hands-off-custom");
    const sw = await screen.findByRole("switch", { name: /Keep frames with a satellite or plane trail/ });
    await waitFor(() => expect(screen.getByTestId("trail-note")).toHaveTextContent(/^Off \(recommended\)/));
    fireEvent.click(sw);
    await waitFor(() => expect(sw).toBeChecked());
    expect(screen.getByTestId("trail-note")).toHaveTextContent(/^On:/);
    expect(document.querySelector('[data-frame-kind="trail"]'))
      .toHaveAttribute("data-left-out", "false");
  });

  it("warns when grading is on but Check is off", async () => {
    renderSettingsWith({}, "automation", { auto_qc: false, auto_grade_frames: true });
    await waitFor(() =>
      expect(screen.getByTestId("picky-waiting")).toHaveTextContent(/Check \(step 3\) is off/));
    expect(screen.getByTestId("picky-waiting")).toHaveAttribute("role", "note");
  });

  it("keeps the three old names on a Was: line, and stamps all three fields", async () => {
    renderSettingsWith({}, "automation", {});
    await screen.findByText(/Was: “Auto-grade frames after QC”, “Sensitivity”/);
    for (const k of ["auto_grade_frames", "auto_grade_sensitivity", "keep_streaked_frames"]) {
      expect(document.querySelector(`[data-setting="${k}"]`)).not.toBeNull();
    }
  });
});

// --- Settings redesign slice 4: location + horizon, the NAS bar, upkeep (v0.499.0)

describe("Observing site — where you observe from", () => {
  const PHOTOS = {
    location_source: "fits" as const, location_reason: null,
    observer: { lat_deg: 48, lon_deg: 11, elevation_m: 0 },
    from_photos: { lat_deg: 48, lon_deg: 11 }, photos_reason: "found",
  };

  it("reads it from the photos by default, and says where that is", async () => {
    renderSettingsWith({}, "observing-site", { site_lat: null, site_lon: null }, { enabled: false }, {}, PHOTOS);
    await waitFor(() => expect(screen.getByTestId("site-current"))
      .toHaveTextContent("Read from your Seestar's photos: 48.0° N, 11.0° E"));
    expect(screen.getByRole("button", { name: "Read it from my photos" }))
      .toHaveAttribute("aria-pressed", "true");
    // Nothing to type while the photos already know — the boxes stay hidden…
    expect(screen.queryByLabelText(/Latitude/)).toBeNull();
    // …but the height is used either way, so it is never hidden.
    expect(screen.getByLabelText(/Height above sea level/)).toBeVisible();
    expect(screen.getByText(/AstroStack never sends it anywhere/)).toBeVisible();
  });

  it("'Type it in' opens the boxes, and Save sends what was typed", async () => {
    const put = vi.spyOn(client.api, "putSettings").mockResolvedValue({} as never);
    renderSettingsWith({}, "observing-site",
      { site_lat: null, site_lon: null, site_elevation_m: 12 }, { enabled: false }, {}, PHOTOS);
    // Wait for a value only the seeded form has: an edit made before
    // `SettingsView`'s seed effect commits would be overwritten by it.
    await waitFor(() => expect(screen.getByLabelText(/Height above sea level/)).toHaveValue("12"));
    await waitFor(() => expect(screen.getByTestId("site-current")).toHaveTextContent(/photos/));

    fireEvent.click(screen.getByRole("button", { name: "Type it in" }));
    const lat = await screen.findByLabelText(/Latitude/);
    fireEvent.change(lat, { target: { value: "51.5" } });
    fireEvent.change(screen.getByLabelText(/Longitude/), { target: { value: "-0.1" } });
    await waitFor(() => expect(screen.getByTestId("site-current"))
      .toHaveTextContent("Typed in: 51.5° N, 0.1° W"));

    fireEvent.click(screen.getAllByRole("button", { name: "Save settings" })[0]);
    await waitFor(() => expect(put).toHaveBeenCalled());
    const patch = put.mock.calls[0][0] as Record<string, unknown>;
    expect(patch.site_lat).toBe(51.5);
    expect(patch.site_lon).toBe(-0.1);
  });

  it("'Read it from my photos' clears a typed location, previewed until Save", async () => {
    const put = vi.spyOn(client.api, "putSettings").mockResolvedValue({} as never);
    renderSettingsWith({}, "observing-site", { site_lat: 10, site_lon: 20 }, { enabled: false }, {}, PHOTOS);
    await waitFor(() => expect(screen.getByTestId("site-current"))
      .toHaveTextContent("Typed in: 10.0° N, 20.0° E"));

    fireEvent.click(screen.getByRole("button", { name: "Read it from my photos" }));
    await waitFor(() => expect(screen.getByTestId("site-current"))
      .toHaveTextContent("Read from your Seestar's photos: 48.0° N, 11.0° E"));
    expect(put).not.toHaveBeenCalled();

    fireEvent.click(screen.getAllByRole("button", { name: "Save settings" })[0]);
    await waitFor(() => expect(put).toHaveBeenCalled());
    const patch = put.mock.calls[0][0] as Record<string, unknown>;
    // `null`, not dropped: the save keeps a cleared number, so the planner
    // really does go back to the photos.
    expect(patch).toHaveProperty("site_lat", null);
    expect(patch).toHaveProperty("site_lon", null);
  });

  it("moves the lit band with the altitude slider, and saves the new floor", async () => {
    const put = vi.spyOn(client.api, "putSettings").mockResolvedValue({} as never);
    renderSettingsWith({}, "observing-site", { min_target_altitude_deg: 25 });
    const slider = await screen.findByRole("slider", { name: "Lowest altitude to suggest" });
    // 25, not the default 30, so this waits for the seeded form (see above).
    await waitFor(() =>
      expect(screen.getByText("Only suggest targets higher than 25°")).toBeVisible());
    const before = screen.getByTestId("altitude-band").getAttribute("d");

    fireEvent.keyDown(slider, { key: "ArrowRight" });
    await waitFor(() =>
      expect(screen.getByText("Only suggest targets higher than 30°")).toBeVisible());
    expect(screen.getByTestId("altitude-band").getAttribute("d")).not.toBe(before);

    fireEvent.click(screen.getAllByRole("button", { name: "Save settings" })[0]);
    await waitFor(() => expect(put).toHaveBeenCalled());
    expect((put.mock.calls[0][0] as Record<string, unknown>).min_target_altitude_deg).toBe(30);
  });
});

describe("Stacking — how hard your NAS works", () => {
  it("draws memory as other apps / room for one stack / kept free", async () => {
    renderSettingsWith({}, "stacking", {}, { enabled: false },
      { total_gb: 16, available_gb: 6, stack_budget_gb: 4.2, stack_budget_source: "available" });
    expect(await screen.findByText("Other apps on your NAS: 10 GB")).toBeVisible();
    expect(screen.getByText("Room one stack may use: 4.2 GB")).toBeVisible();
    expect(screen.getByText("Kept free: 1.8 GB")).toBeVisible();
    expect(screen.getByTestId("memory-headline")).toHaveTextContent(/^Automatic/);
  });

  it("puts the cores choice here, with its warning and way back", async () => {
    const put = vi.spyOn(client.api, "putSettings").mockResolvedValue({} as never);
    renderSettingsWith({}, "stacking", { cpu_workers: null, max_stack_memory_gb: 8 });
    const nas = within(await screen.findByTestId("nas-section"));
    // Only the seeded form says 8 GB; a click before the seed would be lost.
    await waitFor(() =>
      expect(nas.getByTestId("memory-headline")).toHaveTextContent("at most 8 GB per stack."));
    const one = await nas.findByRole("button", { name: "One" });
    fireEvent.click(one);
    await waitFor(() => expect(one).toHaveAttribute("aria-pressed", "true"));
    expect(nas.getByText(/Imports and stacks will take longer/)).toBeVisible();
    fireEvent.click(nas.getByRole("button", { name: /Back to default \(All/ }));
    await waitFor(() =>
      expect(nas.getByRole("button", { name: "All (fastest)" })).toHaveAttribute("aria-pressed", "true"));

    fireEvent.click(nas.getByRole("button", { name: "One" }));
    fireEvent.click(screen.getAllByRole("button", { name: "Save settings" })[0]);
    await waitFor(() => expect(put).toHaveBeenCalled());
    expect((put.mock.calls[0][0] as Record<string, unknown>).cpu_workers).toBe(1);
  });

  it("no longer files the cores box under Plate solving", async () => {
    renderSettingsWith({}, "plate-solving");
    await waitFor(() => expect(screen.getByLabelText(/ASTAP path/)).toBeVisible());
    expect(screen.queryByLabelText(/CPU workers/)).toBeNull();
  });
});

describe("Maintenance — updates & upkeep", () => {
  it("heads the upkeep cards with what they are for", async () => {
    renderSettingsWith({}, "maintenance");
    expect(await screen.findByRole("heading", { name: "Updates & upkeep" })).toBeVisible();
    expect(screen.getByText(/Nothing here touches your raw subs/)).toBeVisible();
    expect(screen.getByText("Reprocess everything")).toBeVisible();
  });
});
