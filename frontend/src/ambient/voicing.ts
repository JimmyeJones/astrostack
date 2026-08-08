/** Sound design for the optional "space ambient" background bed — the pure half.
 *
 * Everything here is a *decision*: the tempo grid, which voices make up the pad,
 * how loud the master gain should be for a given volume setting, when the next
 * bell or pluck fires and on what note, how deep the sub pulse ducks the bed,
 * where the multi-minute arc has got to. Nothing in this file touches the Web
 * Audio API, so it is all directly unit-testable; `player.ts` is the thin,
 * untestable-by-nature layer that turns these numbers into nodes.
 *
 * The bed is **synthesised**, never sampled: no audio file ships in the repo or
 * is fetched at runtime (the owner's box is offline-first), and a generated bed
 * has no loop point to hear on a multi-hour session. Everything below is
 * original material written in the psychill/psydub *idiom* — a tempo, a mode and
 * a set of textures — not a transcription of anything.
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

/* ── The grid ───────────────────────────────────────────────────────────────
 * The genre has a heartbeat rather than a beat: everything rhythmic below is
 * derived from this one tempo, so the sub pulse, the plucks and the delay all
 * agree without anything ever sounding like a drum machine.
 */

/** Beats per minute. 76 sits in the middle of the genre's usual 72–84 and is
 * slow enough to read as breathing rather than as a track playing. */
export const TEMPO_BPM = 76;
export const BEATS_PER_BAR = 4;

/** Lookahead scheduling: a plain timer decides *when to think*, and every event
 * it schedules is pinned to an exact audio-clock time, so timer jitter never
 * reaches the grid. */
export const SCHEDULER_TICK_MS = 200;
export const SCHEDULE_AHEAD_S = 0.6;
/** Backstop so a stalled or non-advancing clock can never make one tick
 * schedule an unbounded number of events. */
export const MAX_BEATS_PER_TICK = 32;

/* ── The bottom end ─────────────────────────────────────────────────────── */

/** The sub pulse: a soft sine an octave under the pad root, enveloped on the
 * grid. Not a kick — no click, no noise, just weight arriving and leaving. */
export const SUB_GAIN = 0.55;
export const SUB_ATTACK_S = 0.02;
export const SUB_DECAY_S = 0.6;

/** Sidechain-style "breathing": the pad and noise bed dip under each sub pulse
 * and swell back. A scheduled gain dip, not a compressor — cheaper, and it can
 * be shaped exactly. */
export const DUCK_DEPTH = 0.34;
export const DUCK_RELEASE_S = 0.5;

/* ── Plucks and the delay that does the real work ───────────────────────── */

/** Short plucks, deliberately sparse: the dotted-eighth delay dissolves each one
 * into a receding trail, which is the sound. Too many and it turns to porridge. */
export const PLUCK_GAIN = 0.06;
export const PLUCK_DECAY_S = 0.9;
/** Chance of a pluck on an eligible beat, at the top of the macro arc. */
export const PLUCK_PROBABILITY = 0.3;

/** Ping-pong feedback. Under 1 by a wide margin — the loop must decay. */
export const DELAY_FEEDBACK = 0.52;
export const DELAY_WET = 0.5;
/** How much of the pluck goes out dry, so the first hit has a body. */
export const DELAY_DRY = 0.35;

/* ── Width ──────────────────────────────────────────────────────────────── */

/** Chorus: two short modulated delay lines, hard-ish left and right. The bed
 * used to be near-mono; the genre is very wide. */
export const CHORUS_DELAY_S = [0.011, 0.019] as const;
export const CHORUS_DEPTH_S = 0.0035;
export const CHORUS_RATE_HZ = [0.07, 0.11] as const;
export const CHORUS_PAN = [-0.7, 0.7] as const;
export const CHORUS_WET = 0.55;
export const CHORUS_DRY = 0.6;

/* ── The pad ────────────────────────────────────────────────────────────── */

/** The pad's lowpass: a slow LFO sweeps the cutoff across this band, which is
 * what stops a static chord from reading as a test tone. The base is also
 * where the multi-minute arc opens and closes the whole bed. */
export const LOWPASS_BASE_HZ = 400;
export const LOWPASS_SWEEP_HZ = 400;
export const LOWPASS_LFO_HZ = 0.035;

/** Overall pad level. Lower than the old sine bed's, because each voice is now
 * a *pair* of sawtooths and a saw carries far more energy than a sine. */
export const PAD_GAIN = 0.3;

/** The "solar wind" layer: brown noise through a slowly-sweeping bandpass,
 * mixed well under the pad. */
export const NOISE_GAIN = 0.05;
export const NOISE_BANDPASS_HZ = 320;
export const NOISE_SWEEP_HZ = 220;
export const NOISE_LFO_HZ = 0.017;
export const NOISE_Q = 0.7;

/** Sparse bells: one ping every 8–25 s, deliberately **off** the grid — the one
 * layer that isn't tempo-locked, which is what keeps the bed from marching. */
export const BELL_MIN_GAP_S = 8;
export const BELL_MAX_GAP_S = 25;
export const BELL_GAIN = 0.09;
export const BELL_DECAY_S = 6;

/** Reverb tail length. Long enough that the bells smear into the pad. */
export const REVERB_SECONDS = 4.5;

/* ── The mode ───────────────────────────────────────────────────────────── */

/** Minor pentatonic — no semitone clashes, so any two notes sound intentional
 * together however they overlap in the reverb tail, and a darker mode than the
 * major pentatonic this bed started with. */
export const MINOR_PENTATONIC_SEMITONES = [0, 3, 5, 7, 10] as const;

/** Dorian colour: the 9th and the natural 6th. Dorian's raised 6th is what
 * keeps a minor bed spacious rather than mournful; used sparingly so the
 * pentatonic still carries the tune. */
export const DORIAN_COLOUR_SEMITONES = [2, 9] as const;

/** How often a note reaches for a colour tone instead of the pentatonic. */
export const COLOUR_TONE_CHANCE = 0.22;

/* ── The macro arc ──────────────────────────────────────────────────────── */

/** One full open-and-close of the bed. Long enough that you feel it rather than
 * notice it — a session goes somewhere instead of sitting still. */
export const MACRO_PERIOD_S = 480;
/** How far the arc lifts the pad's cutoff at its brightest. */
export const MACRO_FILTER_LIFT_HZ = 300;
/** At the bottom of the arc the plucks thin out to this fraction of their
 * usual density; they never stop entirely. */
export const MACRO_DENSITY_FLOOR = 0.35;

export interface DroneVoice {
  /** Base frequency in Hz (already transposed from the root). */
  freqHz: number;
  type: OscillatorType;
  /** Contribution to the pad, before the master gain. Split across the pair. */
  gain: number;
  /** A few cents off, so voices beat slowly against each other instead of
   * phase-locking into one dead tone. */
  detuneCents: number;
  /** The pair's spread: the player builds two oscillators per voice, detuned
   * `detuneCents ± pairDetuneCents`. Supersaw-lite — warmth without a
   * wavetable. */
  pairDetuneCents: number;
  /** Where the voice sits in the stereo field (−1 left … +1 right). */
  pan: number;
  /** Independent slow amplitude swell, so the pad breathes. The periods are
   * mutually awkward numbers so the voices never re-align into a pulse. */
  swellPeriodS: number;
  /** Offset into the swell, in turns (0–1), so they don't all start together. */
  swellPhase: number;
}

/** The pad: root + fifth + octave + twelfth, each a detuned sawtooth pair on its
 * own swell clock and its own place in the stereo field. Pure — same root in,
 * same voices out. */
export function droneVoices(rootHz: number): DroneVoice[] {
  return [
    // The root stays near the centre: a wide bottom end smears the mix.
    { freqHz: rootHz, type: "sawtooth", gain: 0.50, detuneCents: -4, pairDetuneCents: 5,
      pan: -0.12, swellPeriodS: 37, swellPhase: 0 },
    { freqHz: rootHz * 1.5, type: "sawtooth", gain: 0.30, detuneCents: +6, pairDetuneCents: 7,
      pan: 0.35, swellPeriodS: 43, swellPhase: 0.25 },
    { freqHz: rootHz * 2, type: "sawtooth", gain: 0.18, detuneCents: -7, pairDetuneCents: 9,
      pan: -0.45, swellPeriodS: 53, swellPhase: 0.5 },
    { freqHz: rootHz * 3, type: "triangle", gain: 0.09, detuneCents: +3, pairDetuneCents: 6,
      pan: 0.55, swellPeriodS: 61, swellPhase: 0.75 },
  ];
}

/** Master gain for a 0–1 volume setting, clamped and floored above zero so an
 * exponential ramp always has somewhere legal to go. Pure. */
export function masterGainFor(volume: number): number {
  if (!Number.isFinite(volume)) return MIN_GAIN;
  const v = Math.min(1, Math.max(0, volume));
  return Math.max(MIN_GAIN, v * MASTER_GAIN_CEILING);
}

/** One beat, in seconds. Everything rhythmic derives from this. Pure. */
export function beatSeconds(bpm: number = TEMPO_BPM): number {
  return 60 / bpm;
}

/** A bar, in seconds. Pure. */
export function barSeconds(bpm: number = TEMPO_BPM): number {
  return beatSeconds(bpm) * BEATS_PER_BAR;
}

/** The delay time that makes the genre's signature trail: a dotted eighth, so
 * each repeat lands *between* the pulses instead of on them. Pure. */
export function dottedEighthSeconds(bpm: number = TEMPO_BPM): number {
  return beatSeconds(bpm) * 0.75;
}

/** How hard the sub pulses on a given beat of the grid, 0 = not at all.
 * The downbeat carries the weight and the third beat answers it more softly —
 * enough to imply a tempo without ever sounding like a kick pattern. Pure. */
export function subPulseGainForBeat(beatIndex: number): number {
  const inBar = ((beatIndex % BEATS_PER_BAR) + BEATS_PER_BAR) % BEATS_PER_BAR;
  if (inBar === 0) return 1;
  if (inBar === 2) return 0.55;
  return 0;
}

/** Where the multi-minute arc has got to, 0 (closed, quiet) … 1 (open). A
 * raised cosine, so it is always moving and never has a corner. Pure. */
export function macroLevelAt(elapsedS: number): number {
  if (!Number.isFinite(elapsedS)) return 0;
  const phase = (Math.max(0, elapsedS) % MACRO_PERIOD_S) / MACRO_PERIOD_S;
  return 0.5 - 0.5 * Math.cos(2 * Math.PI * phase);
}

/** The pad cutoff the arc asks for at this point in the session. The fast LFO
 * in the graph adds its sweep on top of this, so the two compose. Pure. */
export function macroFilterHz(elapsedS: number): number {
  return LOWPASS_BASE_HZ + LOWPASS_SWEEP_HZ / 2 + MACRO_FILTER_LIFT_HZ * macroLevelAt(elapsedS);
}

/** Pluck density at this point in the arc: thinner when the bed is closed,
 * never zero. Pure. */
export function macroPluckDensity(elapsedS: number): number {
  return MACRO_DENSITY_FLOOR + (1 - MACRO_DENSITY_FLOOR) * macroLevelAt(elapsedS);
}

/** Whether a pluck fires on this beat. Only off-downbeat positions are eligible,
 * so a pluck never competes with the sub, and even then it is a coin-flip well
 * under even odds — the delay makes one note sound like several. Pure given
 * `rand`. */
export function shouldPluckOnBeat(
  beatIndex: number,
  rand: () => number,
  density = 1,
): boolean {
  const inBar = ((beatIndex % BEATS_PER_BAR) + BEATS_PER_BAR) % BEATS_PER_BAR;
  if (inBar === 0) return false;
  const p = PLUCK_PROBABILITY * Math.min(1, Math.max(0, density));
  return Math.min(1, Math.max(0, rand())) < p;
}

/** Pick a scale degree in semitones above the root: usually minor pentatonic,
 * occasionally a Dorian colour tone. Pure given `rand` (consumes two draws). */
export function scaleDegreeSemitones(rand: () => number): number {
  const pick = Math.min(1, Math.max(0, rand()));
  const table = pick < COLOUR_TONE_CHANCE ? DORIAN_COLOUR_SEMITONES : MINOR_PENTATONIC_SEMITONES;
  const r = Math.min(1, Math.max(0, rand()));
  return table[Math.min(table.length - 1, Math.floor(r * table.length))];
}

/** Seconds until the next bell — uniform in [8, 25], never quantised. Pure
 * given `rand` (a 0–1 source), so a test can pin both ends. */
export function nextBellGapS(rand: () => number): number {
  const r = Math.min(1, Math.max(0, rand()));
  return BELL_MIN_GAP_S + r * (BELL_MAX_GAP_S - BELL_MIN_GAP_S);
}

/** A bell pitch: a scale degree two or three octaves above the drone root.
 * Pure given `rand`. */
export function bellFreqHz(rootHz: number, rand: () => number): number {
  const semitone = scaleDegreeSemitones(rand) + (Math.min(1, Math.max(0, rand())) < 0.4 ? 12 : 0);
  // ×4 = two octaves up, so the bells sit clear of the pad rather than in it.
  return rootHz * 4 * Math.pow(2, semitone / 12);
}

/** A pluck pitch: a scale degree one or two octaves above the root, so the
 * plucks speak in the pad's register rather than above the bells. Pure given
 * `rand`. */
export function pluckFreqHz(rootHz: number, rand: () => number): number {
  const semitone = scaleDegreeSemitones(rand) + (Math.min(1, Math.max(0, rand())) < 0.45 ? 12 : 0);
  return rootHz * 2 * Math.pow(2, semitone / 12);
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
