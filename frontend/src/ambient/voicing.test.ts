import { describe, expect, it } from "vitest";

import {
  BELL_MAX_GAP_S,
  BELL_MIN_GAP_S,
  MASTER_GAIN_CEILING,
  MIN_GAIN,
  PENTATONIC_SEMITONES,
  ROOT_DRIFT_MAX_S,
  ROOT_DRIFT_MIN_S,
  ROOT_HZ,
  bellFreqHz,
  brownNoise,
  droneVoices,
  impulseResponse,
  masterGainFor,
  nextBellGapS,
  nextRootHoldS,
  nextRootHz,
} from "./voicing";

/** A `rand` that walks a fixed list, so every "random" decision is pinned. */
function seq(values: number[]): () => number {
  let i = 0;
  return () => values[i++ % values.length];
}

describe("droneVoices", () => {
  it("stacks root, fifth, octave and twelfth over the root", () => {
    const v = droneVoices(55);
    expect(v.map((x) => Math.round(x.freqHz * 100) / 100)).toEqual([55, 82.5, 110, 165]);
  });
  it("detunes every voice so they beat instead of phase-locking", () => {
    for (const voice of droneVoices(55)) {
      expect(voice.detuneCents).not.toBe(0);
      // A few cents, not a wrong note.
      expect(Math.abs(voice.detuneCents)).toBeLessThanOrEqual(12);
    }
  });
  it("gives each voice its own swell period so the pad never pulses in step", () => {
    const periods = droneVoices(55).map((v) => v.swellPeriodS);
    expect(new Set(periods).size).toBe(periods.length);
    // Slow: this is breathing, not tremolo.
    for (const p of periods) expect(p).toBeGreaterThanOrEqual(30);
  });
  it("falls away with height, so the low root carries the chord", () => {
    const gains = droneVoices(55).map((v) => v.gain);
    for (let i = 1; i < gains.length; i++) expect(gains[i]).toBeLessThan(gains[i - 1]);
  });
});

describe("masterGainFor", () => {
  it("scales volume onto the ceiling", () => {
    expect(masterGainFor(1)).toBeCloseTo(MASTER_GAIN_CEILING, 6);
    expect(masterGainFor(0.5)).toBeCloseTo(MASTER_GAIN_CEILING / 2, 6);
  });
  it("never returns zero — an exponential ramp cannot reach it", () => {
    expect(masterGainFor(0)).toBe(MIN_GAIN);
    expect(masterGainFor(-1)).toBe(MIN_GAIN);
    expect(masterGainFor(NaN)).toBe(MIN_GAIN);
  });
  it("clamps above 1 rather than getting loud", () => {
    expect(masterGainFor(4)).toBeCloseTo(MASTER_GAIN_CEILING, 6);
  });
  it("stays a background texture even at full volume", () => {
    expect(masterGainFor(1)).toBeLessThan(0.5);
  });
});

describe("nextBellGapS", () => {
  it("spans the whole 8–25 s window and never lands on a grid", () => {
    expect(nextBellGapS(seq([0]))).toBeCloseTo(BELL_MIN_GAP_S, 6);
    expect(nextBellGapS(seq([1]))).toBeCloseTo(BELL_MAX_GAP_S, 6);
    const mid = nextBellGapS(seq([0.37]));
    expect(mid).toBeGreaterThan(BELL_MIN_GAP_S);
    expect(mid).toBeLessThan(BELL_MAX_GAP_S);
    expect(Number.isInteger(mid)).toBe(false);
  });
  it("survives an out-of-range random source", () => {
    expect(nextBellGapS(seq([-5]))).toBe(BELL_MIN_GAP_S);
    expect(nextBellGapS(seq([9]))).toBe(BELL_MAX_GAP_S);
  });
});

describe("bellFreqHz", () => {
  it("only ever picks pentatonic degrees above the root", () => {
    const root = 55;
    for (let i = 0; i <= 10; i++) {
      const f = bellFreqHz(root, seq([i / 10]));
      // Semitones above the two-octaves-up reference, rounded — must be a
      // pentatonic degree in one of the two octaves the picker spans.
      const semis = Math.round(12 * Math.log2(f / (root * 4)));
      const allowed = [
        ...PENTATONIC_SEMITONES,
        ...PENTATONIC_SEMITONES.map((s) => s + 12),
      ];
      expect(allowed).toContain(semis);
    }
  });
  it("sits clear above the pad rather than inside it", () => {
    const root = 55;
    const highestDrone = Math.max(...droneVoices(root).map((v) => v.freqHz));
    expect(bellFreqHz(root, seq([0]))).toBeGreaterThan(highestDrone);
  });
  it("never runs off the end of its pitch table", () => {
    expect(Number.isFinite(bellFreqHz(55, seq([1])))).toBe(true);
    expect(Number.isFinite(bellFreqHz(55, seq([2])))).toBe(true);
  });
});

describe("root drift", () => {
  it("holds a root for minutes, not seconds", () => {
    expect(nextRootHoldS(seq([0]))).toBe(ROOT_DRIFT_MIN_S);
    expect(nextRootHoldS(seq([1]))).toBe(ROOT_DRIFT_MAX_S);
    expect(ROOT_DRIFT_MIN_S).toBeGreaterThanOrEqual(60);
  });
  it("always moves to a different root, so a drift is audible", () => {
    for (const current of ROOT_HZ) {
      for (const r of [0, 0.5, 0.99, 1]) {
        expect(nextRootHz(current, seq([r]))).not.toBe(current);
      }
    }
  });
  it("stays within the related-roots set", () => {
    expect(ROOT_HZ).toContain(nextRootHz(ROOT_HZ[0], seq([0.9])));
  });
});

describe("impulseResponse", () => {
  it("is a decaying burst: the tail is far quieter than the head", () => {
    const ir = impulseResponse(1000, 1, seq([1]));
    expect(ir.length).toBe(1000);
    expect(Math.abs(ir[0])).toBeGreaterThan(Math.abs(ir[999]) * 10);
  });
  it("stays inside [-1, 1] so the convolver can't blow up", () => {
    const ir = impulseResponse(2000, 1, () => Math.random());
    for (const v of ir) expect(Math.abs(v)).toBeLessThanOrEqual(1);
  });
  it("never returns an empty buffer, however short the request", () => {
    expect(impulseResponse(44100, 0, seq([0.5])).length).toBe(1);
  });
});

describe("brownNoise", () => {
  it("is normalised to unit peak", () => {
    const n = brownNoise(4096, () => Math.random());
    let peak = 0;
    for (const v of n) peak = Math.max(peak, Math.abs(v));
    expect(peak).toBeCloseTo(1, 6);
  });
  it("is much darker than white noise (adjacent samples are close)", () => {
    const n = brownNoise(4096, () => Math.random());
    let diff = 0;
    for (let i = 1; i < n.length; i++) diff += Math.abs(n[i] - n[i - 1]);
    // Mean absolute step of a brown series is tiny next to its full-scale range.
    expect(diff / n.length).toBeLessThan(0.1);
  });
});
