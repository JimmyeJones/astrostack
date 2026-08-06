import { MantineProvider } from "@mantine/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AUTO_FEEDBACK_CHIPS, AutoFeedback, autoFeedbackGroups } from "./AutoFeedback";
import * as client from "../../api/client";

function wrap(onRerun = () => {}, scope?: { safe: string; runId: number }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <MantineProvider>
      <QueryClientProvider client={qc}>
        <AutoFeedback onRerun={onRerun} safe={scope?.safe} runId={scope?.runId} />
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

    // With no run context the cue updates the global taste (no ctx argument).
    await waitFor(() => expect(send).toHaveBeenCalledWith("too_dark", undefined));
    await waitFor(() => expect(onRerun).toHaveBeenCalled());
    // The "why" note surfaces once the profile is non-neutral.
    await screen.findByText(/running a bit brighter/);
  });

  it("scopes feedback to the run's archetype when given safe/runId", async () => {
    const getRun = vi.spyOn(client.api, "getRunAutoPreferences")
      .mockResolvedValue({ biases: {}, note: null, neutral: true });
    const send = vi.spyOn(client.api, "sendAutoFeedback")
      .mockResolvedValue({ biases: { brightness: 1 }, note: "Auto is running a bit brighter for your galaxies, based on your recent feedback.", neutral: false });

    wrap(() => {}, { safe: "M31", runId: 7 });
    fireEvent.click(await screen.findByRole("button", { name: "Too dark" }));

    // The run-scoped profile is queried, and the cue carries the run context.
    await waitFor(() => expect(getRun).toHaveBeenCalledWith("M31", 7));
    await waitFor(() =>
      expect(send).toHaveBeenCalledWith("too_dark", { safe: "M31", runId: 7 }));
    // The archetype-scoped "why" note surfaces.
    await screen.findByText(/for your galaxies/);
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
    await waitFor(() => expect(send).toHaveBeenCalledWith("core_clipped", undefined));
    await screen.findByText(/bright cores held back/);

    fireEvent.click(await screen.findByRole("button", { name: "Core looks flat" }));
    await waitFor(() => expect(send).toHaveBeenCalledWith("core_flat", undefined));
  });

  it("clusters the chips so the row reads as five questions, not eleven buttons", async () => {
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

  it("collapses eleven buttons into a handful of clusters", () => {
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
    for (const [a, b] of [
      ["too_dark", "too_bright"],
      ["too_soft", "over_sharpened"],
      ["too_noisy", "over_smoothed"],
      ["undersaturated", "too_saturated"],
      ["core_clipped", "core_flat"],
    ]) {
      expect(groupOf(a)).toBe(groupOf(b));
      expect(groupOf(a)).toBeDefined();
    }
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
