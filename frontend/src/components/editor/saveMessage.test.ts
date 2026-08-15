import { describe, expect, it } from "vitest";
import { saveRecipeMessage } from "./saveMessage";

const op = (enabled = true) => ({ enabled });

describe("saveRecipeMessage", () => {
  it("names the step that actually makes the edit the picture", () => {
    const msg = saveRecipeMessage([op()]);
    expect(msg).toMatch(/^Saved/);
    expect(msg).toContain("Export");
    // The point of the sentence: Save is not what the other screens read.
    expect(msg).toContain("everywhere else");
  });

  it("keeps the plain confirmation when the recipe was cleared", () => {
    expect(saveRecipeMessage([])).toBe("Recipe saved");
  });

  it("treats an all-disabled recipe as cleared — there is nothing to export", () => {
    expect(saveRecipeMessage([op(false), op(false)])).toBe("Recipe saved");
  });

  it("still points at Export when one op among disabled ones is live", () => {
    expect(saveRecipeMessage([op(false), op(true)])).toContain("Export");
  });
});
