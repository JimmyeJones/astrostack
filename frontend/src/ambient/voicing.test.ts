import { describe, expect, it } from "vitest";

import {
  BEATS_PER_BAR,
  BELL_MAX_GAP_S,
  BELL_MIN_GAP_S,
  CHORUS_TAPS,
  COLOUR_SEMITONES,
  DELAY_BEATS,
  DELAY_FEEDBACK,
  DORIAN_SEMITONES,
  DUCK_DEPTH,
  MACRO_LOWPASS_MAX_HZ,
  MACRO_LOWPASS_MIN_HZ,
  MACRO_PERIOD_S,
  MACRO_PLUCK_CHANCE_MAX,
  MACRO_PLUCK_CHANCE_MIN,
  MASTER_GAIN_CEILING,
  MINOR_PENTATONIC_SEMITONES,
  MIN_GAIN,
  PLUCK_SLOTS,
  ROOT_DRIFT_MAX_S,
  ROOT_DRIFT_MIN_S,
  ROOT_HZ,
  SUB_BEATS,
  SUB_GAIN,
  TEMPO_BPM,
  barPlan,
  barSeconds,
  beatSeconds,
  bellFreqHz,
  brownNoise,
  delaySeconds,
  droneVoices,
  duckEnvelope,
  impulseResponse,
  macroLevels,
  masterGainFor,
  nextBellGapS,
  nextRootHoldS,
  nextRootHz,
  pluckFreqHz,
  subVoices,
} from "./voicing";

/** A `rand` that walks a fixed list, so every "random" decision is pinned. */
function seq(values: number[]): () => number {
  let i = 0;
  return () => values[i++ % values.length];
}

describe("the tempo grid", () => {
  it("sits in the psychill 72–84 BPM window — a pulse, not a beat", () => {
    expect(TEMPO_BPM).toBeGreaterThanOrEqual(72);
    expect(TEMPO_BPM).toBeLessThanOrEqual(84);
  });
  it("derives beats and bars from the one tempo", () => {
    expect(beatSeconds(60)).toBeCloseTo(1, 9);
    expect(barSeconds(60)).toBeCloseTo(BEATS_PER_BAR, 9);
    expect(barSeconds()).toBeCloseTo(beatSeconds() * BEATS_PER_BAR, 9);
  });
  it("delays by a dotted eighth, which the pulse never lands on", () => {
    expect(DELAY_BEATS).toBeCloseTo(0.75, 9);
    expect(delaySeconds(60)).toBeCloseTo(0.75, 9);
    // The signature of the genre: the echo weaves through the grid rather than
    // doubling it, so it must not be a whole or half beat.
    expect(Number.isInteger(DELAY_BEATS * 2)).toBe(false);
    // …and it has to die away rather than build up.
    expect(DELAY_FEEDBACK).toBeGreaterThan(0);
    expect(DELAY_FEEDBACK).toBeLessThan(1);
  });
});

describe("droneVoices", () => {
  it("stacks root, fifth, octave, a minor 7th and the twelfth over the root", () => {
    const v = droneVoices(55);
    expect(v.map((x) => Math.round(x.freqHz * 10) / 10)).toEqual([55, 82.5, 110, 392, 165]);
  });
  it("is a detuned pair per voice, so the pad is wide rather than a buzz", () => {
    for (const voice of droneVoices(55)) {
      // The spread is a half-width the player mirrors: it must be positive…
      expect(voice.detuneCents).toBeGreaterThan(0);
      // …and a few cents, not a wrong note.
      expect(voice.detuneCents).toBeLessThanOrEqual(12);
    }
  });
  it("is mostly sawtooth — a sine cannot be made warm by a filter", () => {
    const types = droneVoices(55).map((v) => v.type);
    expect(types.filter((t) => t === "sawtooth").length).toBeGreaterThanOrEqual(3);
    expect(types).not.toContain("sine");
  });
  it("gives each voice its own swell period so the pad never pulses in step", () => {
    const periods = droneVoices(55).map((v) => v.swellPeriodS);
    expect(new Set(periods).size).toBe(periods.length);
    // Slow: this is breathing, not tremolo.
    for (const p of periods) expect(p).toBeGreaterThanOrEqual(30);
  });
  it("spreads across the stereo field on offset clocks, so it never swings as one", () => {
    const voices = droneVoices(55);
    const rates = voices.map((v) => v.panLfoHz);
    expect(new Set(rates).size).toBe(rates.length);
    expect(voices.some((v) => v.pan < 0)).toBe(true);
    expect(voices.some((v) => v.pan > 0)).toBe(true);
    for (const v of voices) {
      // A pan plus its drift must stay inside the field's legal range.
      expect(Math.abs(v.pan) + v.panDepth).toBeLessThanOrEqual(1);
      expect(v.panLfoHz).toBeLessThan(0.05); // drift, not a tremolo pan
    }
  });
  it("keeps the low root carrying the chord", () => {
    const gains = droneVoices(55).map((v) => v.gain);
    expect(Math.max(...gains)).toBe(gains[0]);
  });
  it("chorus taps are short, slow and panned apart", () => {
    expect(CHORUS_TAPS.length).toBe(2);
    const rates = CHORUS_TAPS.map((t) => t.lfoHz);
    expect(new Set(rates).size).toBe(rates.length);
    expect(CHORUS_TAPS[0].pan).toBeLessThan(0);
    expect(CHORUS_TAPS[1].pan).toBeGreaterThan(0);
    for (const tap of CHORUS_TAPS) {
      // Chorus territory (a few ms), not a slapback echo.
      expect(tap.delayS).toBeLessThan(0.04);
      expect(tap.depthS).toBeLessThan(tap.delayS);
    }
  });
});

describe("subVoices", () => {
  it("puts the fundamental an octave under the pad root", () => {
    const [fundamental] = subVoices(55);
    expect(fundamental.freqHz).toBeCloseTo(27.5, 9);
  });
  it("carries a quieter partner at the root, which is what a laptop plays", () => {
    const voices = subVoices(55);
    expect(voices.map((v) => v.freqHz)).toEqual([27.5, 55]);
    expect(voices[1].gain).toBeLessThan(voices[0].gain);
  });
});

describe("barPlan", () => {
  it("always lays down the heartbeat, loudest on the downbeat", () => {
    const plan = barPlan(55, 0, seq([1]));
    expect(plan.subs.map((s) => s.atBeat)).toEqual([...SUB_BEATS]);
    expect(plan.subs[0].atBeat).toBe(0);
    expect(plan.subs[0].gain).toBe(SUB_GAIN);
    expect(plan.subs[1].gain).toBeLessThan(plan.subs[0].gain);
  });
  it("stays inside the bar", () => {
    const plan = barPlan(55, 1, seq([0, 0, 0, 0, 0, 0]));
    for (const ev of [...plan.subs, ...plan.plucks]) {
      expect(ev.atBeat).toBeGreaterThanOrEqual(0);
      expect(ev.atBeat).toBeLessThan(BEATS_PER_BAR);
    }
  });
  it("fires no pluck when the arc has closed the layer down", () => {
    // First draw decides whether a pluck happens at all.
    expect(barPlan(55, 0, seq([0.9])).plucks).toHaveLength(0);
  });
  it("fires at most two — two is a phrase, three would be a melody", () => {
    for (let i = 0; i <= 20; i++) {
      const plan = barPlan(55, 1, seq([i / 20, (i * 7) % 20 / 20, 0.05, 0.3, 0.61, 0.9]));
      expect(plan.plucks.length).toBeLessThanOrEqual(2);
    }
  });
  it("never puts two plucks on the same sixteenth", () => {
    // Both plucks roll the same slot; the duplicate must be dropped, not doubled.
    const plan = barPlan(55, 1, seq([0, 0]));
    const beats = plan.plucks.map((p) => p.atBeat);
    expect(new Set(beats).size).toBe(beats.length);
  });
  it("leaves the downbeat to the sub and returns plucks in time order", () => {
    for (const slot of PLUCK_SLOTS) expect(slot).toBeGreaterThan(0);
    const plan = barPlan(55, 1, seq([0, 0.99, 0.4, 0.5, 0.05, 0.4, 0.5]));
    const beats = plan.plucks.map((p) => p.atBeat);
    expect([...beats].sort((a, b) => a - b)).toEqual(beats);
  });
  it("survives a nonsense pluck chance rather than throwing mid-bar", () => {
    expect(barPlan(55, NaN, seq([0])).plucks).toHaveLength(0);
    expect(() => barPlan(55, 5, seq([0.5]))).not.toThrow();
  });
});

describe("the mode is minor", () => {
  it("bells only ever pick minor-pentatonic degrees above the root", () => {
    const root = 55;
    for (let i = 0; i <= 10; i++) {
      const f = bellFreqHz(root, seq([i / 10]));
      const semis = Math.round(12 * Math.log2(f / (root * 4)));
      const allowed = [
        ...MINOR_PENTATONIC_SEMITONES,
        ...MINOR_PENTATONIC_SEMITONES.map((s) => s + 12),
      ];
      expect(allowed).toContain(semis);
    }
  });
  it("the pentatonic really is minor — a flat third, no major third", () => {
    expect(MINOR_PENTATONIC_SEMITONES).toContain(3);
    expect(MINOR_PENTATONIC_SEMITONES).not.toContain(4);
  });
  it("Dorian keeps the natural 6th, which is what stops it sounding mournful", () => {
    expect(DORIAN_SEMITONES).toContain(9); // natural 6th
    expect(DORIAN_SEMITONES).toContain(3); // still minor
    expect(DORIAN_SEMITONES).not.toContain(8); // …not the flat 6th
  });
  it("plucks pick Dorian degrees, with an occasional 9th/11th for colour", () => {
    const root = 55;
    const allowed = [...DORIAN_SEMITONES, ...COLOUR_SEMITONES];
    for (let i = 0; i <= 12; i++) {
      for (const colourRoll of [0.02, 0.9]) {
        const f = pluckFreqHz(root, seq([i / 12, colourRoll]));
        expect(allowed).toContain(Math.round(12 * Math.log2(f / (root * 4))));
      }
    }
  });
  it("colour tones are the exception, not the rule", () => {
    const root = 55;
    // A colour roll well above the chance must land on a plain Dorian degree.
    const plain = pluckFreqHz(root, seq([0.5, 0.95]));
    expect(DORIAN_SEMITONES).toContain(Math.round(12 * Math.log2(plain / (root * 4))));
    // …and one below it must reach above the octave.
    const colour = pluckFreqHz(root, seq([0.5, 0.0]));
    expect(Math.round(12 * Math.log2(colour / (root * 4)))).toBeGreaterThanOrEqual(12);
  });
  it("bells sit clear above the pad rather than inside it", () => {
    const root = 55;
    const highestDrone = Math.max(...droneVoices(root).map((v) => v.freqHz));
    expect(bellFreqHz(root, seq([1]))).toBeGreaterThan(highestDrone);
  });
  it("never runs off the end of a pitch table", () => {
    expect(Number.isFinite(bellFreqHz(55, seq([1])))).toBe(true);
    expect(Number.isFinite(bellFreqHz(55, seq([2])))).toBe(true);
    expect(Number.isFinite(pluckFreqHz(55, seq([1, 1])))).toBe(true);
    expect(Number.isFinite(pluckFreqHz(55, seq([2, -1])))).toBe(true);
  });
});

describe("duckEnvelope", () => {
  it("dips the pad under a full pulse and recovers to untouched", () => {
    const env = duckEnvelope(1);
    expect(env.dipTo).toBeCloseTo(1 - DUCK_DEPTH, 9);
    expect(env.attackS).toBeGreaterThan(0);
  });
  it("is breathing, not pumping — the dip is a fraction, never a gate", () => {
    expect(DUCK_DEPTH).toBeLessThanOrEqual(0.35);
    expect(duckEnvelope(1).dipTo).toBeGreaterThan(0.5);
  });
  it("scales with how hard the pulse hit, and a silent pulse leaves it alone", () => {
    expect(duckEnvelope(0.5).dipTo).toBeGreaterThan(duckEnvelope(1).dipTo);
    expect(duckEnvelope(0).dipTo).toBe(1);
  });
  it("is back up before the next pulse arrives", () => {
    const env = duckEnvelope(1);
    const gapS = beatSeconds() * (SUB_BEATS[1] - SUB_BEATS[0]);
    expect(env.attackS + env.releaseS).toBeLessThan(gapS);
  });
  it("never dips to a value an exponential ramp couldn't reach", () => {
    expect(duckEnvelope(1).dipTo).toBeGreaterThanOrEqual(MIN_GAIN);
    expect(duckEnvelope(NaN).dipTo).toBe(1);
  });
});

describe("macroLevels", () => {
  it("is a multi-minute arc, not something you can hear turning", () => {
    expect(MACRO_PERIOD_S).toBeGreaterThanOrEqual(240);
  });
  it("opens and closes over the period", () => {
    expect(macroLevels(0).openness).toBeCloseTo(0, 9);
    expect(macroLevels(MACRO_PERIOD_S / 2).openness).toBeCloseTo(1, 9);
    expect(macroLevels(MACRO_PERIOD_S).openness).toBeCloseTo(0, 9);
  });
  it("moves the filter, the noise, the plucks and the sub together", () => {
    const closed = macroLevels(0);
    const open = macroLevels(MACRO_PERIOD_S / 2);
    expect(closed.lowpassHz).toBeCloseTo(MACRO_LOWPASS_MIN_HZ, 6);
    expect(open.lowpassHz).toBeCloseTo(MACRO_LOWPASS_MAX_HZ, 6);
    expect(closed.pluckChance).toBeCloseTo(MACRO_PLUCK_CHANCE_MIN, 6);
    expect(open.pluckChance).toBeCloseTo(MACRO_PLUCK_CHANCE_MAX, 6);
    expect(open.noiseGain).toBeGreaterThan(closed.noiseGain);
    expect(open.subLevel).toBeGreaterThan(closed.subLevel);
  });
  it("has no corner to hear: neighbouring seconds are almost identical", () => {
    for (const t of [0, 37, MACRO_PERIOD_S / 2, MACRO_PERIOD_S - 1]) {
      expect(Math.abs(macroLevels(t + 1).openness - macroLevels(t).openness)).toBeLessThan(0.02);
    }
  });
  it("wraps, so an hours-long session keeps arcing", () => {
    expect(macroLevels(MACRO_PERIOD_S * 9 + 60).openness)
      .toBeCloseTo(macroLevels(60).openness, 9);
  });
  it("survives a negative or non-finite clock", () => {
    for (const t of [-5, NaN, Infinity]) {
      const m = macroLevels(t);
      expect(m.openness).toBeGreaterThanOrEqual(0);
      expect(m.openness).toBeLessThanOrEqual(1);
      expect(Number.isFinite(m.lowpassHz)).toBe(true);
    }
  });
  it("never closes the bed down to nothing", () => {
    const closed = macroLevels(0);
    expect(closed.noiseGain).toBeGreaterThan(0);
    expect(closed.pluckChance).toBeGreaterThan(0);
    expect(closed.subLevel).toBeGreaterThan(0.5);
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
  it("spans its whole window and never lands on a grid", () => {
    expect(nextBellGapS(seq([0]))).toBeCloseTo(BELL_MIN_GAP_S, 6);
    expect(nextBellGapS(seq([1]))).toBeCloseTo(BELL_MAX_GAP_S, 6);
    const mid = nextBellGapS(seq([0.37]));
    expect(mid).toBeGreaterThan(BELL_MIN_GAP_S);
    expect(mid).toBeLessThan(BELL_MAX_GAP_S);
    expect(Number.isInteger(mid)).toBe(false);
  });
  it("is rarer than a bar, so it can't read as part of the pulse", () => {
    expect(BELL_MIN_GAP_S).toBeGreaterThan(barSeconds());
  });
  it("survives an out-of-range random source", () => {
    expect(nextBellGapS(seq([-5]))).toBe(BELL_MIN_GAP_S);
    expect(nextBellGapS(seq([9]))).toBe(BELL_MAX_GAP_S);
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
