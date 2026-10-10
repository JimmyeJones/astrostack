import { MantineProvider } from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AUTO_FEEDBACK_CHIPS, AutoFeedback, autoFeedbackGroups } from "./AutoFeedback";
import autoFeedbackCueCases from "./autoFeedbackCues.cases.json";
import * as client from "../../api/client";

/** The shared cue table, driven from both sides — see the file's own
 * `_comment` and `tests/test_auto_feedback_cues_mirror.py`. */
const CUE_CASES = autoFeedbackCueCases.cases as {
  cue: string; param: string; step: number; label: string;
}[];

function wrap(onRerun = () => {},
  scope?: { safe: string; runId: number; autoCrop?: boolean }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <MantineProvider>
      <QueryClientProvider client={qc}>
        <AutoFeedback onRerun={onRerun} safe={scope?.safe} runId={scope?.runId}
          autoCrop={scope?.autoCrop} />
      </QueryClientProvider>
    </MantineProvider>,
  );
}

afterEach(() => vi.restoreAllMocks());

describe("AutoFeedback", () => {
  it("sends the matching cue and re-runs Auto when a chip is tapped", async () => {
    vi.spyOn(client.api, "getAutoPreferences")
      .mockResolvedValue({ biases: {}, note: null, neutral: true });
    const send = vi.spyOn(client.api, "sendAutoFeedback")
      .mockResolvedValue({ biases: { brightness: 1 }, note: "Auto is running a bit brighter for you, based on your recent feedback.", neutral: false });
    const onRerun = vi.fn();

    wrap(onRerun);
    fireEvent.click(await screen.findByRole("button", { name: "Too dark" }));

    // With no run context the cue updates the global taste (no ctx argument), and
    // there is no per-run border-trim override to carry either — a tap outside the
    // editor's own switch must look exactly like an older build's.
    await waitFor(() =>
      expect(send).toHaveBeenCalledWith("too_dark", undefined, undefined));
    await waitFor(() => expect(onRerun).toHaveBeenCalled());
    // The "why" note surfaces once the profile is non-neutral.
    await screen.findByText(/running a bit brighter/);
  });

  it("says a tap changed nothing, and does not re-run Auto, when the server says so", async () => {
    // The server decides this (`editor._feedback_limit_note`) by rebuilding Auto's
    // recipe either side of the tap: on a clean deep stack — the owner's own shape
    // — Auto leaves the denoise at exactly 0, so *every* "Over-smoothed" tap is
    // inert. Answering it with "Auto will lean that way for you" and re-rendering
    // a byte-identical recipe is what this replaces.
    vi.spyOn(client.api, "getRunAutoPreferences")
      .mockResolvedValue({ biases: {}, note: null, neutral: true });
    vi.spyOn(client.api, "sendAutoFeedback").mockResolvedValue({
      biases: { denoise: -1 }, note: null, neutral: false,
      limit_note: "That didn\u2019t change this picture \u2014 Auto is already smoothing as little as it will here.",
    });
    const shown = vi.spyOn(notifications, "show");
    const onRerun = vi.fn();

    wrap(onRerun, { safe: "M31", runId: 7 });
    fireEvent.click(await screen.findByRole("button", { name: "Over-smoothed" }));

    await waitFor(() => expect(shown).toHaveBeenCalled());
    expect(shown.mock.calls[0][0].message)
      .toMatch(/already smoothing as little as it will/);
    expect(shown.mock.calls[0][0].message).not.toMatch(/lean that way/);
    // Nothing moved, so there is nothing to re-render either.
    expect(onRerun).not.toHaveBeenCalled();
  });

  it("still thanks the user, and re-runs Auto, when the tap did move something", async () => {
    // The control: an absent/null `limit_note` must leave the tap's answer exactly
    // what it has always been, so a live chip is never told it did nothing.
    vi.spyOn(client.api, "getRunAutoPreferences")
      .mockResolvedValue({ biases: {}, note: null, neutral: true });
    vi.spyOn(client.api, "sendAutoFeedback").mockResolvedValue({
      biases: { brightness: 1 }, note: null, neutral: false, limit_note: null,
    });
    const shown = vi.spyOn(notifications, "show");
    const onRerun = vi.fn();

    wrap(onRerun, { safe: "M31", runId: 7 });
    fireEvent.click(await screen.findByRole("button", { name: "Too dark" }));

    await waitFor(() => expect(onRerun).toHaveBeenCalled());
    expect(shown.mock.calls[0][0].message).toMatch(/Auto will lean that way/);
  });

  it("scopes feedback to the run's archetype when given safe/runId", async () => {
    // Two answers, because a tap re-reads the run-scoped profile (the tap can be
    // what kills a chip — see the refresh test below). The second answer is the
    // profile the POST has just written; a mock that kept returning the *pre*-tap
    // one would be describing a server that forgot the write.
    const galaxyNote = "Auto is running a bit brighter for your galaxies, based on your recent feedback.";
    const getRun = vi.spyOn(client.api, "getRunAutoPreferences")
      .mockResolvedValueOnce({ biases: {}, note: null, neutral: true })
      .mockResolvedValue({ biases: { brightness: 1 }, note: galaxyNote, neutral: false });
    const send = vi.spyOn(client.api, "sendAutoFeedback")
      .mockResolvedValue({ biases: { brightness: 1 }, note: galaxyNote, neutral: false });

    wrap(() => {}, { safe: "M31", runId: 7 });
    fireEvent.click(await screen.findByRole("button", { name: "Too dark" }));

    // The run-scoped profile is queried, and the cue carries the run context.
    // Neither carries a border-trim override here: this test sets none, so both
    // must ask for the saved setting, which is the pre-override behaviour.
    await waitFor(() => expect(getRun).toHaveBeenCalledWith("M31", 7, undefined));
    await waitFor(() =>
      expect(send)
        .toHaveBeenCalledWith("too_dark", { safe: "M31", runId: 7 }, undefined));
    // The archetype-scoped "why" note surfaces.
    await screen.findByText(/for your galaxies/);
  });

  it("carries the editor's per-run border-trim override on both requests, so the "
    + "bucket is the one Auto keys on", async () => {
    // The archetype a tap is filed under has to be the archetype `auto_recipe`
    // keys on, and with the border trim off Auto keys on the whole canvas — a
    // different archetype on a ragged mosaic (v0.492.50). The editor's per-run
    // switch reaches `…/editor/auto`, so it has to reach these two as well, or the
    // write side and the read side of the taste profile disagree again at exactly
    // the moment the owner has told Auto to leave the fringe in.
    const getRun = vi.spyOn(client.api, "getRunAutoPreferences")
      .mockResolvedValue({ biases: {}, note: null, neutral: true });
    const send = vi.spyOn(client.api, "sendAutoFeedback")
      .mockResolvedValue({ biases: { brightness: 1 }, note: "Auto is running a bit brighter for you, based on your recent feedback.", neutral: false });

    wrap(() => {}, { safe: "M31", runId: 7, autoCrop: false });
    fireEvent.click(await screen.findByRole("button", { name: "Too dark" }));

    await waitFor(() => expect(getRun).toHaveBeenCalledWith("M31", 7, false));
    await waitFor(() =>
      expect(send)
        .toHaveBeenCalledWith("too_dark", { safe: "M31", runId: 7 }, false));
  });

  it("shows the why-note and Reset only when the profile is non-neutral", async () => {
    vi.spyOn(client.api, "getAutoPreferences")
      .mockResolvedValue({ biases: { sharpen: -1 }, note: "Auto is running softer for you, based on your recent feedback.", neutral: false });
    const reset = vi.spyOn(client.api, "resetAutoPreferences")
      .mockResolvedValue({ biases: {}, note: null, neutral: true });
    const onRerun = vi.fn();

    wrap(onRerun);
    fireEvent.click(await screen.findByText("Reset"));

    await waitFor(() => expect(reset).toHaveBeenCalled());
    await waitFor(() => expect(onRerun).toHaveBeenCalled());
  });

  it("offers the bright-core pair and sends its cues", async () => {
    // "Core blown out" is the one-sided highlight-protection cue (it starts off);
    // "Core looks flat" walks it back. Both must reach the backend by their exact
    // cue keys — an unknown cue is a 422 there, so a typo here is a dead chip.
    vi.spyOn(client.api, "getAutoPreferences")
      .mockResolvedValue({ biases: {}, note: null, neutral: true });
    const send = vi.spyOn(client.api, "sendAutoFeedback")
      .mockResolvedValue({ biases: { highlights: 1 }, note: "Auto is running with the bright cores held back for you, based on your recent feedback.", neutral: false });

    wrap();
    fireEvent.click(await screen.findByRole("button", { name: "Core blown out" }));
    await waitFor(() =>
      expect(send).toHaveBeenCalledWith("core_clipped", undefined, undefined));
    await screen.findByText(/bright cores held back/);

    fireEvent.click(await screen.findByRole("button", { name: "Core looks flat" }));
    await waitFor(() =>
      expect(send).toHaveBeenCalledWith("core_flat", undefined, undefined));
  });

  it("offers the green pair and sends its cues", async () => {
    // "Too green" asks for a stronger green-cast removal; "Too magenta" eases it
    // back off — the direction this row shipped without, which left a saturated
    // green bias undoable except by discarding the whole profile. Both must
    // reach the backend by their exact cue keys (an unknown cue 422s there).
    vi.spyOn(client.api, "getAutoPreferences")
      .mockResolvedValue({ biases: {}, note: null, neutral: true });
    const send = vi.spyOn(client.api, "sendAutoFeedback")
      .mockResolvedValue({ biases: { green: -1 }, note: "Auto is running with a lighter green-cast removal for you, based on your recent feedback.", neutral: false });

    wrap();
    fireEvent.click(await screen.findByRole("button", { name: "Too green" }));
    await waitFor(() => expect(send).toHaveBeenCalledWith("too_green", undefined, undefined));

    fireEvent.click(await screen.findByRole("button", { name: "Too magenta" }));
    await waitFor(() => expect(send).toHaveBeenCalledWith("too_magenta", undefined, undefined));
    // The note for the negative green bias is a sentence the app could not say
    // before, because no cue could produce the bias it describes.
    await screen.findByText(/lighter green-cast removal/);
  });

  it("clusters the chips so the row reads as five questions, not twelve buttons", async () => {
    vi.spyOn(client.api, "getAutoPreferences")
      .mockResolvedValue({ biases: {}, note: null, neutral: true });
    wrap();
    await screen.findByRole("button", { name: "Too dark" });
    for (const heading of ["Brightness", "Sharpness", "Grain", "Colour", "Bright core"]) {
      expect(screen.getByText(heading)).toBeInTheDocument();
    }
    // Every cue still has its own tappable button — grouping hides nothing.
    for (const chip of AUTO_FEEDBACK_CHIPS) {
      expect(screen.getByRole("button", { name: chip.label })).toBeInTheDocument();
    }
  });

  it("offers no Reset link when neutral", async () => {
    vi.spyOn(client.api, "getAutoPreferences")
      .mockResolvedValue({ biases: {}, note: null, neutral: true });
    wrap();
    // Chips render, but there's no why-note/Reset for a neutral profile.
    await screen.findByRole("button", { name: "Too dark" });
    expect(screen.queryByText("Reset")).toBeNull();
  });
});

describe("autoFeedbackGroups", () => {
  it("keeps every chip exactly once, in the order they were declared", () => {
    const flat = autoFeedbackGroups().flatMap((g) => g.chips);
    expect(flat.map((c) => c.cue)).toEqual(AUTO_FEEDBACK_CHIPS.map((c) => c.cue));
  });

  it("collapses twelve buttons into a handful of clusters", () => {
    const groups = autoFeedbackGroups();
    expect(groups.length).toBeLessThanOrEqual(6);
    expect(groups.length).toBeLessThan(AUTO_FEEDBACK_CHIPS.length);
    expect(groups.map((g) => g.group)).toEqual(
      ["Brightness", "Sharpness", "Grain", "Colour", "Bright core"],
    );
  });

  it("keeps each opposing pair together, so the walk-back is never further away", () => {
    const groupOf = (cue: string) =>
      autoFeedbackGroups().find((g) => g.chips.some((c) => c.cue === cue))?.group;
    // Derived from the shared table rather than hand-kept: this list used to be
    // written out here and silently omitted the green pair, which is the pair
    // that did not exist. Every parameter now has two cues, so every parameter
    // yields exactly one pair.
    const pairs = [...new Set(CUE_CASES.map((c) => c.param))].map((param) => {
      const both = CUE_CASES.filter((c) => c.param === param);
      expect(both.map((c) => c.step).sort()).toEqual([-1, 1]);
      return both.map((c) => c.cue);
    });
    expect(pairs.length).toBeGreaterThanOrEqual(6);
    for (const [a, b] of pairs) {
      expect(groupOf(a)).toBe(groupOf(b));
      expect(groupOf(a)).toBeDefined();
    }
  });

  it("renders exactly the cues and labels of the shared table, in its order", () => {
    // The other half of the guard in `tests/test_auto_feedback_cues_mirror.py`:
    // the cue string is the wire contract, so a chip the engine does not know
    // 422s at the user and a cue with no chip is a taste they cannot express.
    // Order is pinned on this side because this is the side that renders.
    expect(AUTO_FEEDBACK_CHIPS.map((c) => [c.cue, c.label])).toEqual(
      CUE_CASES.map((c) => [c.cue, c.label]),
    );
  });

  it("explains a faded taste, including when it has faded away entirely", async () => {
    // A fully-faded profile reads as neutral, so the "why Auto shifted" note is
    // gone — the fade note is what stops that looking like a silent drift.
    vi.spyOn(client.api, "getAutoPreferences").mockResolvedValue({
      biases: {}, note: null, neutral: true,
      fade_note: "Your older feedback has faded, so Auto is back to its measured default — tap again any time to lean it back.",
    });
    wrap();
    await screen.findByText(/back to its measured default/);
    // Neutral ⇒ still no Reset link; there is nothing left to reset.
    expect(screen.queryByRole("button", { name: "Reset" })).toBeNull();
  });

  it("says nothing about fading when nothing has faded", async () => {
    vi.spyOn(client.api, "getAutoPreferences").mockResolvedValue({
      biases: { brightness: 1 }, note: "Auto is running a bit brighter for you, based on your recent feedback.",
      neutral: false, fade_note: null,
    });
    wrap();
    await screen.findByText(/running a bit brighter/);
    expect(screen.queryByText(/fading|faded/)).toBeNull();
  });

  it("marks the chips that cannot move this picture, without taking them away", async () => {
    // The server measures which chips are dead on *this* picture
    // (`editor._run_inert_cue_hints`) — the stored taste is at its limit, or the
    // value Auto measured for the image is. Marked and explained, never removed
    // or disabled: the taste profile is library-wide, so the tap still teaches
    // Auto for the owner's other targets, and the UI rule forbids taking a
    // control away in any case.
    vi.spyOn(client.api, "getRunAutoPreferences").mockResolvedValue({
      biases: {}, note: null, neutral: true,
      inert_cues: {
        over_smoothed: "Auto is already smoothing as little as it will here. Tapping still teaches Auto for your other pictures.",
        core_flat: "Auto is already leaving the bright cores alone here. Tapping still teaches Auto for your other pictures.",
      },
    });
    const send = vi.spyOn(client.api, "sendAutoFeedback")
      .mockResolvedValue({ biases: { denoise: -1 }, note: null, neutral: false });

    wrap(() => {}, { safe: "M31", runId: 7 });

    // The legend, so the dimming is explained without a hover (a tooltip is not
    // an explanation on a touch screen).
    await screen.findByText(/Faded chips can.t change this picture/);
    // Every chip is still there, and still tappable.
    const dead = await screen.findByRole("button", { name: "Over-smoothed" });
    expect(dead).not.toBeDisabled();
    fireEvent.click(dead);
    await waitFor(() =>
      expect(send).toHaveBeenCalledWith("over_smoothed", { safe: "M31", runId: 7 }, undefined));
  });

  it("says nothing about faded chips when every chip can move the picture", async () => {
    // The control: an empty/absent `inert_cues` must leave the row exactly as an
    // older build renders it — no legend, no dimming.
    vi.spyOn(client.api, "getRunAutoPreferences")
      .mockResolvedValue({ biases: {}, note: null, neutral: true, inert_cues: {} });
    wrap(() => {}, { safe: "M31", runId: 7 });
    await screen.findByRole("button", { name: "Too dark" });
    expect(screen.queryByText(/Faded chips/)).toBeNull();
  });

  it("refreshes the marks after a tap, since the tap can be what kills a chip", async () => {
    // Which chips are dead depends on the picture *and* the profile, and a tap
    // moves the profile — the third "Too dark" can be the one that takes Auto's
    // stretch target to the end of its range. The feedback POST deliberately
    // measures no picture (its response carries no marks), so the run-scoped read
    // is re-fetched instead; until it lands, the marks already on screen stay put
    // rather than blinking off and on.
    const getRun = vi.spyOn(client.api, "getRunAutoPreferences")
      .mockResolvedValueOnce({
        biases: {}, note: null, neutral: true,
        inert_cues: { core_flat: "Auto is already leaving the bright cores alone here. Tapping still teaches Auto for your other pictures." },
      })
      .mockResolvedValue({
        biases: { brightness: 3 }, note: null, neutral: false,
        inert_cues: {
          core_flat: "Auto is already leaving the bright cores alone here. Tapping still teaches Auto for your other pictures.",
          too_dark: "Auto is already lifting this picture as far as it will go. Tapping still teaches Auto for your other pictures.",
        },
      });
    vi.spyOn(client.api, "sendAutoFeedback").mockResolvedValue({
      biases: { brightness: 3 }, note: null, neutral: false,
    });

    wrap(() => {}, { safe: "M31", runId: 7 });
    fireEvent.click(await screen.findByRole("button", { name: "Too dark" }));

    await waitFor(() => expect(getRun).toHaveBeenCalledTimes(2));
    // The legend survives the POST's mark-less response rather than flickering.
    await screen.findByText(/Faded chips can.t change this picture/);
  });

  it("groups a caller's own chip list without touching the shipped one", () => {
    const before = AUTO_FEEDBACK_CHIPS.length;
    const groups = autoFeedbackGroups([
      { cue: "a", label: "A", group: "One" },
      { cue: "b", label: "B", group: "Two" },
      { cue: "c", label: "C", group: "One" },
    ]);
    expect(groups).toEqual([
      { group: "One", chips: [{ cue: "a", label: "A", group: "One" }, { cue: "c", label: "C", group: "One" }] },
      { group: "Two", chips: [{ cue: "b", label: "B", group: "Two" }] },
    ]);
    expect(AUTO_FEEDBACK_CHIPS.length).toBe(before);
  });
});
