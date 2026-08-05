import { describe, it, expect } from "vitest";
import { backgroundModeLabel, backgroundModeNudge } from "./backgroundModeNudge";
import type { ObjectInfo, StackOptionField } from "./api/client";

const nebula = (): ObjectInfo => ({
  id: "M42", name: "Orion Nebula", type: "nebula", constellation: "Orion",
  constellation_abbr: "Ori", ra_deg: 83.8, dec_deg: -5.4, matched_by: "name",
  size_arcmin: 85,
  background_mode_hint: { mode: "luminance", text: "…cyan cores and red halos…" },
});

// The form's defaults: the per-frame flatten is on, in per-channel mode.
const on = { background_flatten: true, background_mode: "per_channel" };

describe("backgroundModeNudge", () => {
  it("suggests the advised mode for a target the catalog flags", () => {
    expect(backgroundModeNudge(nebula(), on))
      .toEqual({ mode: "luminance", text: "…cyan cores and red halos…" });
  });

  it("says nothing without a matched target or advice", () => {
    expect(backgroundModeNudge(null, on)).toBeNull();
    expect(backgroundModeNudge(undefined, on)).toBeNull();
    expect(backgroundModeNudge({ ...nebula(), background_mode_hint: null }, on)).toBeNull();
    // An older backend omits the field entirely.
    const { background_mode_hint: _omit, ...older } = nebula();
    expect(backgroundModeNudge(older as ObjectInfo, on)).toBeNull();
  });

  it("stays silent once the form is already on the advised mode", () => {
    expect(backgroundModeNudge(nebula(), {
      background_flatten: true, background_mode: "luminance",
    })).toBeNull();
  });

  it("stays silent when the per-frame flatten is switched off entirely", () => {
    // With no flatten running, its mode changes nothing — suggesting one would
    // just be noise.
    expect(backgroundModeNudge(nebula(), {
      background_flatten: false, background_mode: "per_channel",
    })).toBeNull();
  });

  it("treats a missing mode value as not-yet-advised rather than crashing", () => {
    expect(backgroundModeNudge(nebula(), { background_flatten: true }))
      .toEqual({ mode: "luminance", text: "…cyan cores and red halos…" });
  });

  it("ignores a hint missing its mode or its reason", () => {
    for (const bad of [{ mode: "", text: "x" }, { mode: "luminance", text: "" }]) {
      expect(backgroundModeNudge({ ...nebula(), background_mode_hint: bad }, on)).toBeNull();
    }
  });
});

describe("backgroundModeLabel", () => {
  const field = {
    key: "background_mode", label: "Background mode", type: "enum", group: "advanced",
    default: "per_channel", min: null, max: null, step: null,
    options: ["per_channel", "luminance"],
    option_labels: { per_channel: "Per channel", luminance: "Luminance" },
    help: null, depends_on: "background_flatten",
  } as StackOptionField;

  it("reads the engine's own option label so the button can't drift", () => {
    expect(backgroundModeLabel("luminance", [field])).toBe("Luminance");
  });

  it("falls back to the raw value when the schema has no label for it", () => {
    expect(backgroundModeLabel("luminance", undefined)).toBe("luminance");
    expect(backgroundModeLabel("luminance", [])).toBe("luminance");
    expect(backgroundModeLabel("something_new", [field])).toBe("something_new");
  });
});
