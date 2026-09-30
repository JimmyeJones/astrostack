import { describe, expect, it } from "vitest";

import { stackBudgetNote } from "./stackBudgetNote";

describe("stackBudgetNote", () => {
  it("says the blank case is priced against whatever is free, and that it varies", () => {
    const note = stackBudgetNote({ stack_budget_gb: 4.1, stack_budget_source: "available" });
    expect(note?.tone).toBe("info");
    // The number in force…
    expect(note?.text).toContain("4.1 GB");
    // …and the consequence the placeholder never spelled out, which is the whole
    // reason this note exists: the same target can come out differently.
    expect(note?.text).toMatch(/busy day/);
    expect(note?.text).toMatch(/Put a number here/);
  });

  it("confirms a set budget is repeatable", () => {
    const note = stackBudgetNote({ stack_budget_gb: 6, stack_budget_source: "setting" });
    expect(note?.tone).toBe("info");
    expect(note?.text).toContain("6 GB");
    expect(note?.text).toMatch(/same picture every time/);
  });

  it("warns, loudly, when the env override makes the field decoration", () => {
    const note = stackBudgetNote({ stack_budget_gb: 3, stack_budget_source: "env" });
    expect(note?.tone).toBe("warning");
    expect(note?.text).toContain("ASTROSTACK_MAX_STACK_GB");
    expect(note?.text).toMatch(/ignored/);
  });

  it("explains the fallback when this box's memory can't be read", () => {
    const note = stackBudgetNote({ stack_budget_gb: 12, stack_budget_source: "fallback" });
    expect(note?.tone).toBe("info");
    expect(note?.text).toContain("12 GB");
  });

  it("says nothing on an older backend, or on a source it doesn't know", () => {
    expect(stackBudgetNote(undefined)).toBeNull();
    expect(stackBudgetNote({})).toBeNull();
    expect(stackBudgetNote({ stack_budget_gb: 8 })).toBeNull();
    expect(stackBudgetNote({ stack_budget_gb: 8, stack_budget_source: "cgroup" })).toBeNull();
    // A nonsense number is not half a sentence either.
    expect(stackBudgetNote({ stack_budget_gb: 0, stack_budget_source: "setting" })).toBeNull();
  });
});
