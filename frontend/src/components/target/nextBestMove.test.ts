import { describe, it, expect } from "vitest";
import {
  nextBestMove,
  LOCATE_MIN_UNSOLVED,
  SHORT_INTEGRATION_S,
  DEEP_INTEGRATION_S,
} from "./nextBestMove";

const HOUR = 60 * 60;

describe("nextBestMove", () => {
  it("returns null when nothing has been stacked yet", () => {
    expect(nextBestMove({})).toBeNull();
    expect(nextBestMove({ nFramesUsed: null })).toBeNull();
    expect(nextBestMove({ nFramesUsed: undefined })).toBeNull();
  });

  it("flags plate-solve as the top lever when a real share of subs are unsolved", () => {
    // 30 used, 30 unsolved → half the session left out.
    const tip = nextBestMove({ nFramesUsed: 30, nUnsolved: 30, integrationS: 5 * HOUR });
    expect(tip?.kind).toBe("locate");
    // Names the honest counts and points at the fix.
    expect(tip?.phrase).toContain("30 of your 60");
    expect(tip?.phrase.toLowerCase()).toContain("star database");
  });

  it("does not flag locate for just a stray unsolved sub or two", () => {
    // 40 used, 2 unsolved → below the count floor; falls through to depth advice.
    const tip = nextBestMove({ nFramesUsed: 40, nUnsolved: LOCATE_MIN_UNSOLVED - 1, integrationS: 2 * HOUR });
    expect(tip?.kind).not.toBe("locate");
  });

  it("does not flag locate when unsolved is a tiny fraction even if above the count floor", () => {
    // 100 used, 4 unsolved → 4/104 < 25%; not the top lever.
    const tip = nextBestMove({ nFramesUsed: 100, nUnsolved: 4, integrationS: 2 * HOUR });
    expect(tip?.kind).not.toBe("locate");
  });

  it("flags a thin stack (add more subs) when very few frames combined", () => {
    const single = nextBestMove({ nFramesUsed: 1 });
    expect(single?.kind).toBe("thin");
    expect(single?.phrase).toContain("1 sub");
    const thin = nextBestMove({ nFramesUsed: 3 });
    expect(thin?.kind).toBe("thin");
    expect(thin?.phrase).toContain("3 subs");
  });

  it("prioritises locate over thin when both apply", () => {
    // 3 used, 20 unsolved → thin AND mostly-unsolved; locate is the higher lever.
    const tip = nextBestMove({ nFramesUsed: 3, nUnsolved: 20 });
    expect(tip?.kind).toBe("locate");
  });

  it("advises a refocus when a healthy stack came out softer than usual", () => {
    const tip = nextBestMove({
      nFramesUsed: 40,
      integrationS: 2 * HOUR,
      softStars: { currentFwhmPx: 4.5, typicalFwhmPx: 3.0 },
    });
    expect(tip?.kind).toBe("soft");
    expect(tip?.phrase).toContain("4.5 px");
    expect(tip?.phrase).toContain("3.0 px");
    expect(tip?.phrase.toLowerCase()).toContain("refocus");
  });

  it("fires the soft rung even when integration time is unknown", () => {
    const tip = nextBestMove({
      nFramesUsed: 40,
      integrationS: null,
      softStars: { currentFwhmPx: 5.0, typicalFwhmPx: 3.0 },
    });
    expect(tip?.kind).toBe("soft");
  });

  it("prioritises locate and thin over soft-stars", () => {
    const soft = { currentFwhmPx: 5.0, typicalFwhmPx: 3.0 };
    // A thin stack that's also soft → thin outranks soft.
    expect(nextBestMove({ nFramesUsed: 2, softStars: soft })?.kind).toBe("thin");
    // Mostly-unsolved AND soft → locate is still the top lever.
    expect(nextBestMove({ nFramesUsed: 30, nUnsolved: 30, softStars: soft })?.kind).toBe("locate");
  });

  it("prefers the refocus nudge over add-time advice when both apply", () => {
    // Healthy count, under an hour, AND soft stars → soft outranks integration.
    const tip = nextBestMove({
      nFramesUsed: 40,
      integrationS: 18 * 60,
      softStars: { currentFwhmPx: 5.0, typicalFwhmPx: 3.0 },
    });
    expect(tip?.kind).toBe("soft");
  });

  it("advises more time for a healthy stack under an hour", () => {
    const tip = nextBestMove({ nFramesUsed: 40, integrationS: 18 * 60 }); // 18 min
    expect(tip?.kind).toBe("integration");
    expect(tip?.phrase).toContain("18 min so far");
  });

  it("stays silent when integration time is unknown for a healthy stack", () => {
    // No total_exposure_s → don't guess depth advice.
    expect(nextBestMove({ nFramesUsed: 40, integrationS: null })).toBeNull();
  });

  it("gives an encouraging note for a decent (1–3h) result", () => {
    const tip = nextBestMove({ nFramesUsed: 120, integrationS: 2 * HOUR });
    expect(tip?.kind).toBe("good");
    expect(tip?.phrase.toLowerCase()).toContain("solid result");
  });

  it("stays silent once a stack is genuinely deep and healthy", () => {
    expect(nextBestMove({ nFramesUsed: 300, integrationS: DEEP_INTEGRATION_S })).toBeNull();
    expect(nextBestMove({ nFramesUsed: 300, integrationS: 5 * HOUR })).toBeNull();
  });

  it("respects the ladder ordering across the boundaries", () => {
    // Just over the thin cap and just under the short-integration cap → integration.
    const tip = nextBestMove({ nFramesUsed: 5, integrationS: SHORT_INTEGRATION_S - 1 });
    expect(tip?.kind).toBe("integration");
    // At exactly the short cap → not short anymore, and below deep → good.
    const good = nextBestMove({ nFramesUsed: 50, integrationS: SHORT_INTEGRATION_S });
    expect(good?.kind).toBe("good");
  });

  it("treats a stray negative/NaN input as missing rather than erroring", () => {
    expect(nextBestMove({ nFramesUsed: -1 })).toBeNull();
    expect(nextBestMove({ nFramesUsed: 40, nUnsolved: NaN, integrationS: 2 * HOUR })?.kind).toBe("good");
  });
});
