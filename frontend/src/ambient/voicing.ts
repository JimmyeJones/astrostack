/** Sound design for the optional "space ambient" background bed — the pure half.
 *
 * Everything here is a *decision*: the tempo grid, which voices make up the pad,
 * how loud the master gain should be for a given volume setting, what happens in
 * the next bar, what the reverb tail looks like. Nothing in this file touches the
 * Web Audio API, so it is all directly unit-testable; `player.ts` is the thin,
 * untestable-by-nature layer that turns these numbers into nodes.
 *
 * The bed is **synthesised**, never sampled: no audio file ships in the repo or
 * is fetched at runtime (the owner's box is offline-first), and a generated bed
 * has no loop point to hear on a multi-hour session.
 *
 * **The style is psychill / psydub, written from scratch in the genre's idiom** —
 * a slow heartbeat around 76 BPM, a warm sub under a wide detuned pad, a
 * dotted-eighth ping-pong delay doing most of the melodic work, a minor mode, and
 * a multi-minute arc so a long session goes somewhere. Nothing here reproduces or
 * approximates any existing recording: these are stylistic conventions (a tempo
 * range, a scale, a delay division), the same way "write something bluesy" names
 * a style rather than a song.
 *
 * It still has to sit *behind* an app someone is working in, so every level here
 * is chosen to be felt rather than noticed.
 */

/* ── Level and fade ─────────────────────────────────────────────────────── */

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

/* ── The grid ───────────────────────────────────────────────────────────── */

/** The bed's heartbeat. The genre lives at roughly 72–84 BPM; 76 is slow enough
 * to read as a pulse you sink into rather than a beat you tap along to. Every
 * timed decision below is derived from this one number, so the whole bed stays
 * locked to one grid. */
export const TEMPO_BPM = 76;

/** Four beats to a bar — the unit the scheduler plans in. */
export const BEATS_PER_BAR = 4;

/** Seconds per beat at a given tempo. Pure. */
export function beatSeconds(bpm: number = TEMPO_BPM): number {
  return 60 / bpm;
}

/** Seconds per bar at a given tempo. Pure. */
export function barSeconds(bpm: number = TEMPO_BPM): number {
  return beatSeconds(bpm) * BEATS_PER_BAR;
}

/* ── Mode ───────────────────────────────────────────────────────────────── */

/** Low roots, a whole step and a minor third apart (A1 / B1 / D2) — related
 * enough that drifting between them never sounds like a key change. */
export const ROOT_HZ = [55, 61.735, 73.416] as const;

/** How long the bed sits on one root before drifting to another. Minutes, so
 * the change is something you notice only in hindsight. */
export const ROOT_DRIFT_MIN_S = 120;
export const ROOT_DRIFT_MAX_S = 300;

/** How long the outgoing and incoming pads overlap on a drift. Stopping a
 * sawtooth pad on the spot is an audible click; a slow crossfade is the whole
 * reason a drift reads as the room changing rather than an edit. */
export const ROOT_CROSSFADE_S = 6;

/** Minor pentatonic — the dark counterpart of the major set this bed used to
 * use, and still gapped enough that any two notes overlapping in the reverb
 * tail sound intentional. This single change moves the character further than
 * anything else in the file. */
export const MINOR_PENTATONIC_SEMITONES = [0, 3, 5, 7, 10] as const;

/** Dorian — minor, but with a natural 6th (the 9) that keeps it spacious rather
 * than mournful. The plucks use the fuller set; the bells stay pentatonic so a
 * long tail can't land a semitone away from a pluck. */
export const DORIAN_SEMITONES = [0, 2, 3, 5, 7, 9, 10] as const;

/** Occasional colour above the octave: the 9th and the 11th. Rare on purpose —
 * they are the notes that make a minor bed sound *considered* rather than sad,
 * and constant ones would just sound unresolved. */
export const COLOUR_SEMITONES = [14, 17] as const;
export const COLOUR_CHANCE = 0.18;

/* ── The pad ────────────────────────────────────────────────────────────── */

/** The pad's lowpass: a slow LFO sweeps the cutoff across this band, which is
 * what stops a static chord from reading as a test tone. The *centre* of the
 * band is moved much more slowly still, by the macro arc below. */
export const LOWPASS_SWEEP_HZ = 400;
export const LOWPASS_LFO_HZ = 0.035;

/** The "solar wind" layer: brown noise through a slowly-sweeping bandpass,
 * mixed well under the pad. */
export const NOISE_BANDPASS_HZ = 320;
export const NOISE_SWEEP_HZ = 220;
export const NOISE_LFO_HZ = 0.017;
export const NOISE_Q = 0.7;

export interface DroneVoice {
  /** Base frequency in Hz (already transposed from the root). */
  freqHz: number;
  type: OscillatorType;
  /** Contribution to the pad, before the master gain. */
  gain: number;
  /** Half-spread of the voice's **pair** of oscillators, in cents: the player
   * places one at `-detuneCents` and one at `+detuneCents`. A pair of slightly
   * mistuned sawtooths through a lowpass is the cheap, dependency-free way to
   * get the wide "supersaw-lite" warmth the genre is built on — a single sine
   * cannot be made to sound wide however it is panned. */
  detuneCents: number;
  /** Independent slow amplitude swell, so the pad breathes. The periods are
   * mutually awkward numbers so the voices never re-align into a pulse. */
  swellPeriodS: number;
  /** Offset into the swell, in turns (0–1), so they don't all start together. */
  swellPhase: number;
  /** Where the voice sits across the stereo field, −1 (left) … +1 (right). The
   * bed used to be near-mono; the genre is very wide. */
  pan: number;
  /** Rate of that voice's slow pan drift, in Hz. Deliberately *not* shared —
   * offset rates keep the field moving without the whole pad swinging as one. */
  panLfoHz: number;
  /** How far either side of `pan` the drift reaches. */
  panDepth: number;
}

/** The pad: root + fifth + octave + twelfth, plus a quiet minor 7th for the
 * mode, each a detuned sawtooth pair swelling and drifting on its own clock.
 * Pure — same root in, same voices out. */
export function droneVoices(rootHz: number): DroneVoice[] {
  return [
    { freqHz: rootHz, type: "sawtooth", gain: 0.34, detuneCents: 5, swellPeriodS: 37, swellPhase: 0, pan: -0.25, panLfoHz: 0.019, panDepth: 0.22 },
    { freqHz: rootHz * 1.5, type: "sawtooth", gain: 0.21, detuneCents: 7, swellPeriodS: 43, swellPhase: 0.25, pan: 0.3, panLfoHz: 0.023, panDepth: 0.25 },
    { freqHz: rootHz * 2, type: "sawtooth", gain: 0.13, detuneCents: 6, swellPeriodS: 53, swellPhase: 0.5, pan: -0.45, panLfoHz: 0.014, panDepth: 0.3 },
    // The minor 7th two octaves up: the one pad voice that states the mode.
    { freqHz: rootHz * 4 * Math.pow(2, 10 / 12), type: "triangle", gain: 0.07, detuneCents: 4, swellPeriodS: 67, swellPhase: 0.65, pan: 0.5, panLfoHz: 0.029, panDepth: 0.28 },
    { freqHz: rootHz * 3, type: "sawtooth", gain: 0.06, detuneCents: 8, swellPeriodS: 61, swellPhase: 0.75, pan: 0.12, panLfoHz: 0.011, panDepth: 0.35 },
  ];
}

/** Chorus: two short modulated delay lines, panned hard apart, mixed under the
 * dry pad. Slow and shallow — this is width, not a vibrato effect. */
export const CHORUS_TAPS = [
  { delayS: 0.013, depthS: 0.0035, lfoHz: 0.11, pan: -1 },
  { delayS: 0.019, depthS: 0.0045, lfoHz: 0.17, pan: 1 },
] as const;
export const CHORUS_MIX = 0.4;

/* ── Sub-bass and the pulse ─────────────────────────────────────────────── */

/** The sub sits an octave *under* the pad root. At these roots the fundamental
 * is 27–37 Hz, which small speakers cannot reproduce at all, so it is paired
 * with a quieter partner at the root itself — that partner is what a laptop
 * actually plays, and a subwoofer gets the octave underneath it. */
export function subVoices(rootHz: number): Array<{ freqHz: number; gain: number }> {
  return [
    { freqHz: rootHz / 2, gain: 1 },
    { freqHz: rootHz, gain: 0.45 },
  ];
}

/** Which beats of the bar the sub pulses on: the downbeat, and a softer one
 * halfway through. Not a drum kit — one soft thump, low in the mix, is all it
 * takes to imply a tempo. */
export const SUB_BEATS = [0, 2] as const;
/** The half-bar pulse relative to the downbeat's. */
export const SUB_OFFBEAT_LEVEL = 0.6;
export const SUB_GAIN = 0.5;
/** Attack and decay of one pulse. Slow enough that it reads as a breath rather
 * than a kick. */
export const SUB_ATTACK_S = 0.045;
export const SUB_DECAY_S = 0.75;

export interface ScheduledSub {
  /** Beat within the bar (0-based, may be fractional). */
  atBeat: number;
  gain: number;
}

/* ── Plucks and the delay ───────────────────────────────────────────────── */

/** A dotted eighth — three quarters of a beat. Delaying by a division the pulse
 * does *not* land on is what makes the echoes weave through the grid instead of
 * doubling it, and it is the single most recognisable move in the genre. */
export const DELAY_BEATS = 0.75;
export const DELAY_FEEDBACK = 0.52;
/** Sent level into the delay. The plucks themselves are quiet and sparse; the
 * trail is what the listener actually hears. */
export const DELAY_SEND = 0.75;

/** Delay time in seconds for a given tempo. Pure. */
export function delaySeconds(bpm: number = TEMPO_BPM): number {
  return beatSeconds(bpm) * DELAY_BEATS;
}

export const PLUCK_GAIN = 0.085;
export const PLUCK_ATTACK_S = 0.006;
export const PLUCK_DECAY_S = 0.55;
/** Beats a pluck may land on. All off the downbeat, which belongs to the sub,
 * and mostly off the beat entirely so the delay's dotted trail has somewhere to
 * fall. */
export const PLUCK_SLOTS = [1, 1.5, 2.5, 3, 3.5] as const;
/** Chance of a second pluck once the first has fired. Two is a phrase; three
 * would be a melody, which is too much foreground for a background bed. */
export const PLUCK_SECOND_CHANCE = 0.22;

export interface ScheduledPluck {
  atBeat: number;
  freqHz: number;
  gain: number;
}

export interface BarPlan {
  subs: ScheduledSub[];
  plucks: ScheduledPluck[];
}

/** A pluck pitch: a Dorian degree two octaves above the drone root, with an
 * occasional 9th/11th above that for colour. Pure given `rand` (consumes two
 * draws: one for the degree, one for the colour roll). */
export function pluckFreqHz(rootHz: number, rand: () => number): number {
  const r = clamp01(rand());
  const semitone = DORIAN_SEMITONES[
    Math.min(DORIAN_SEMITONES.length - 1, Math.floor(r * DORIAN_SEMITONES.length))
  ];
  const colour = clamp01(rand());
  if (colour < COLOUR_CHANCE) {
    const c = COLOUR_SEMITONES[
      Math.min(COLOUR_SEMITONES.length - 1, Math.floor((colour / COLOUR_CHANCE) * COLOUR_SEMITONES.length))
    ];
    return rootHz * 4 * Math.pow(2, c / 12);
  }
  return rootHz * 4 * Math.pow(2, semitone / 12);
}

/** Everything that happens in one bar: the sub pulses (always — that is the
 * heartbeat) and however many plucks the dice allow. Pure given `rand`, so the
 * scheduler in `player.ts` only has to turn times into nodes.
 *
 * `pluckChance` comes from the macro arc, which is how the bed thins out and
 * fills back in over a session. */
export function barPlan(rootHz: number, pluckChance: number, rand: () => number): BarPlan {
  const subs: ScheduledSub[] = SUB_BEATS.map((atBeat, i) => ({
    atBeat,
    gain: i === 0 ? SUB_GAIN : SUB_GAIN * SUB_OFFBEAT_LEVEL,
  }));

  const plucks: ScheduledPluck[] = [];
  const chance = clamp01(Number.isFinite(pluckChance) ? pluckChance : 0);
  if (clamp01(rand()) < chance) {
    plucks.push(pluckAt(rootHz, rand));
    if (clamp01(rand()) < PLUCK_SECOND_CHANCE) {
      const second = pluckAt(rootHz, rand);
      // Two plucks on the same sixteenth would just be one louder pluck.
      if (second.atBeat !== plucks[0].atBeat) plucks.push(second);
    }
  }
  plucks.sort((a, b) => a.atBeat - b.atBeat);
  return { subs, plucks };
}

function pluckAt(rootHz: number, rand: () => number): ScheduledPluck {
  const slot = PLUCK_SLOTS[
    Math.min(PLUCK_SLOTS.length - 1, Math.floor(clamp01(rand()) * PLUCK_SLOTS.length))
  ];
  return { atBeat: slot, freqHz: pluckFreqHz(rootHz, rand), gain: PLUCK_GAIN };
}

/* ── The sidechain-style duck ───────────────────────────────────────────── */

/** How far the pad and noise dip under each sub pulse, as a fraction. A fifth
 * is enough to hear as breathing and nowhere near enough to hear as pumping. */
export const DUCK_DEPTH = 0.2;
export const DUCK_ATTACK_S = 0.035;
/** How long the dip takes to recover, in beats — just under the gap to the next
 * pulse, so the pad is back up before it is pushed down again. */
export const DUCK_RELEASE_BEATS = 1.4;

export interface DuckEnvelope {
  /** Gain to dip to (1 = untouched). */
  dipTo: number;
  attackS: number;
  releaseS: number;
}

/** The scheduled gain dip that stands in for a sidechain compressor: a real
 * compressor would need the sub routed into a detector and would react to the
 * pad as well, where this is exactly as deep as it is written to be. Pure. */
export function duckEnvelope(strength: number = 1, bpm: number = TEMPO_BPM): DuckEnvelope {
  const s = clamp01(Number.isFinite(strength) ? strength : 0);
  return {
    dipTo: Math.max(MIN_GAIN, 1 - DUCK_DEPTH * s),
    attackS: DUCK_ATTACK_S,
    releaseS: beatSeconds(bpm) * DUCK_RELEASE_BEATS,
  };
}

/* ── The macro arc ──────────────────────────────────────────────────────── */

/** One trip around the arc. Seven minutes is long enough that nothing about it
 * is noticeable moment to moment, and short enough that a half-hour stack run
 * hears it several times. */
export const MACRO_PERIOD_S = 420;

/** The band the pad's filter centre moves across over the arc, and the layer
 * levels at each end of it. Closed and thin at 0, open and full at 1. */
export const MACRO_LOWPASS_MIN_HZ = 340;
export const MACRO_LOWPASS_MAX_HZ = 880;
export const MACRO_NOISE_MIN = 0.03;
export const MACRO_NOISE_MAX = 0.062;
export const MACRO_PLUCK_CHANCE_MIN = 0.22;
export const MACRO_PLUCK_CHANCE_MAX = 0.7;
export const MACRO_SUB_MIN = 0.62;
export const MACRO_SUB_MAX = 1;

export interface MacroLevels {
  /** 0 (most closed and sparse) … 1 (most open and full). */
  openness: number;
  /** Centre frequency for the pad lowpass; the fast LFO sweeps around this. */
  lowpassHz: number;
  noiseGain: number;
  pluckChance: number;
  /** Multiplier on the sub pulse level, so the bottom end eases in and out too. */
  subLevel: number;
}

/** Where the arc is at `tSeconds`. A raised cosine, so it has no corners to
 * hear: the bed is always either slowly opening or slowly closing, never
 * stepping. Pure, and defined for any input including a negative or
 * non-finite clock. */
export function macroLevels(tSeconds: number): MacroLevels {
  const t = Number.isFinite(tSeconds) ? tSeconds : 0;
  const phase = (((t % MACRO_PERIOD_S) + MACRO_PERIOD_S) % MACRO_PERIOD_S) / MACRO_PERIOD_S;
  const openness = (1 - Math.cos(2 * Math.PI * phase)) / 2;
  return {
    openness,
    lowpassHz: lerp(MACRO_LOWPASS_MIN_HZ, MACRO_LOWPASS_MAX_HZ, openness),
    noiseGain: lerp(MACRO_NOISE_MIN, MACRO_NOISE_MAX, openness),
    pluckChance: lerp(MACRO_PLUCK_CHANCE_MIN, MACRO_PLUCK_CHANCE_MAX, openness),
    subLevel: lerp(MACRO_SUB_MIN, MACRO_SUB_MAX, openness),
  };
}

/* ── Bells (the "space" layer, kept — retuned) ──────────────────────────── */

/** Sparse bells: one ping every 12–34 s, never on the grid. With a tempo-locked
 * pluck layer now carrying the movement, these are rarer than they were — they
 * are what makes it read as *space* rather than *hum*, and the layer most
 * easily overdone. */
export const BELL_MIN_GAP_S = 12;
export const BELL_MAX_GAP_S = 34;
export const BELL_GAIN = 0.075;
export const BELL_DECAY_S = 6;

/** Reverb tail length. Long enough that the bells smear into the pad. */
export const REVERB_SECONDS = 4.5;

/** Master gain for a 0–1 volume setting, clamped and floored above zero so an
 * exponential ramp always has somewhere legal to go. Pure. */
export function masterGainFor(volume: number): number {
  if (!Number.isFinite(volume)) return MIN_GAIN;
  const v = clamp01(volume);
  return Math.max(MIN_GAIN, v * MASTER_GAIN_CEILING);
}

/** Seconds until the next bell — uniform in [12, 34], never quantised. Pure
 * given `rand` (a 0–1 source), so a test can pin both ends. */
export function nextBellGapS(rand: () => number): number {
  const r = clamp01(rand());
  return BELL_MIN_GAP_S + r * (BELL_MAX_GAP_S - BELL_MIN_GAP_S);
}

/** A bell pitch: a minor-pentatonic degree two or three octaves above the drone
 * root. Pure given `rand`. */
export function bellFreqHz(rootHz: number, rand: () => number): number {
  const degrees = MINOR_PENTATONIC_SEMITONES.length;
  const octaves = 2;
  const slot = Math.min(degrees * octaves - 1,
                        Math.floor(clamp01(rand()) * degrees * octaves));
  const semitone = MINOR_PENTATONIC_SEMITONES[slot % degrees] + 12 * Math.floor(slot / degrees);
  // ×4 = two octaves up, so the bells sit clear of the pad rather than in it.
  return rootHz * 4 * Math.pow(2, semitone / 12);
}

/** Seconds to sit on the current root before drifting. Pure given `rand`. */
export function nextRootHoldS(rand: () => number): number {
  const r = clamp01(rand());
  return ROOT_DRIFT_MIN_S + r * (ROOT_DRIFT_MAX_S - ROOT_DRIFT_MIN_S);
}

/** Pick a root that isn't the one already sounding, so a "drift" always audibly
 * moves. Pure given `rand`. */
export function nextRootHz(currentHz: number, rand: () => number): number {
  const others = ROOT_HZ.filter((hz) => hz !== currentHz);
  if (!others.length) return ROOT_HZ[0];
  const i = Math.min(others.length - 1, Math.floor(clamp01(rand()) * others.length));
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

function clamp01(v: number): number {
  return Math.min(1, Math.max(0, v));
}

function lerp(a: number, b: number, t: number): number {
  return a + (b - a) * t;
}
