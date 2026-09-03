import { describe, it, expect } from "vitest";
import {
  integrationReadiness,
  readinessColor,
  readinessRowBadge,
  readinessRowHint,
  noiseReductionHint,
} from "./readiness";

const H = 3600;

describe("integrationReadiness", () => {
  it("returns null when there's no integration yet", () => {
    expect(integrationReadiness(0, "galaxy")).toBeNull();
    expect(integrationReadiness(-10, "galaxy")).toBeNull();
    expect(integrationReadiness(NaN, "galaxy")).toBeNull();
  });

  it("scores against a per-object-type goal (galaxy 6 h, cluster 1.5 h)", () => {
    const galaxy = integrationReadiness(1.8 * H, "galaxy");
    expect(galaxy?.goalHours).toBe(6);
    expect(galaxy?.hours).toBeCloseTo(1.8, 5);
    expect(galaxy?.fraction).toBeCloseTo(0.3, 5);
    expect(galaxy?.level).toBe("solid");

    // 1 h on a 1.5 h cluster goal is a bigger fraction than the same hour on a
    // galaxy — the goal, not the raw time, drives the verdict.
    const cluster = integrationReadiness(1 * H, "open cluster");
    expect(cluster?.goalHours).toBe(1.5);
    expect(cluster?.level).toBe("solid");
  });

  it("walks through the four levels as the fraction grows", () => {
    // Galaxy goal = 6 h.
    expect(integrationReadiness(1 * H, "galaxy")?.level).toBe("starting"); // 0.17
    expect(integrationReadiness(3 * H, "galaxy")?.level).toBe("solid"); // 0.5
    expect(integrationReadiness(5 * H, "galaxy")?.level).toBe("close"); // 0.83
    expect(integrationReadiness(7 * H, "galaxy")?.level).toBe("plenty"); // 1.17
  });

  it("clamps the progress fraction to [0, 1] even when well past the goal", () => {
    const r = integrationReadiness(20 * H, "star cluster"); // goal 1.5 h
    expect(r?.fraction).toBe(1);
    expect(r?.level).toBe("plenty");
  });

  it("falls back to a sensible mid-range goal for an unknown type", () => {
    const r = integrationReadiness(2 * H, null);
    expect(r?.bucket).toBe("Other");
    expect(r?.goalHours).toBe(4);
    expect(r?.level).toBe("solid"); // 0.5
  });

  it("phrases a plain-language verdict, dropping the goal once there's plenty", () => {
    expect(integrationReadiness(1.8 * H, "galaxy")?.verdict).toBe(
      "1.8 h of ~6 h — a solid start — keep going to pull out fainter detail.",
    );
    // Plenty drops the "of ~N h" and just reassures.
    expect(integrationReadiness(8 * H, "galaxy")?.verdict).toBe(
      "8.0 h — plenty for a clean image of this target.",
    );
  });

  it("uses a positive user goal override instead of the per-type default", () => {
    // A galaxy defaults to 6 h; the user wants 10 h → the goal and verdict follow.
    const r = integrationReadiness(5 * H, "galaxy", 10);
    expect(r?.goalHours).toBe(10);
    expect(r?.customGoal).toBe(true);
    expect(r?.fraction).toBeCloseTo(0.5, 5);
    expect(r?.level).toBe("solid"); // 5/10 = 0.5, would be "close" at the 6 h default
    expect(r?.verdict).toContain("of ~10 h");
  });

  it("ignores a null / non-positive / non-finite goal override (keeps the default)", () => {
    for (const bad of [null, undefined, 0, -3, NaN]) {
      const r = integrationReadiness(3 * H, "galaxy", bad as number | null);
      expect(r?.goalHours).toBe(6);
      expect(r?.customGoal).toBe(false);
    }
  });

  it("marks the default goal as non-custom", () => {
    expect(integrationReadiness(3 * H, "galaxy")?.customGoal).toBe(false);
  });

  // The mosaic-scaling case — the "fourth wrong-denominator" bug. A per-type
  // goal is a per-pixel depth, so on a mosaic it has to be multiplied by the
  // number of single-frame field-fulls the target's canvas covers; otherwise a
  // four-panel mosaic at 1 h/panel reads as "plenty" at a quarter of the light
  // it needs, and the Tonight planner tells the owner to shoot something else.
  describe("scales the per-type goal by the target's field-fulls of sky", () => {
    it("keeps a single-field verdict bit-for-bit unchanged when fieldFulls=1", () => {
      const baseline = integrationReadiness(1.8 * H, "galaxy");
      const scaled = integrationReadiness(1.8 * H, "galaxy", null, 1);
      expect(scaled).toEqual(baseline);
      // And absent/null/nonsense all reduce to the same "single field"
      // behaviour, so an older backend or a target with no stack is safe.
      for (const noScale of [null, undefined, NaN, Infinity, 0, -1, 0.5]) {
        const r = integrationReadiness(
          1.8 * H, "galaxy", null, noScale as number | null);
        expect(r?.goalHours).toBe(baseline?.goalHours);
        expect(r?.fieldFulls).toBe(1);
      }
    });

    it("scales a four-panel mosaic's galaxy goal by 4 (6 h → 24 h)", () => {
      const r = integrationReadiness(6 * H, "galaxy", null, 4);
      expect(r?.baseGoalHours).toBe(6);
      expect(r?.goalHours).toBe(24);
      expect(r?.fieldFulls).toBe(4);
      // 6 h of 24 h = 0.25 — a quarter done, and demonstrably *not* "plenty".
      expect(r?.fraction).toBeCloseTo(0.25, 5);
      expect(r?.level).not.toBe("plenty");
    });

    it("stops the wrong 'plenty' verdict on a mosaic at a quarter of the light", () => {
      // The canonical bug: 4 h totalled, 1 h per panel, on a 4-h nebula goal.
      // Today's un-scaled code would call it "plenty" and the planner would
      // say "try something new" while each panel is a quarter done.
      const un = integrationReadiness(4 * H, "nebula");
      expect(un?.level).toBe("plenty"); // documents the shape of the bug
      const r = integrationReadiness(4 * H, "nebula", null, 4);
      expect(r?.goalHours).toBe(16); // 4 h × 4 panels
      expect(r?.level).not.toBe("plenty"); // 4 / 16 = 0.25 — a quarter done
      expect(r?.verdict).toContain("of ~16 h");
    });

    it("does NOT scale a user-set goal — a hand-set number is a decision", () => {
      // An owner who says "I want 12 h on M 31" is naming a whole-target
      // figure, not a per-pixel depth to re-interpret. Scaling it would
      // silently turn 12 h into 48 h on a 2×2 mosaic and make every custom
      // goal impossible to satisfy.
      const r = integrationReadiness(6 * H, "galaxy", 12, 4);
      expect(r?.customGoal).toBe(true);
      expect(r?.baseGoalHours).toBe(12);
      expect(r?.goalHours).toBe(12);
      expect(r?.fraction).toBeCloseTo(0.5, 5);
    });

    it("carries fieldFulls out to the caller so the UI can label the shape", () => {
      // A card that wants to write "6 h × 4 fields = 24 h" needs the number.
      const r = integrationReadiness(1 * H, "galaxy", null, 2.25);
      expect(r?.fieldFulls).toBeCloseTo(2.25, 5);
      expect(r?.goalHours).toBeCloseTo(6 * 2.25, 5);
    });
  });

  it("maps each level to a distinct progress colour", () => {
    expect(readinessColor("starting")).toBe("gray");
    expect(readinessColor("solid")).toBe("blue");
    expect(readinessColor("close")).toBe("teal");
    expect(readinessColor("plenty")).toBe("green");
  });
});

describe("readinessRowHint", () => {
  it("nudges toward something new only once close to / past the goal", () => {
    // Galaxy goal 6 h: 1 h (starting) and 3 h (solid) stay quiet — still worth
    // topping up. 5 h (close) and 7 h (plenty) nudge.
    expect(readinessRowHint(1 * H, "galaxy")).toBeNull();
    expect(readinessRowHint(3 * H, "galaxy")).toBeNull();
    expect(readinessRowHint(5 * H, "galaxy")).toEqual({
      label: "Nearly there", color: "teal",
    });
    expect(readinessRowHint(7 * H, "galaxy")).toEqual({
      label: "Plenty — try something new", color: "green",
    });
  });

  it("returns null when there's no integration", () => {
    expect(readinessRowHint(0, "galaxy")).toBeNull();
  });

  it("honours a user-set goal, so the planner can't contradict the Target page", () => {
    // 7 h on a galaxy is "plenty" against the 6 h type default — but an owner who
    // set a 12 h goal has said they want more, and the row must not tell them to
    // move on. (The Target page and the Dashboard card already read it this way.)
    expect(readinessRowHint(7 * H, "galaxy")).toEqual({
      label: "Plenty — try something new", color: "green",
    });
    expect(readinessRowHint(7 * H, "galaxy", 12)).toBeNull();

    // ...and the other direction: a modest goal the owner set means a target the
    // default would still nag them to top up is genuinely finished.
    expect(readinessRowHint(3 * H, "galaxy")).toBeNull();
    expect(readinessRowHint(3 * H, "galaxy", 2)).toEqual({
      label: "Plenty — try something new", color: "green",
    });
  });

  it("ignores an absent or nonsensical goal, falling back to the type default", () => {
    for (const bad of [null, undefined, 0, -5, NaN]) {
      expect(readinessRowHint(7 * H, "galaxy", bad as number | null)).toEqual({
        label: "Plenty — try something new", color: "green",
      });
    }
  });

  it("stops telling a mosaic owner to shoot something else at a quarter done", () => {
    // The canonical bug shape, on the planner: 4 h totalled, 1 h per panel,
    // 4 h nebula goal. Un-scaled: "Plenty — try something new" is what the
    // owner reads on the night they are choosing where to point.
    expect(readinessRowHint(4 * H, "nebula")).toEqual({
      label: "Plenty — try something new", color: "green",
    });
    // With field_fulls=4 the row goes quiet — 4 h of a 16 h scaled goal is
    // "starting", which the row deliberately says nothing about (the row's
    // integration figure already implies "keep going").
    expect(readinessRowHint(4 * H, "nebula", null, 4)).toBeNull();
  });
});

describe("readinessRowBadge", () => {
  it("prefers the owner's own pace over the vague readiness word", () => {
    // Galaxy goal 6 h, 5 h shot → a 1 h gap. At 2 h of kept subs a clear night
    // that's a single night, and saying so beats "Nearly there" at the moment
    // the user is choosing what to point at.
    expect(readinessRowBadge(5 * H, "galaxy", null, 2 * H)).toMatchObject({
      label: "~1 more night", color: "teal",
    });
    // A 3 h gap at 1.5 h a night → 2 nights, pluralised.
    expect(readinessRowBadge(3 * H, "galaxy", null, 1.5 * H)).toMatchObject({
      label: "~2 more nights", color: "teal",
    });
  });

  it("explains the chip on hover, so three terse words aren't the whole story", () => {
    // The tooltip has to answer "of what, toward what?": where the pace came
    // from, and the goal it's counting toward.
    const paced = readinessRowBadge(5 * H, "galaxy", null, 2 * H);
    expect(paced!.tooltip).toContain("of ~6 h");
    expect(paced!.tooltip).toContain("At your recent pace");
    expect(paced!.tooltip).toContain("1 more clear night");
    // The fallback badges are explained too — by the same readiness verdict the
    // Target page prints, so the two screens say the same thing about the target.
    expect(readinessRowBadge(7 * H, "galaxy")!.tooltip)
      .toBe(integrationReadiness(7 * H, "galaxy")!.verdict);
    expect(readinessRowBadge(5 * H, "galaxy")!.tooltip)
      .toBe(integrationReadiness(5 * H, "galaxy")!.verdict);
  });

  it("speaks up on a row the plain hint stays silent on", () => {
    // 3 h of a 6 h galaxy goal is "solid" — the badge-only version says nothing,
    // because "keep going" is already implied by the row's integration figure.
    // A measured pace turns that silence into something actionable.
    expect(readinessRowHint(3 * H, "galaxy")).toBeNull();
    expect(readinessRowBadge(3 * H, "galaxy", null, 3 * H)).toMatchObject({
      label: "~1 more night", color: "teal",
    });
  });

  it("falls back to the plain hint, verbatim, whenever there's no number", () => {
    // No pace at all (fewer than two productive nights) — every shape of "none".
    for (const noPace of [null, undefined, 0, -1, NaN, Infinity]) {
      expect(readinessRowBadge(5 * H, "galaxy", null, noPace as number | null))
        .toMatchObject(readinessRowHint(5 * H, "galaxy")!);
      expect(readinessRowBadge(3 * H, "galaxy", null, noPace as number | null))
        .toBeNull();
    }
    // Goal already met: the "try something new" nudge is the useful thing, and a
    // nights count would be meaningless (there's no gap left to divide).
    expect(readinessRowBadge(7 * H, "galaxy", null, 2 * H)).toMatchObject({
      label: "Plenty — try something new", color: "green",
    });
    // No integration yet → nothing to say either way.
    expect(readinessRowBadge(0, "galaxy", null, 2 * H)).toBeNull();
  });

  it("stays quiet about nights on a target further out than the cap", () => {
    // 1 h of a 6 h goal at 0.5 h a night is 10 nights away. Printing that reads
    // as a scold rather than encouragement, so the row keeps its ordinary badge
    // (here: none — it's still plainly worth topping up).
    expect(readinessRowBadge(1 * H, "galaxy", null, 0.5 * H)).toBeNull();
    // The cap is 3, so 3 nights still prints and 4 doesn't. A 3 h gap at 1 h a
    // night is exactly 3; at 0.75 h a night it's 4.
    expect(readinessRowBadge(3 * H, "galaxy", null, 1 * H)).toMatchObject({
      label: "~3 more nights", color: "teal",
    });
    expect(readinessRowBadge(3 * H, "galaxy", null, 0.75 * H)).toBeNull();
  });

  it("measures the gap against the goal the owner set", () => {
    // 7 h on a galaxy is past the 6 h default → "plenty". With a 12 h goal set
    // there are 5 h to go, which at 2.5 h a night is 2 more nights — the planner
    // must answer against the user's goal, exactly as every other screen does.
    expect(readinessRowBadge(7 * H, "galaxy", null, 2.5 * H)).toMatchObject({
      label: "Plenty — try something new", color: "green",
    });
    expect(readinessRowBadge(7 * H, "galaxy", 12, 2.5 * H)).toMatchObject({
      label: "~2 more nights", color: "teal",
    });
  });

  it("measures the gap against the SCALED goal on a mosaic", () => {
    // 7 h totalled on a 2×2 nebula mosaic = 1.75 h per panel, against a
    // scaled goal of 16 h. Gap is 9 h; at 3 h a night that's 3 more nights —
    // the row now says a plan the owner can act on, where without the
    // scaling it would have said "Plenty — try something new".
    expect(readinessRowBadge(7 * H, "nebula", null, 3 * H)).toMatchObject({
      label: "Plenty — try something new", color: "green",
    });
    expect(readinessRowBadge(7 * H, "nebula", null, 3 * H, 4)).toMatchObject({
      label: "~3 more nights", color: "teal",
    });
  });
});

describe("noiseReductionHint", () => {
  it("returns null when there's no integration yet", () => {
    expect(noiseReductionHint(0)).toBeNull();
    expect(noiseReductionHint(-10)).toBeNull();
    expect(noiseReductionHint(NaN)).toBeNull();
  });

  it("reports the honest √N cut and lands in the right regime by integration", () => {
    // 0.5 h so far: one more hour trebles the total → a big drop, steep part.
    // 1 − √(1800/5400) = 1 − 0.577 ≈ 0.423 → ~42%.
    const thin = noiseReductionHint(0.5 * H);
    expect(thin).toContain("about 42% more");
    expect(thin).toContain("steep part of the curve");

    // 4 h: 1 − √(14400/18000) = 1 − 0.894 ≈ 0.106 → ~11%, diminishing returns.
    const solid = noiseReductionHint(4 * H);
    expect(solid).toContain("about 11% more");
    expect(solid).toContain("Another clear hour");
    expect(solid).toContain("diminishing returns");

    // 12 h: 1 − √(43200/46800) = 1 − 0.961 ≈ 0.039 → ~4%, past the steep part.
    const deep = noiseReductionHint(12 * H);
    expect(deep).toContain("about 4% more");
    expect(deep).toContain("well past the steep part");
  });

  it("says nothing once an extra hour rounds below 1%", () => {
    // 60 h: 1 − √(216000/219600) ≈ 0.0082 → rounds to 1% (still shown)…
    expect(noiseReductionHint(60 * H)).toContain("about 1% more");
    // …but 200 h rounds to 0% → nothing useful to add.
    expect(noiseReductionHint(200 * H)).toBeNull();
  });

  it("monotonically shrinks the quoted cut as integration grows", () => {
    const pct = (s: string | null) =>
      Number(/about (\d+)% more/.exec(s ?? "")?.[1] ?? "-1");
    const a = pct(noiseReductionHint(1 * H));
    const b = pct(noiseReductionHint(4 * H));
    const c = pct(noiseReductionHint(10 * H));
    expect(a).toBeGreaterThan(b);
    expect(b).toBeGreaterThan(c);
  });
});
