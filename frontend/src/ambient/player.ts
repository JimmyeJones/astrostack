/** The Web Audio half of the ambient soundbed: turns `voicing.ts`'s decisions
 * into a running node graph.
 *
 * Shape of the graph:
 *
 *     4 detuned oscillators ─┐
 *     brown-noise loop ──────┼─> bus ─┬─> convolver (generated IR) ─┐
 *     sparse bells ──────────┘        └────────── dry ──────────────┴─> master gain
 *                                                                        └─> limiter ─> out
 *
 * Three rules this layer exists to honour:
 *   1. **Only ever created/resumed from a user gesture.** Browsers start an
 *      `AudioContext` suspended and refuse to resume it outside a real click,
 *      so building the graph on mount would silently fail and leave the toggle
 *      lying about its state. `start()` is called from the toggle's handler and
 *      the UI reflects the context's *actual* state.
 *   2. **Suspend, don't just mute.** A convolver running in a tab left open for
 *      hours burns real CPU. Stopping fades out, then suspends the context.
 *   3. **Never a click.** Every gain change is a ramp, and an exponential ramp
 *      never targets exactly zero (see `MIN_GAIN`).
 *
 * The constructor takes its `AudioContext` from an injectable factory so tests
 * can pass a stub — jsdom has no Web Audio, and asserting on rendered sound
 * isn't the point: that `resume`/`suspend` happen at the right moments is.
 */
import {
  BELL_DECAY_S,
  BELL_GAIN,
  FADE_SECONDS,
  LOWPASS_BASE_HZ,
  LOWPASS_LFO_HZ,
  LOWPASS_SWEEP_HZ,
  MIN_GAIN,
  NOISE_BANDPASS_HZ,
  NOISE_GAIN,
  NOISE_LFO_HZ,
  NOISE_Q,
  NOISE_SWEEP_HZ,
  REVERB_SECONDS,
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

export type AmbientState = "stopped" | "playing";

type ContextFactory = () => AudioContext;

function defaultContextFactory(): AudioContext {
  const Ctor =
    (window as unknown as { AudioContext?: typeof AudioContext }).AudioContext
    ?? (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
  if (!Ctor) throw new Error("Web Audio is not available in this browser");
  return new Ctor();
}

/** Whether this browser can play the bed at all. */
export function ambientSupported(): boolean {
  if (typeof window === "undefined") return false;
  const w = window as unknown as { AudioContext?: unknown; webkitAudioContext?: unknown };
  return Boolean(w.AudioContext || w.webkitAudioContext);
}

export interface AmbientPlayerOptions {
  contextFactory?: ContextFactory;
  /** 0–1 source for the un-gridded bell timing and pitches. Injectable so a
   * test can make the schedule deterministic. */
  random?: () => number;
  /** Injectable timers so a test can drive the bell/root schedule with a fake
   * clock instead of waiting 25 real seconds. */
  setTimer?: (fn: () => void, ms: number) => number;
  clearTimer?: (handle: number) => void;
}

export class AmbientPlayer {
  private ctx: AudioContext | null = null;
  private master: GainNode | null = null;
  private bus: GainNode | null = null;
  private rootHz: number = ROOT_HZ[0];
  // Kept apart on purpose: a root drift tears down and rebuilds the *pad* only.
  // Folding the (pitchless, always-on) noise bed into the same list would stop
  // it on the first drift and never bring it back.
  private droneStops: Array<() => void> = [];
  private noiseStops: Array<() => void> = [];
  private bellTimer: number | null = null;
  private rootTimer: number | null = null;
  private listeners = new Set<() => void>();
  private playing = false;
  private volume: number;

  private readonly makeContext: ContextFactory;
  private readonly random: () => number;
  private readonly setTimer: (fn: () => void, ms: number) => number;
  private readonly clearTimer: (handle: number) => void;

  constructor(volume: number, opts: AmbientPlayerOptions = {}) {
    this.volume = volume;
    this.makeContext = opts.contextFactory ?? defaultContextFactory;
    this.random = opts.random ?? Math.random;
    this.setTimer = opts.setTimer ?? ((fn, ms) => window.setTimeout(fn, ms));
    this.clearTimer = opts.clearTimer ?? ((h) => window.clearTimeout(h));
  }

  get state(): AmbientState {
    return this.playing ? "playing" : "stopped";
  }

  /** Subscribe to state changes (for `useSyncExternalStore`). */
  subscribe(fn: () => void): () => void {
    this.listeners.add(fn);
    return () => this.listeners.delete(fn);
  }

  private emit(): void {
    for (const fn of this.listeners) fn();
  }

  /** Build (once) and resume the graph. **Must be called from a user gesture.**
   * Returns false if audio couldn't be started, so the caller can leave the
   * toggle off rather than showing "playing" over silence. */
  async start(): Promise<boolean> {
    try {
      if (!this.ctx) {
        this.ctx = this.makeContext();
        this.buildGraph(this.ctx);
      }
      await this.ctx.resume();
      // Fade up from silence every time, including after a suspend.
      this.rampMaster(masterGainFor(this.volume));
      if (!this.playing) {
        this.playing = true;
        this.scheduleBell();
        this.scheduleRootDrift();
        this.emit();
      }
      return true;
    } catch {
      this.playing = false;
      this.emit();
      return false;
    }
  }

  /** Fade out, then suspend the context so an idle tab costs nothing. The graph
   * is kept intact so a later `start()` is instant (and needs no rebuild). */
  async stop(): Promise<void> {
    if (!this.ctx) {
      this.playing = false;
      this.emit();
      return;
    }
    this.cancelTimers();
    this.rampMaster(MIN_GAIN);
    this.playing = false;
    this.emit();
    const ctx = this.ctx;
    await new Promise<void>((resolve) => {
      this.setTimer(() => resolve(), Math.ceil(FADE_SECONDS * 1000));
    });
    // A restart during the fade must win — don't suspend out from under it.
    if (this.playing) return;
    try {
      await ctx.suspend();
    } catch {
      /* already closed/suspended — nothing to undo. */
    }
  }

  /** Ramp to a new volume (0–1). Takes effect immediately when playing, and is
   * remembered for the next start when not. */
  setVolume(volume: number): void {
    this.volume = volume;
    if (this.playing) this.rampMaster(masterGainFor(volume));
  }

  private rampMaster(target: number): void {
    const ctx = this.ctx;
    const master = this.master;
    if (!ctx || !master) return;
    const now = ctx.currentTime;
    const g = master.gain;
    try {
      g.cancelScheduledValues(now);
      // Pin the current value first: without it the ramp starts from whatever
      // value was last *scheduled*, which jumps audibly mid-fade.
      g.setValueAtTime(Math.max(MIN_GAIN, g.value || MIN_GAIN), now);
      g.exponentialRampToValueAtTime(Math.max(MIN_GAIN, target), now + FADE_SECONDS);
    } catch {
      /* a stub/older implementation without ramps — leave the gain alone. */
    }
  }

  private buildGraph(ctx: AudioContext): void {
    const master = ctx.createGain();
    master.gain.value = MIN_GAIN;
    // Safety limiter: no combination of pad + noise + overlapping bells can
    // spike, however many tails are ringing at once.
    const limiter = ctx.createDynamicsCompressor();
    limiter.threshold.value = -18;
    limiter.ratio.value = 12;
    master.connect(limiter);
    limiter.connect(ctx.destination);

    const bus = ctx.createGain();
    bus.gain.value = 1;
    // Wet/dry: the convolver gives the long tail, the dry path keeps the pad
    // from turning to mush.
    const reverb = ctx.createConvolver();
    reverb.buffer = this.makeImpulse(ctx);
    const wet = ctx.createGain();
    wet.gain.value = 0.75;
    const dry = ctx.createGain();
    dry.gain.value = 0.55;
    bus.connect(reverb);
    reverb.connect(wet);
    wet.connect(master);
    bus.connect(dry);
    dry.connect(master);

    this.master = master;
    this.bus = bus;
    this.startDrone(ctx, bus, this.rootHz);
    this.startNoiseBed(ctx, bus);
  }

  private makeImpulse(ctx: AudioContext): AudioBuffer {
    const len = Math.max(1, Math.floor(ctx.sampleRate * REVERB_SECONDS));
    const buf = ctx.createBuffer(2, len, ctx.sampleRate);
    for (let ch = 0; ch < buf.numberOfChannels; ch++) {
      // A different noise realisation per channel is what makes the tail stereo.
      buf.copyToChannel(impulseResponse(ctx.sampleRate, REVERB_SECONDS, this.random), ch);
    }
    return buf;
  }

  private startDrone(ctx: AudioContext, dest: AudioNode, rootHz: number): void {
    const pad = ctx.createGain();
    pad.gain.value = 0.5;
    const lowpass = ctx.createBiquadFilter();
    lowpass.type = "lowpass";
    lowpass.frequency.value = LOWPASS_BASE_HZ + LOWPASS_SWEEP_HZ / 2;
    pad.connect(lowpass);
    lowpass.connect(dest);

    // Very slow LFO across the cutoff — the pad's "breathing in the dark".
    const lfo = ctx.createOscillator();
    lfo.frequency.value = LOWPASS_LFO_HZ;
    const lfoGain = ctx.createGain();
    lfoGain.gain.value = LOWPASS_SWEEP_HZ / 2;
    lfo.connect(lfoGain);
    lfoGain.connect(lowpass.frequency);
    lfo.start();

    const stops: Array<() => void> = [() => lfo.stop()];
    for (const voice of droneVoices(rootHz)) {
      const osc = ctx.createOscillator();
      osc.type = voice.type;
      osc.frequency.value = voice.freqHz;
      osc.detune.value = voice.detuneCents;
      const g = ctx.createGain();
      g.gain.value = voice.gain;
      // Each voice swells on its own clock, so the chord never sits still.
      const swell = ctx.createOscillator();
      swell.frequency.value = 1 / voice.swellPeriodS;
      const swellDepth = ctx.createGain();
      swellDepth.gain.value = voice.gain * 0.45;
      swell.connect(swellDepth);
      swellDepth.connect(g.gain);
      osc.connect(g);
      g.connect(pad);
      osc.start();
      // An oscillator's phase can't be set, so de-phase the swells by starting
      // each a fraction of its own period late; until then the voice just holds
      // its base gain, which is inaudible as a difference.
      swell.start(ctx.currentTime + voice.swellPhase * voice.swellPeriodS);
      stops.push(() => { osc.stop(); swell.stop(); });
    }
    this.droneStops = stops;
  }

  private startNoiseBed(ctx: AudioContext, dest: AudioNode): void {
    const seconds = 8;
    const len = Math.max(1, Math.floor(ctx.sampleRate * seconds));
    const buf = ctx.createBuffer(1, len, ctx.sampleRate);
    buf.copyToChannel(brownNoise(len, this.random), 0);
    const src = ctx.createBufferSource();
    src.buffer = buf;
    src.loop = true;
    const band = ctx.createBiquadFilter();
    band.type = "bandpass";
    band.frequency.value = NOISE_BANDPASS_HZ;
    band.Q.value = NOISE_Q;
    const g = ctx.createGain();
    g.gain.value = NOISE_GAIN;
    const lfo = ctx.createOscillator();
    lfo.frequency.value = NOISE_LFO_HZ;
    const lfoGain = ctx.createGain();
    lfoGain.gain.value = NOISE_SWEEP_HZ;
    lfo.connect(lfoGain);
    lfoGain.connect(band.frequency);
    lfo.start();
    src.connect(band);
    band.connect(g);
    g.connect(dest);
    src.start();
    this.noiseStops.push(() => { src.stop(); lfo.stop(); });
  }

  private scheduleBell(): void {
    const gap = nextBellGapS(this.random);
    this.bellTimer = this.setTimer(() => {
      this.ringBell();
      if (this.playing) this.scheduleBell();
    }, Math.round(gap * 1000));
  }

  private ringBell(): void {
    const ctx = this.ctx;
    const bus = this.bus;
    if (!ctx || !bus || !this.playing) return;
    try {
      const now = ctx.currentTime;
      const freq = bellFreqHz(this.rootHz, this.random);
      const osc = ctx.createOscillator();
      osc.type = "sine";
      osc.frequency.value = freq;
      // A quiet inharmonic partner an octave-and-a-bit up gives the ping its
      // metallic edge without an FM operator's cost.
      const shimmer = ctx.createOscillator();
      shimmer.type = "sine";
      shimmer.frequency.value = freq * 2.76;
      const shimmerGain = ctx.createGain();
      shimmerGain.gain.value = 0.18;
      const g = ctx.createGain();
      g.gain.setValueAtTime(MIN_GAIN, now);
      g.gain.exponentialRampToValueAtTime(BELL_GAIN, now + 0.02);
      g.gain.exponentialRampToValueAtTime(MIN_GAIN, now + BELL_DECAY_S);
      osc.connect(g);
      shimmer.connect(shimmerGain);
      shimmerGain.connect(g);
      g.connect(bus);
      osc.start(now);
      shimmer.start(now);
      osc.stop(now + BELL_DECAY_S);
      shimmer.stop(now + BELL_DECAY_S);
    } catch {
      /* a bell that fails to sound must never take the bed down with it. */
    }
  }

  private scheduleRootDrift(): void {
    const hold = nextRootHoldS(this.random);
    this.rootTimer = this.setTimer(() => {
      this.driftRoot();
      if (this.playing) this.scheduleRootDrift();
    }, Math.round(hold * 1000));
  }

  /** Move to a related root: fade the current pad out by stopping its voices and
   * building the next one. Only the bells and pad change; the noise bed is
   * pitchless and stays. */
  private driftRoot(): void {
    const ctx = this.ctx;
    const bus = this.bus;
    if (!ctx || !bus || !this.playing) return;
    try {
      const stops = this.droneStops;
      this.droneStops = [];
      this.rootHz = nextRootHz(this.rootHz, this.random);
      this.startDrone(ctx, bus, this.rootHz);
      for (const stop of stops) {
        try {
          stop();
        } catch {
          /* a node already stopped — fine. */
        }
      }
    } catch {
      /* keep playing on the old root rather than dying mid-session. */
    }
  }

  private cancelTimers(): void {
    if (this.bellTimer !== null) this.clearTimer(this.bellTimer);
    if (this.rootTimer !== null) this.clearTimer(this.rootTimer);
    this.bellTimer = null;
    this.rootTimer = null;
  }
}

let singleton: AmbientPlayer | null = null;

/** The one player the app shell shares between the header toggle and the
 * Settings volume slider. Created lazily so importing this module never touches
 * Web Audio (which would be a no-op at best, an autoplay-policy failure at
 * worst). */
export function ambientPlayer(volume: number, opts?: AmbientPlayerOptions): AmbientPlayer {
  if (!singleton) singleton = new AmbientPlayer(volume, opts);
  return singleton;
}

/** Test seam: drop the shared instance so each test starts clean. */
export function resetAmbientPlayer(): void {
  singleton = null;
}
