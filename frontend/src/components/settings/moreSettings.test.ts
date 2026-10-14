import { describe, expect, it } from "vitest";
import {
  CUSTOM_CHOICE, filterMoreGroups, MORE_SETTINGS_GROUPS, moreSettingChanged,
  moreSettingDefaultLabel, moreSettingKeys, moreSettingMatches, moreSettingResetPatch,
  moreSettingWarning, type MoreCtx, type MoreSetting,
} from "./moreSettings";

const CTX: MoreCtx = { cpuCount: 8 };

const card = (id: string): MoreSetting => {
  for (const g of MORE_SETTINGS_GROUPS) {
    const found = g.items.find((d) => d.id === id);
    if (found) return found;
  }
  throw new Error(`no card ${id}`);
};

const all = (): MoreSetting[] => MORE_SETTINGS_GROUPS.flatMap((g) => g.items);

// The defaults every card measures "changed" against. These are the values in
// `webapp/config.py::Settings`, copied here on purpose: a card that warns about
// a value that *is* the default, or stays silent on one that isn't, is the one
// failure this whole section can't survive.
const DEFAULTS: Record<string, unknown> = {
  data_root: "/data", incoming_dir: "", library_root: "",
  copy_to_cache: false, job_history_limit: 200,
  watch_quiet_period_s: 30, watch_poll_interval_s: 300,
  astap_fov_deg: 1.3, astap_timeout_s: 60,
  astap_use_solve_hints: true, astap_bootstrap_solve: false,
  cpu_workers: null, max_stack_memory_gb: null, auto_reject_on_unattended: false,
  seestar_enabled: false, seestar_control_enabled: false,
  seestar_scan_subnet: "", seestar_known_ips: [], seestar_scan_interval_s: 300,
  seestar_poll_interval_s: 5,
};

describe("More settings — nothing shouts before you have changed anything", () => {
  it("warns about nothing on a settings payload that is all defaults", () => {
    for (const d of all()) {
      expect(moreSettingChanged(d, DEFAULTS, CTX), d.id).toBe(false);
      expect(moreSettingWarning(d, DEFAULTS, CTX), d.id).toBe("");
    }
  });

  it("warns about nothing while the page is still loading (an empty form)", () => {
    // The form starts `{}` and a test fixture may carry only the fields it cares
    // about. Reading an absent key as "differs from the default" would open a
    // Heads up note about a value nobody has.
    for (const d of all()) {
      expect(moreSettingChanged(d, {}, CTX), d.id).toBe(false);
    }
  });
});

describe("More settings — every card warns the moment it leaves its default", () => {
  const changedForms: Record<string, Record<string, unknown>> = {
    folders: { incoming_dir: "/mnt/other/incoming" },
    copy_to_cache: { copy_to_cache: true },
    job_history_limit: { job_history_limit: 1000 },
    watch_quiet_period_s: { watch_quiet_period_s: 10 },
    watch_poll_interval_s: { watch_poll_interval_s: 60 },
    astap_fov_deg: { astap_fov_deg: 2.1 },
    astap_timeout_s: { astap_timeout_s: 120 },
    astap_use_solve_hints: { astap_use_solve_hints: false },
    astap_bootstrap_solve: { astap_bootstrap_solve: true },
    cpu_workers: { cpu_workers: 1 },
    max_stack_memory_gb: { max_stack_memory_gb: 16 },
    auto_reject_on_unattended: { auto_reject_on_unattended: true },
    seestar_enabled: { seestar_enabled: true },
    seestar_control_enabled: { seestar_control_enabled: true },
    seestar_find: { seestar_known_ips: ["192.0.2.10"] },
  };

  it("covers every card on the page", () => {
    expect(Object.keys(changedForms).sort()).toEqual(all().map((d) => d.id).sort());
  });

  it("says something specific, and offers the way back", () => {
    for (const d of all()) {
      const form = { ...DEFAULTS, ...changedForms[d.id] };
      expect(moreSettingChanged(d, form, CTX), d.id).toBe(true);
      const warning = moreSettingWarning(d, form, CTX);
      expect(warning.length, d.id).toBeGreaterThan(40);
      expect(moreSettingDefaultLabel(d, CTX), d.id).not.toBe("");

      // Applying "Back to default" puts the card back to silent.
      const back = { ...form, ...moreSettingResetPatch(d, CTX) };
      expect(moreSettingChanged(d, back, CTX), d.id).toBe(false);
      expect(moreSettingWarning(d, back, CTX), d.id).toBe("");
    }
  });
});

describe("More settings — the warnings that depend on which way you moved", () => {
  it("tells job history's two directions apart", () => {
    const d = card("job_history_limit");
    expect(moreSettingWarning(d, { job_history_limit: 2000 }, CTX)).toMatch(/more disk/);
    expect(moreSettingWarning(d, { job_history_limit: 50 }, CTX)).toMatch(/forgotten sooner/);
  });

  it("warns about a half-copied frame only when the wait is shortened", () => {
    const d = card("watch_quiet_period_s");
    expect(moreSettingWarning(d, { watch_quiet_period_s: 10 }, CTX)).toMatch(/half-finished/);
    expect(moreSettingWarning(d, { watch_quiet_period_s: 120 }, CTX)).toMatch(/a little later/);
  });

  it("quotes the real delay when the back-up check is slowed down", () => {
    const d = card("watch_poll_interval_s");
    expect(moreSettingWarning(d, { watch_poll_interval_s: 1800 }, CTX))
      .toMatch(/up to 30 minutes/);
    expect(moreSettingWarning(d, { watch_poll_interval_s: 60 }, CTX))
      .toMatch(/more disk activity/);
  });

  it("names the three-attempt ladder when the solve timeout is raised", () => {
    // `astap_timeout_s` is per *attempt* and the runner tries up to three
    // strategies, so the number a cloudy night actually costs is 3x the slider.
    const d = card("astap_timeout_s");
    expect(moreSettingWarning(d, { astap_timeout_s: 120 }, CTX)).toMatch(/about 360 seconds/);
    expect(moreSettingWarning(d, { astap_timeout_s: 20 }, CTX)).toMatch(/left out of/);
  });
});

describe("More settings — a control with fewer choices than its field still shows the truth", () => {
  it("maps the cores choice to All / Half / One on this box", () => {
    const d = card("cpu_workers");
    expect(d.kind).toBe("choice");
    if (d.kind !== "choice") return;
    expect(d.selected({ cpu_workers: null }, CTX)).toBe("all");
    expect(d.selected({ cpu_workers: 4 }, CTX)).toBe("half");
    expect(d.selected({ cpu_workers: 1 }, CTX)).toBe("one");
    expect(d.choices({}, CTX).map((c) => c.id)).toEqual(["all", "half", "one"]);
  });

  it("shows — and keeps — a core count none of its buttons offers", () => {
    const d = card("cpu_workers");
    if (d.kind !== "choice") throw new Error("choice");
    expect(d.selected({ cpu_workers: 3 }, CTX)).toBe(CUSTOM_CHOICE);
    const custom = d.choices({ cpu_workers: 3 }, CTX).find((c) => c.id === CUSTOM_CHOICE);
    expect(custom?.label).toBe("Currently 3");
    // Shown, never offered: picking it would be the one way this card could
    // silently overwrite a value it has no button for.
    expect(custom?.readOnly).toBe(true);
    expect(custom?.patch).toEqual({});
  });

  it("drops the Half button on a box where it would mean the same as One", () => {
    const d = card("cpu_workers");
    if (d.kind !== "choice") throw new Error("choice");
    expect(d.choices({}, { cpuCount: 2 }).map((c) => c.id)).toEqual(["all", "one"]);
  });

  it("maps the field of view to the two Seestars and shows anything else", () => {
    const d = card("astap_fov_deg");
    if (d.kind !== "choice") throw new Error("choice");
    expect(d.selected({ astap_fov_deg: 2.1 }, CTX)).toBe("s30");
    expect(d.selected({ astap_fov_deg: 1.3 }, CTX)).toBe("s50");
    expect(d.selected({ astap_fov_deg: 1.9 }, CTX)).toBe(CUSTOM_CHOICE);
    const opts = d.choices({ astap_fov_deg: 1.9 }, CTX);
    expect(opts[opts.length - 1].label).toBe("Currently 1.9°");
  });

  it("says the field of view is only a fallback, because that is what the solver does", () => {
    // `seestack/solve/runner._fov_deg_for_frame` derives the field from every
    // frame's own FOCALLEN/XPIXSZ and only falls back to this number, so the
    // spec's "Read from my photos" is not a choice anyone can switch off — and
    // the warning must not claim that most frames go unplaced when it is wrong.
    const d = card("astap_fov_deg");
    expect(d.desc).toMatch(/works this out from each photo/);
    expect(moreSettingWarning(d, { astap_fov_deg: 2.1 }, CTX))
      .toMatch(/for a photo that doesn't say/i);
  });
});

describe("More settings — Automatic is a value, not a blank", () => {
  it("puts the memory slider at its Automatic end for a stored null", () => {
    const d = card("max_stack_memory_gb");
    if (d.kind !== "slider") throw new Error("slider");
    expect(d.value({ max_stack_memory_gb: null })).toBe(0);
    expect(d.format(0)).toMatch(/Automatic/);
    expect(d.format(16)).toBe("At most 16 GB");
  });

  it("stores Automatic as null, never as a 0 the field would refuse", () => {
    // `max_stack_memory_gb` is `float | None` with a 0.5 GB floor, so the
    // slider's left-hand end has to clear the field, not write a zero.
    const d = card("max_stack_memory_gb");
    if (d.kind !== "slider") throw new Error("slider");
    expect(d.patch(0)).toEqual({ max_stack_memory_gb: null });
    expect(d.patch(16)).toEqual({ max_stack_memory_gb: 16 });
  });
});

describe("More settings — standard folders", () => {
  it("reads as custom once either folder is set by hand", () => {
    const d = card("folders");
    if (d.kind !== "choice") throw new Error("choice");
    expect(d.selected({ incoming_dir: "", library_root: "" }, CTX)).toBe("standard");
    expect(d.selected({ library_root: "/mnt/elsewhere" }, CTX)).toBe("custom");
  });

  it("goes back to standard by clearing both folders, and never the data root", () => {
    // The data root is what the installer set and the app has no second copy of
    // it, so "Back to default" must not reach for it.
    const d = card("folders");
    expect(moreSettingResetPatch(d, CTX)).toEqual({ incoming_dir: "", library_root: "" });
  });

  it("promises your raw subs are untouched, because ingest only ever copies", () => {
    expect(moreSettingWarning(card("folders"), { incoming_dir: "/x" }, CTX))
      .toMatch(/raw\s+subs are never touched/);
  });
});

describe("Find a setting", () => {
  it("finds a card by the name it used to have", () => {
    expect(moreSettingMatches(card("seestar_find"), "CIDR")).toBe(true);
    expect(moreSettingMatches(card("watch_quiet_period_s"), "quiet period")).toBe(true);
    expect(moreSettingMatches(card("max_stack_memory_gb"), "stack memory budget")).toBe(true);
  });

  it("finds a card by its new title, its sentence, or the field's own name", () => {
    expect(moreSettingMatches(card("cpu_workers"), "cores")).toBe(true);
    expect(moreSettingMatches(card("astap_bootstrap_solve"), "faint")).toBe(true);
    expect(moreSettingMatches(card("astap_timeout_s"), "astap_timeout_s")).toBe(true);
  });

  it("needs every word, and matches nothing it should not", () => {
    expect(moreSettingMatches(card("cpu_workers"), "memory cores")).toBe(false);
    expect(moreSettingMatches(card("cpu_workers"), "drizzle")).toBe(false);
  });

  it("empties the groups that have nothing left, and keeps the lot for a blank box", () => {
    expect(filterMoreGroups(MORE_SETTINGS_GROUPS, "")).toEqual(MORE_SETTINGS_GROUPS);
    const hits = filterMoreGroups(MORE_SETTINGS_GROUPS, "telescope");
    expect(hits.length).toBeGreaterThan(0);
    expect(hits.flatMap((g) => g.items).length)
      .toBeLessThan(MORE_SETTINGS_GROUPS.flatMap((g) => g.items).length);
    expect(filterMoreGroups(MORE_SETTINGS_GROUPS, "zzzzz")).toEqual([]);
  });
});

describe("More settings — the page's own shape", () => {
  it("gives every card a title, a sentence, an old name and a badge", () => {
    for (const d of all()) {
      expect(d.title.length, d.id).toBeGreaterThan(3);
      expect(d.desc.length, d.id).toBeGreaterThan(20);
      expect(d.was.length, d.id).toBeGreaterThan(3);
      expect(d.keys.length, d.id).toBeGreaterThan(0);
    }
  });

  it("speaks plainly — no jargon outside the `Was:` line", () => {
    // The owner's words were that the old terms "can seem scary"; the spec bans
    // these from the page's own copy and keeps them only as the old name.
    const jargon = /\b(QC|ASTAP|FOV|CIDR|pixfrac|poll interval)\b/i;
    for (const d of all()) {
      expect(`${d.title} ${d.desc}`, d.id).not.toMatch(jargon);
    }
  });

  it("names every settings field it can write, for the drift test to check", () => {
    expect(moreSettingKeys()).toEqual([
      "astap_bootstrap_solve", "astap_fov_deg", "astap_timeout_s", "astap_use_solve_hints",
      "auto_reject_on_unattended", "copy_to_cache", "cpu_workers", "data_root",
      "incoming_dir", "job_history_limit", "library_root", "max_stack_memory_gb",
      "seestar_control_enabled", "seestar_enabled", "seestar_known_ips",
      "seestar_poll_interval_s", "seestar_scan_interval_s", "seestar_scan_subnet",
      "watch_poll_interval_s", "watch_quiet_period_s",
    ]);
  });
});
