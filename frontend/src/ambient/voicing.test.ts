import { describe, expect, it } from "vitest";

import {
  BEATS_PER_BAR,
  BELL_MAX_GAP_S,
  BELL_MIN_GAP_S,
  DORIAN_COLOUR_SEMITONES,
  MACRO_DENSITY_FLOOR,
  MACRO_PERIOD_S,
  MASTER_GAIN_CEILING,
  MINOR_PENTATONIC_SEMITONES,
  MIN_GAIN,
  PLUCK_PROBABILITY,
  ROOT_DRIFT_MAX_S,
  ROOT_DRIFT_MIN_S,
  ROOT_HZ,
  TEMPO_BPM,
  barSeconds,
  beatSeconds,
  bellFreqHz,
  brownNoise,
  dottedEighthSeconds,
  droneVoices,
  impulseResponse,
  macroFilterHz,
  macroLevelAt,
  macroPluckDensity,
  masterGainFor,
  nextBellGapS,
  nextRootHoldS,
  nextRootHz,
  pluckFreqHz,
  scaleDegreeSemitones,
  shouldPluckOnBeat,
  subPulseGainForBeat,
} from "./voicing";

/** Every pitch the bed is allowed to reach for, in one octave. */
const SCALE = [...MINOR_PENTATONIC_SEMITONES, ...DORIAN_COLOUR_SEMITONES];

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
  it("is built from detuned pairs, so the pad is warm rather than pure", () => {
    for (const voice of droneVoices(55)) {
      expect(voice.pairDetuneCents).toBeGreaterThan(0);
      // Chorus, not a wrong note: the pair must stay well inside a semitone.
      expect(voice.pairDetuneCents).toBeLessThan(50);
    }
    // Most of the pad is sawtooth now — sines have no harmonics for the
    // lowpass to shape, which is what made the old bed read as a test tone.
    expect(droneVoices(55).filter((v) => v.type === "sawtooth").length)
      .toBeGreaterThanOrEqual(3);
  });
  it("spreads across the stereo field but keeps the bottom end centred", () => {
    const v = droneVoices(55);
    const pans = v.map((x) => x.pan);
    expect(new Set(pans).size).toBe(pans.length);
    for (const p of pans) expect(Math.abs(p)).toBeLessThanOrEqual(1);
    // A wide sub-bass smears the mix; the root stays near the middle.
    expect(Math.abs(v[0].pan)).toBeLessThan(0.25);
    expect(Math.max(...pans.map(Math.abs))).toBeGreaterThan(0.4);
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

describe("the mode", () => {
  it("is minor, not major — the single biggest character change", () => {
    // A minor third and no major third is what makes the bed dark.
    expect(MINOR_PENTATONIC_SEMITONES).toContain(3);
    expect(MINOR_PENTATONIC_SEMITONES).not.toContain(4);
  });
  it("colours with Dorian's 9th and natural 6th rather than a flat 6th", () => {
    expect([...DORIAN_COLOUR_SEMITONES]).toEqual([2, 9]);
    // A flat 6th would tip it from spacious into mournful.
    expect(DORIAN_COLOUR_SEMITONES).not.toContain(8);
  });
  it("has no semitone clashes inside the pentatonic core", () => {
    const s = [...MINOR_PENTATONIC_SEMITONES].sort((a, b) => a - b);
    for (let i = 1; i < s.length; i++) expect(s[i] - s[i - 1]).toBeGreaterThan(1);
  });
  it("reaches for a colour tone sometimes and the pentatonic mostly", () => {
    // First draw picks the table, second picks within it.
    expect(DORIAN_COLOUR_SEMITONES).toContain(scaleDegreeSemitones(seq([0, 0])));
    expect(MINOR_PENTATONIC_SEMITONES).toContain(scaleDegreeSemitones(seq([0.9, 0])));
    let colour = 0;
    for (let i = 0; i < 100; i++) {
      const d = scaleDegreeSemitones(seq([i / 100, 0.5]));
      if ((DORIAN_COLOUR_SEMITONES as readonly number[]).includes(d)) colour++;
    }
    expect(colour).toBeGreaterThan(0);
    expect(colour).toBeLessThan(50); // the pentatonic still carries it
  });
});

describe("bellFreqHz", () => {
  it("only ever picks scale degrees above the root", () => {
    const root = 55;
    for (let i = 0; i <= 10; i++) {
      const f = bellFreqHz(root, seq([i / 10]));
      // Semitones above the two-octaves-up reference, rounded — must be a
      // scale degree in one of the two octaves the picker spans.
      const semis = Math.round(12 * Math.log2(f / (root * 4)));
      const allowed = [...SCALE, ...SCALE.map((s) => s + 12)];
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

describe("pluckFreqHz", () => {
  it("speaks in the pad's register, an octave under the bells", () => {
    const root = 55;
    for (let i = 0; i <= 10; i++) {
      const pluck = pluckFreqHz(root, seq([i / 10]));
      const semis = Math.round(12 * Math.log2(pluck / (root * 2)));
      expect([...SCALE, ...SCALE.map((s) => s + 12)]).toContain(semis);
    }
    // Same degree, one octave apart: plucks below, bells above.
    expect(pluckFreqHz(root, seq([0.5]))).toBeLessThan(bellFreqHz(root, seq([0.5])));
  });
});

describe("the tempo grid", () => {
  it("beats at a psychill heartbeat, not a dance tempo", () => {
    expect(TEMPO_BPM).toBeGreaterThanOrEqual(72);
    expect(TEMPO_BPM).toBeLessThanOrEqual(84);
    expect(beatSeconds()).toBeCloseTo(60 / TEMPO_BPM, 9);
    expect(barSeconds()).toBeCloseTo(beatSeconds() * BEATS_PER_BAR, 9);
  });

  it("delays by a dotted eighth, so repeats land between the pulses", () => {
    expect(dottedEighthSeconds()).toBeCloseTo(beatSeconds() * 0.75, 9);
    // Never on the beat — that's what stops it sounding like an echo of itself.
    expect(dottedEighthSeconds() % beatSeconds()).toBeGreaterThan(1e-6);
  });

  it("derives every grid time from the one tempo", () => {
    expect(dottedEighthSeconds(120)).toBeCloseTo(beatSeconds(120) * 0.75, 9);
    expect(beatSeconds(120)).toBe(0.5);
  });

  it("pulses the sub on the downbeat and answers softly mid-bar", () => {
    expect(subPulseGainForBeat(0)).toBe(1);
    expect(subPulseGainForBeat(2)).toBeGreaterThan(0);
    expect(subPulseGainForBeat(2)).toBeLessThan(subPulseGainForBeat(0));
    // Beats 1 and 3 stay empty: a pulse on every beat is a drum machine.
    expect(subPulseGainForBeat(1)).toBe(0);
    expect(subPulseGainForBeat(3)).toBe(0);
  });

  it("keeps the pulse on the grid however far into the session it is", () => {
    for (const bar of [1, 7, 1000]) {
      expect(subPulseGainForBeat(bar * BEATS_PER_BAR)).toBe(1);
      expect(subPulseGainForBeat(bar * BEATS_PER_BAR + 1)).toBe(0);
    }
    // …and a negative index (a clock that ran backwards) can't crash it.
    expect(subPulseGainForBeat(-4)).toBe(1);
  });
});

describe("plucks", () => {
  it("never lands on the downbeat, where the sub already is", () => {
    for (const bar of [0, 3, 25]) {
      expect(shouldPluckOnBeat(bar * BEATS_PER_BAR, seq([0]), 1)).toBe(false);
    }
  });

  it("is sparse — the delay is what fills the space, not the notes", () => {
    expect(PLUCK_PROBABILITY).toBeLessThan(0.5);
    let fired = 0;
    for (let i = 0; i < 400; i++) {
      if (shouldPluckOnBeat(i, seq([(i % 40) / 40]), 1)) fired++;
    }
    expect(fired / 400).toBeLessThan(0.35);
    expect(fired).toBeGreaterThan(0);
  });

  it("thins out when the macro arc closes, without ever stopping", () => {
    // A draw just under the full-density probability fires at density 1 and
    // not at the arc's floor.
    const r = () => PLUCK_PROBABILITY * 0.9;
    expect(shouldPluckOnBeat(1, r, 1)).toBe(true);
    expect(shouldPluckOnBeat(1, r, MACRO_DENSITY_FLOOR)).toBe(false);
    // …but a quiet enough draw still gets through at the floor.
    expect(shouldPluckOnBeat(1, () => 0, MACRO_DENSITY_FLOOR)).toBe(true);
  });
});

describe("the macro arc", () => {
  it("opens and closes over minutes, not seconds", () => {
    expect(MACRO_PERIOD_S).toBeGreaterThanOrEqual(240);
    expect(macroLevelAt(0)).toBeCloseTo(0, 9);
    expect(macroLevelAt(MACRO_PERIOD_S / 2)).toBeCloseTo(1, 9);
    expect(macroLevelAt(MACRO_PERIOD_S)).toBeCloseTo(0, 9);
  });

  it("stays inside [0, 1] and repeats, so a long session never runs away", () => {
    for (let t = 0; t < MACRO_PERIOD_S * 3; t += 7) {
      const v = macroLevelAt(t);
      expect(v).toBeGreaterThanOrEqual(0);
      expect(v).toBeLessThanOrEqual(1);
    }
    expect(macroLevelAt(MACRO_PERIOD_S * 2.25)).toBeCloseTo(macroLevelAt(MACRO_PERIOD_S * 0.25), 9);
  });

  it("has no corner — consecutive seconds never jump", () => {
    let biggest = 0;
    for (let t = 0; t < MACRO_PERIOD_S; t++) {
      biggest = Math.max(biggest, Math.abs(macroLevelAt(t + 1) - macroLevelAt(t)));
    }
    expect(biggest).toBeLessThan(0.02);
  });

  it("lifts the pad's cutoff at the top of the arc and lets it back down", () => {
    expect(macroFilterHz(MACRO_PERIOD_S / 2)).toBeGreaterThan(macroFilterHz(0));
    // Still a lowpass on a bed, not a filter sweep you'd notice.
    expect(macroFilterHz(MACRO_PERIOD_S / 2)).toBeLessThan(2000);
  });

  it("never thins the plucks to silence", () => {
    for (let t = 0; t < MACRO_PERIOD_S; t += 13) {
      expect(macroPluckDensity(t)).toBeGreaterThanOrEqual(MACRO_DENSITY_FLOOR);
      expect(macroPluckDensity(t)).toBeLessThanOrEqual(1);
    }
  });

  it("survives a nonsense clock rather than going silent", () => {
    expect(macroLevelAt(NaN)).toBe(0);
    expect(macroLevelAt(-5)).toBe(0);
    expect(Number.isFinite(macroFilterHz(NaN))).toBe(true);
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
