import { describe, it, expect } from "vitest";
import { integrationReadiness, readinessColor, readinessRowHint } from "./readiness";

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
});
