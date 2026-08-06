/** Sound design for the optional "space ambient" background bed — the pure half.
 *
 * Everything here is a *decision*: which voices make up the drone, how loud the
 * master gain should be for a given volume setting, when the next bell fires and
 * on what note, what the reverb tail looks like. Nothing in this file touches
 * the Web Audio API, so it is all directly unit-testable; `player.ts` is the
 * thin, untestable-by-nature layer that turns these numbers into nodes.
 *
 * The bed is **synthesised**, never sampled: no audio file ships in the repo or
 * is fetched at runtime (the owner's box is offline-first), and a generated bed
 * has no loop point to hear on a multi-hour session.
 */

/** Loudest the bed can ever be, at volume 1.0. Deliberately well below unity —
 * this is a background texture, not a foreground track, and it is summed from
 * several always-on voices. */
export const MASTER_GAIN_CEILING = 0.28;

/** Fade applied to every start, stop and volume change. A raw start or stop
 * clicks audibly; ~2.5 s reads as the room simply getting quieter. */
export const FADE_SECONDS = 2.5;

/** Exponential gain ramps cannot reach or pass through zero, so silence is
 * approached rather than hit. Far below audibility. */
export const MIN_GAIN = 0.0001;

/** Low roots, a whole step and a minor third apart (A1 / B1 / D2) — related
 * enough that drifting between them never sounds like a key change. */
export const ROOT_HZ = [55, 61.735, 73.416] as const;

/** How long the bed sits on one root before drifting to another. Minutes, so
 * the change is something you notice only in hindsight. */
export const ROOT_DRIFT_MIN_S = 120;
export const ROOT_DRIFT_MAX_S = 300;

/** The pad's lowpass: a slow LFO sweeps the cutoff across this band, which is
 * what stops a static chord from reading as a test tone. */
export const LOWPASS_BASE_HZ = 400;
export const LOWPASS_SWEEP_HZ = 400;
export const LOWPASS_LFO_HZ = 0.035;

/** The "solar wind" layer: brown noise through a slowly-sweeping bandpass,
 * mixed well under the pad. */
export const NOISE_GAIN = 0.05;
export const NOISE_BANDPASS_HZ = 320;
export const NOISE_SWEEP_HZ = 220;
export const NOISE_LFO_HZ = 0.017;
export const NOISE_Q = 0.7;

/** Sparse bells: one ping every 8–25 s, never on a grid. This is the layer that
 * makes it read as *space* rather than *hum*, and the one most easily overdone. */
export const BELL_MIN_GAP_S = 8;
export const BELL_MAX_GAP_S = 25;
export const BELL_GAIN = 0.09;
export const BELL_DECAY_S = 6;

/** Reverb tail length. Long enough that the bells smear into the pad. */
export const REVERB_SECONDS = 4.5;

/** Major pentatonic — no semitone clashes, so any two bells sound intentional
 * together however they overlap in the reverb tail. */
export const PENTATONIC_SEMITONES = [0, 2, 4, 7, 9] as const;

export interface DroneVoice {
  /** Base frequency in Hz (already transposed from the root). */
  freqHz: number;
  type: OscillatorType;
  /** Contribution to the pad, before the master gain. */
  gain: number;
  /** A few cents off, so voices beat slowly against each other instead of
   * phase-locking into one dead tone. */
  detuneCents: number;
  /** Independent slow amplitude swell, so the pad breathes. The periods are
   * mutually awkward numbers so the voices never re-align into a pulse. */
  swellPeriodS: number;
  /** Offset into the swell, in turns (0–1), so they don't all start together. */
  swellPhase: number;
}

/** The pad: root + fifth + octave + twelfth, each detuned and swelling on its
 * own clock. Pure — same root in, same voices out. */
export function droneVoices(rootHz: number): DroneVoice[] {
  return [
    { freqHz: rootHz, type: "sine", gain: 0.50, detuneCents: -4, swellPeriodS: 37, swellPhase: 0 },
    { freqHz: rootHz * 1.5, type: "sine", gain: 0.30, detuneCents: +6, swellPeriodS: 43, swellPhase: 0.25 },
    { freqHz: rootHz * 2, type: "triangle", gain: 0.18, detuneCents: -7, swellPeriodS: 53, swellPhase: 0.5 },
    { freqHz: rootHz * 3, type: "sine", gain: 0.09, detuneCents: +3, swellPeriodS: 61, swellPhase: 0.75 },
  ];
}

/** Master gain for a 0–1 volume setting, clamped and floored above zero so an
 * exponential ramp always has somewhere legal to go. Pure. */
export function masterGainFor(volume: number): number {
  if (!Number.isFinite(volume)) return MIN_GAIN;
  const v = Math.min(1, Math.max(0, volume));
  return Math.max(MIN_GAIN, v * MASTER_GAIN_CEILING);
}

/** Seconds until the next bell — uniform in [8, 25], never quantised. Pure
 * given `rand` (a 0–1 source), so a test can pin both ends. */
export function nextBellGapS(rand: () => number): number {
  const r = Math.min(1, Math.max(0, rand()));
  return BELL_MIN_GAP_S + r * (BELL_MAX_GAP_S - BELL_MIN_GAP_S);
}

/** A bell pitch: a pentatonic degree two or three octaves above the drone root.
 * Pure given `rand`. */
export function bellFreqHz(rootHz: number, rand: () => number): number {
  const degrees = PENTATONIC_SEMITONES.length;
  const octaves = 2;
  const slot = Math.min(degrees * octaves - 1,
                        Math.floor(Math.min(1, Math.max(0, rand())) * degrees * octaves));
  const semitone = PENTATONIC_SEMITONES[slot % degrees] + 12 * Math.floor(slot / degrees);
  // ×4 = two octaves up, so the bells sit clear of the pad rather than in it.
  return rootHz * 4 * Math.pow(2, semitone / 12);
}

/** Seconds to sit on the current root before drifting. Pure given `rand`. */
export function nextRootHoldS(rand: () => number): number {
  const r = Math.min(1, Math.max(0, rand()));
  return ROOT_DRIFT_MIN_S + r * (ROOT_DRIFT_MAX_S - ROOT_DRIFT_MIN_S);
}

/** Pick a root that isn't the one already sounding, so a "drift" always audibly
 * moves. Pure given `rand`. */
export function nextRootHz(currentHz: number, rand: () => number): number {
  const others = ROOT_HZ.filter((hz) => hz !== currentHz);
  if (!others.length) return ROOT_HZ[0];
  const i = Math.min(others.length - 1,
                     Math.floor(Math.min(1, Math.max(0, rand())) * others.length));
  return others[i];
}

/** An exponentially-decaying noise burst — the impulse response the convolver
 * uses for its tail. Generated rather than loaded, so no asset ships. Returns
 * one channel; the caller writes it into both. Pure given `rand`. */
export function impulseResponse(
  sampleRate: number,
  seconds: number,
  rand: () => number,
): Float32Array<ArrayBuffer> {
  const n = Math.max(1, Math.floor(sampleRate * seconds));
  const out = new Float32Array(n);
  for (let i = 0; i < n; i++) {
    // decay ~ e^-5t over the tail: audible for its whole length, gone by the end.
    const decay = Math.exp(-5 * (i / n));
    out[i] = (rand() * 2 - 1) * decay;
  }
  return out;
}

/** Brown (1/f²) noise for the "solar wind" layer — much darker than white, which
 * would hiss. Integrated with a leak so it can't wander off-scale, then
 * normalised. Pure given `rand`. */
export function brownNoise(length: number, rand: () => number): Float32Array<ArrayBuffer> {
  const n = Math.max(1, Math.floor(length));
  const out = new Float32Array(n);
  let last = 0;
  let peak = 0;
  for (let i = 0; i < n; i++) {
    const white = rand() * 2 - 1;
    last = (last + 0.02 * white) / 1.02;
    out[i] = last;
    const a = Math.abs(last);
    if (a > peak) peak = a;
  }
  if (peak > 0) {
    for (let i = 0; i < n; i++) out[i] /= peak;
  }
  return out;
}
