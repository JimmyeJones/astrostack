import { describe, expect, it } from "vitest";

import { latestStackFirst } from "./latestStack";

type Run = { id: number; n_frames_used?: number; carried_in?: boolean };

describe("latestStackFirst", () => {
  it("leaves a list with no carried runs exactly as it was", () => {
    const runs: Run[] = [{ id: 3 }, { id: 2 }, { id: 1 }];
    expect(latestStackFirst(runs)).toBe(runs);
  });

  it("puts the newest run made here ahead of a newer carried-in picture", () => {
    // The `--combine` dogfood shape: the folded-in night was stacked a few
    // seconds after the deep target's own picture.
    const runs: Run[] = [
      { id: 2, n_frames_used: 3, carried_in: true },
      { id: 1, n_frames_used: 4, carried_in: false },
    ];
    expect(latestStackFirst(runs)?.map((r) => r.id)).toEqual([1, 2]);
  });

  it("keeps the remaining runs, carried ones included, in their own order", () => {
    const runs: Run[] = [
      { id: 5, carried_in: true },
      { id: 4, carried_in: true },
      { id: 3 },
      { id: 2, carried_in: true },
      { id: 1 },
    ];
    expect(latestStackFirst(runs)?.map((r) => r.id)).toEqual([3, 5, 4, 2, 1]);
  });

  it("answers the newest run when every run was carried in", () => {
    const runs: Run[] = [{ id: 2, carried_in: true }, { id: 1, carried_in: true }];
    expect(latestStackFirst(runs)).toBe(runs);
  });

  it("a stack made after the Combine is the latest again", () => {
    const runs: Run[] = [{ id: 3 }, { id: 2, carried_in: true }, { id: 1 }];
    expect(latestStackFirst(runs)).toBe(runs);
  });

  it("degrades on an empty or missing list", () => {
    expect(latestStackFirst([])).toEqual([]);
    expect(latestStackFirst(null)).toBeUndefined();
    expect(latestStackFirst(undefined)).toBeUndefined();
  });

  it("does not mutate its input", () => {
    const runs: Run[] = [{ id: 2, carried_in: true }, { id: 1 }];
    latestStackFirst(runs);
    expect(runs.map((r) => r.id)).toEqual([2, 1]);
  });
});
