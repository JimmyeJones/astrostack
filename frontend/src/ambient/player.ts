/** The Web Audio half of the ambient soundbed: turns `voicing.ts`'s decisions
 * into a running node graph.
 *
 * Shape of the graph:
 *
 *     detuned saw pairs ─> pan ─┬─> pad sum ─┬─> chorus x2 ─┐
 *                               │            └───── dry ────┴─> lowpass ─┐
 *     brown-noise loop ─────────┼──────────────────────────────────────> duck ─┐
 *     sparse bells ─────────────┼──────────────────────────────────────────────┤
 *     plucks ─┬─> dry ──────────┘                                              │
 *             └─> ping-pong delay (dotted 8th) ─────────────────────────────>  bus
 *                                                     ┌──────────────────────────┘
 *     sub pulses ─> sub gain ─┐                       ├─> convolver ─> wet ─┐
 *                             └───────────────────────┼──── dry ────────────┴─> master
 *                                                                              └─> limiter ─> out
 *
 * The **duck** is the scheduled gain dip that stands in for a sidechain: every
 * sub pulse pushes the pad and noise down and lets them back up, which is the
 * breathing the genre is built on. The sub deliberately bypasses both the duck
 * (it must not duck itself) and the reverb (a 4.5 s tail on 30 Hz is mud).
 *
 * Four rules this layer exists to honour:
 *   1. **Only ever created/resumed from a user gesture.** Browsers start an
 *      `AudioContext` suspended and refuse to resume it outside a real click,
 *      so building the graph on mount would silently fail and leave the toggle
 *      lying about its state. `start()` is called from the toggle's handler and
 *      the UI reflects the context's *actual* state.
 *   2. **Suspend, don't just mute.** A convolver running in a tab left open for
 *      hours burns real CPU. Stopping fades out, then suspends the context.
 *   3. **Never a click.** Every gain change is a ramp, and an exponential ramp
 *      never targets exactly zero (see `MIN_GAIN`).
 *   4. **Bounded, constant node count.** The persistent graph is built once and
 *      reused; the only nodes created per bar are the sub pulses and plucks,
 *      and each disconnects itself in `onended` so a tab left open all night
 *      does not accumulate a graph.
 *
 * The constructor takes its `AudioContext` from an injectable factory so tests
 * can pass a stub — jsdom has no Web Audio, and asserting on rendered sound
 * isn't the point: that `resume`/`suspend` happen at the right moments, and
 * that the grid keeps producing bars, is.
 */
import {
  BELL_DECAY_S,
  BELL_GAIN,
  CHORUS_MIX,
  CHORUS_TAPS,
  DELAY_FEEDBACK,
  DELAY_SEND,
  FADE_SECONDS,
  LOWPASS_LFO_HZ,
  LOWPASS_SWEEP_HZ,
  MIN_GAIN,
  NOISE_BANDPASS_HZ,
  NOISE_LFO_HZ,
  NOISE_Q,
  NOISE_SWEEP_HZ,
  PLUCK_ATTACK_S,
  PLUCK_DECAY_S,
  REVERB_SECONDS,
  ROOT_CROSSFADE_S,
  ROOT_HZ,
  SUB_ATTACK_S,
  SUB_DECAY_S,
  SUB_GAIN,
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
  subVoices,
} from "./voicing";

export type AmbientState = "stopped" | "playing";

type ContextFactory = () => AudioContext;

/** How far ahead of the clock bars are scheduled, and how often we top that up.
 * Two bars of lookahead rides out a busy main thread (a stack-run poll, a
 * re-render) without the pulse stuttering; the tick is well inside that. */
const SCHEDULE_AHEAD_BARS = 2;
const SCHEDULE_TICK_MS = 900;

/** How often the multi-minute arc is re-applied. Each application is a slow
 * ramp to the next value, so a coarse tick still sounds continuous. */
const MACRO_TICK_MS = 5000;
const MACRO_RAMP_S = 6;

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
  /** 0–1 source for the un-gridded bell timing, the pluck dice and the pitches.
   * Injectable so a test can make the schedule deterministic. */
  random?: () => number;
  /** Injectable timers so a test can drive the bar/bell/root schedule with a
   * fake clock instead of waiting for real seconds. */
  setTimer?: (fn: () => void, ms: number) => number;
  clearTimer?: (handle: number) => void;
}

export class AmbientPlayer {
  private ctx: AudioContext | null = null;
  private master: GainNode | null = null;
  private bus: GainNode | null = null;
  /** Where the pad's oscillators land — persistent, so a root drift rebuilds
   * only the voices and never the filter/chorus/duck behind them. */
  private padSum: GainNode | null = null;
  private padFilter: BiquadFilterNode | null = null;
  private duck: GainNode | null = null;
  private noiseGain: GainNode | null = null;
  private subOut: GainNode | null = null;
  private pluckBus: GainNode | null = null;
  private rootHz: number = ROOT_HZ[0];
  // Kept apart on purpose: a root drift tears down and rebuilds the *pad* only.
  // Folding the (pitchless, always-on) noise bed into the same list would stop
  // it on the first drift and never bring it back.
  private droneStops: Array<() => void> = [];
  private noiseStops: Array<() => void> = [];
  private bellTimer: number | null = null;
  private rootTimer: number | null = null;
  private gridTimer: number | null = null;
  private macroTimer: number | null = null;
  /** Context time of the next bar still to be scheduled. */
  private nextBarTime = 0;
  /** Context time the arc is measured from — reset on each start, so a bed
   * resumed after a long pause opens from the top rather than mid-swell. */
  private arcOrigin = 0;
  /** Latest arc value, read by the bar planner. */
  private pluckChance = macroLevels(0).pluckChance;
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
        // The grid restarts from *now*: a bar scheduled before a suspend is
        // long in the past, and catching up would fire a burst of pulses.
        this.nextBarTime = this.ctx.currentTime;
        this.arcOrigin = this.ctx.currentTime;
        this.applyMacro();
        this.scheduleGrid();
        this.scheduleMacro();
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

  /* ── Graph ─────────────────────────────────────────────────────────── */

  private buildGraph(ctx: AudioContext): void {
    const master = ctx.createGain();
    master.gain.value = MIN_GAIN;
    // Safety limiter: no combination of pad + sub + noise + overlapping tails
    // can spike, however many are ringing at once.
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
    wet.gain.value = 0.7;
    const dry = ctx.createGain();
    dry.gain.value = 0.55;
    bus.connect(reverb);
    reverb.connect(wet);
    wet.connect(master);
    bus.connect(dry);
    dry.connect(master);

    // Everything that ducks against the sub goes through here.
    const duck = ctx.createGain();
    duck.gain.value = 1;
    duck.connect(bus);

    const padFilter = ctx.createBiquadFilter();
    padFilter.type = "lowpass";
    padFilter.frequency.value = macroLevels(0).lowpassHz;
    padFilter.connect(duck);

    // Very slow LFO across the cutoff — the pad's "breathing in the dark". The
    // macro arc moves the *centre* this sweeps around, far more slowly still.
    const cutoffLfo = ctx.createOscillator();
    cutoffLfo.frequency.value = LOWPASS_LFO_HZ;
    const cutoffDepth = ctx.createGain();
    cutoffDepth.gain.value = LOWPASS_SWEEP_HZ / 2;
    cutoffLfo.connect(cutoffDepth);
    cutoffDepth.connect(padFilter.frequency);
    cutoffLfo.start();
    this.noiseStops.push(() => cutoffLfo.stop());

    const padSum = ctx.createGain();
    padSum.gain.value = 1;
    padSum.connect(padFilter);
    this.buildChorus(ctx, padSum, padFilter);

    // The sub bypasses both the duck (it must not duck itself) and the reverb.
    const subOut = ctx.createGain();
    subOut.gain.value = macroLevels(0).subLevel;
    subOut.connect(master);

    const pluckBus = ctx.createGain();
    pluckBus.gain.value = 1;
    pluckBus.connect(duck);
    this.buildPingPong(ctx, pluckBus, bus);

    this.master = master;
    this.bus = bus;
    this.padSum = padSum;
    this.padFilter = padFilter;
    this.duck = duck;
    this.subOut = subOut;
    this.pluckBus = pluckBus;
    this.startDrone(ctx, padSum, this.rootHz);
    this.startNoiseBed(ctx, duck);
  }

  /** Two short modulated delay lines panned hard apart, mixed under the dry
   * pad. This is what turns a detuned saw stack from "wide-ish" into wide. */
  private buildChorus(ctx: AudioContext, src: AudioNode, dest: AudioNode): void {
    for (const tap of CHORUS_TAPS) {
      const delay = ctx.createDelay(0.1);
      delay.delayTime.value = tap.delayS;
      const lfo = ctx.createOscillator();
      lfo.frequency.value = tap.lfoHz;
      const depth = ctx.createGain();
      depth.gain.value = tap.depthS;
      lfo.connect(depth);
      depth.connect(delay.delayTime);
      lfo.start();
      const pan = ctx.createStereoPanner();
      pan.pan.value = tap.pan;
      const mix = ctx.createGain();
      mix.gain.value = CHORUS_MIX;
      src.connect(delay);
      delay.connect(pan);
      pan.connect(mix);
      mix.connect(dest);
      this.noiseStops.push(() => lfo.stop());
    }
  }

  /** Dotted-eighth ping-pong: the send lands in the left line, each line hands
   * on to the other, and only the second one feeds back — so the echoes
   * alternate across the stereo field a dotted eighth apart and die away. */
  private buildPingPong(ctx: AudioContext, src: AudioNode, dest: AudioNode): void {
    const time = delaySeconds();
    const left = ctx.createDelay(2);
    left.delayTime.value = time;
    const right = ctx.createDelay(2);
    right.delayTime.value = time;
    const send = ctx.createGain();
    send.gain.value = DELAY_SEND;
    const feedback = ctx.createGain();
    feedback.gain.value = DELAY_FEEDBACK;
    const panLeft = ctx.createStereoPanner();
    panLeft.pan.value = -0.85;
    const panRight = ctx.createStereoPanner();
    panRight.pan.value = 0.85;

    src.connect(send);
    send.connect(left);
    left.connect(right);
    left.connect(panLeft);
    right.connect(panRight);
    right.connect(feedback);
    feedback.connect(left);
    panLeft.connect(dest);
    panRight.connect(dest);
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

  /** Build one pad on `rootHz` behind its own group gain, and leave behind a
   * teardown that fades that group out before stopping anything. `fadeIn` is
   * false only for the very first pad, which the master fade already covers. */
  private startDrone(ctx: AudioContext, dest: AudioNode, rootHz: number, fadeIn = false): void {
    const group = ctx.createGain();
    group.gain.value = fadeIn ? MIN_GAIN : 1;
    group.connect(dest);
    if (fadeIn) this.rampGain(ctx, group.gain, 1, ROOT_CROSSFADE_S);

    const oscillators: OscillatorNode[] = [];
    for (const voice of droneVoices(rootHz)) {
      const g = ctx.createGain();
      g.gain.value = voice.gain;
      const panner = ctx.createStereoPanner();
      panner.pan.value = voice.pan;
      g.connect(panner);
      panner.connect(group);

      // Each voice swells on its own clock, so the chord never sits still.
      const swell = ctx.createOscillator();
      swell.frequency.value = 1 / voice.swellPeriodS;
      const swellDepth = ctx.createGain();
      swellDepth.gain.value = voice.gain * 0.45;
      swell.connect(swellDepth);
      swellDepth.connect(g.gain);

      // …and drifts across the stereo field on another, offset one.
      const panLfo = ctx.createOscillator();
      panLfo.frequency.value = voice.panLfoHz;
      const panDepth = ctx.createGain();
      panDepth.gain.value = voice.panDepth;
      panLfo.connect(panDepth);
      panDepth.connect(panner.pan);
      panLfo.start();

      // A *pair* of oscillators a few cents apart: the beating between them is
      // the width. One sawtooth alone is just a buzz.
      for (const sign of [-1, 1]) {
        const osc = ctx.createOscillator();
        osc.type = voice.type;
        osc.frequency.value = voice.freqHz;
        osc.detune.value = sign * voice.detuneCents;
        osc.connect(g);
        osc.start();
        oscillators.push(osc);
      }
      // An oscillator's phase can't be set, so de-phase the swells by starting
      // each a fraction of its own period late; until then the voice just holds
      // its base gain, which is inaudible as a difference.
      swell.start(ctx.currentTime + voice.swellPhase * voice.swellPeriodS);
      oscillators.push(swell, panLfo);
    }

    this.droneStops = [() => {
      this.rampGain(ctx, group.gain, MIN_GAIN, ROOT_CROSSFADE_S);
      // Only once it is inaudible: stopping a live sawtooth stack is a click,
      // and a group left running for ever is the other way to get this wrong.
      this.setTimer(() => {
        for (const osc of oscillators) {
          try {
            osc.stop();
          } catch {
            /* already stopped — fine. */
          }
        }
        try {
          group.disconnect();
        } catch {
          /* already gone — fine. */
        }
      }, Math.ceil(ROOT_CROSSFADE_S * 1000));
    }];
  }

  /** Ramp a gain from wherever it actually is, never through zero. */
  private rampGain(ctx: AudioContext, param: AudioParam, target: number, seconds: number): void {
    const now = ctx.currentTime;
    try {
      param.cancelScheduledValues(now);
      param.setValueAtTime(Math.max(MIN_GAIN, param.value || MIN_GAIN), now);
      param.exponentialRampToValueAtTime(Math.max(MIN_GAIN, target), now + seconds);
    } catch {
      /* a stub/older implementation without ramps — leave the gain alone. */
    }
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
    g.gain.value = macroLevels(0).noiseGain;
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
    this.noiseGain = g;
    this.noiseStops.push(() => { src.stop(); lfo.stop(); });
  }

  /* ── The grid ──────────────────────────────────────────────────────── */

  /** Top up the schedule, then re-arm. Bars are planned ahead of the clock so a
   * busy main thread can't make the pulse late. */
  private scheduleGrid(): void {
    const ctx = this.ctx;
    if (!ctx || !this.playing) return;
    const bar = barSeconds();
    const horizon = ctx.currentTime + bar * SCHEDULE_AHEAD_BARS;
    // The guard is a backstop, not a policy: a context whose clock jumped
    // forward (a tab restored from the background) must not spend a frame
    // scheduling the hundreds of bars it "missed".
    let guard = 0;
    if (this.nextBarTime < ctx.currentTime) this.nextBarTime = ctx.currentTime;
    while (this.nextBarTime < horizon && guard++ < SCHEDULE_AHEAD_BARS + 2) {
      this.scheduleBar(ctx, this.nextBarTime);
      this.nextBarTime += bar;
    }
    this.gridTimer = this.setTimer(() => this.scheduleGrid(), SCHEDULE_TICK_MS);
  }

  /** Turn one bar's plan into scheduled voices. Wrapped so a single bad bar can
   * never take the bed down with it. */
  private scheduleBar(ctx: AudioContext, at: number): void {
    try {
      const beat = beatSeconds();
      const plan = barPlan(this.rootHz, this.pluckChance, this.random);
      for (const sub of plan.subs) {
        const t = at + sub.atBeat * beat;
        this.pulseSub(ctx, t, sub.gain);
        this.duckAt(t, sub.gain / SUB_GAIN);
      }
      for (const pluck of plan.plucks) {
        this.pluck(ctx, at + pluck.atBeat * beat, pluck.freqHz, pluck.gain);
      }
    } catch {
      /* keep the bed running; the next bar gets another go. */
    }
  }

  /** One soft thump: the octave-under fundamental plus an audible-on-laptops
   * partner at the root, sharing one envelope. */
  private pulseSub(ctx: AudioContext, at: number, gain: number): void {
    const dest = this.subOut;
    if (!dest) return;
    const g = ctx.createGain();
    g.gain.setValueAtTime(MIN_GAIN, at);
    g.gain.exponentialRampToValueAtTime(Math.max(MIN_GAIN, gain), at + SUB_ATTACK_S);
    g.gain.exponentialRampToValueAtTime(MIN_GAIN, at + SUB_DECAY_S);
    g.connect(dest);
    const voices = subVoices(this.rootHz);
    voices.forEach((voice, i) => {
      const osc = ctx.createOscillator();
      osc.type = "sine";
      osc.frequency.value = voice.freqHz;
      const vg = ctx.createGain();
      vg.gain.value = voice.gain;
      osc.connect(vg);
      vg.connect(g);
      osc.start(at);
      osc.stop(at + SUB_DECAY_S + 0.05);
      // Both oscillators stop together; the last one also drops the envelope
      // they share, so nothing is left connected to the sub bus.
      this.disposeWith(osc, osc, vg, ...(i === voices.length - 1 ? [g] : []));
    });
  }

  /** The sidechain-style dip. Scheduled, not compressed, so its depth is
   * exactly what `voicing.ts` says it is. */
  private duckAt(at: number, strength: number): void {
    const duck = this.duck;
    if (!duck) return;
    const env = duckEnvelope(strength);
    try {
      duck.gain.setValueAtTime(1, at);
      duck.gain.linearRampToValueAtTime(env.dipTo, at + env.attackS);
      duck.gain.linearRampToValueAtTime(1, at + env.attackS + env.releaseS);
    } catch {
      /* a stub without ramps — the bed just doesn't breathe. */
    }
  }

  /** A short plucked note into the delay. Quiet on purpose: the dotted-eighth
   * trail behind it is the part meant to be heard. */
  private pluck(ctx: AudioContext, at: number, freqHz: number, gain: number): void {
    const dest = this.pluckBus;
    if (!dest) return;
    const osc = ctx.createOscillator();
    osc.type = "triangle";
    osc.frequency.value = freqHz;
    const tone = ctx.createBiquadFilter();
    tone.type = "lowpass";
    tone.frequency.value = Math.max(600, freqHz * 4);
    const g = ctx.createGain();
    g.gain.setValueAtTime(MIN_GAIN, at);
    g.gain.exponentialRampToValueAtTime(Math.max(MIN_GAIN, gain), at + PLUCK_ATTACK_S);
    g.gain.exponentialRampToValueAtTime(MIN_GAIN, at + PLUCK_DECAY_S);
    osc.connect(tone);
    tone.connect(g);
    g.connect(dest);
    osc.start(at);
    osc.stop(at + PLUCK_DECAY_S + 0.05);
    this.disposeWith(osc, osc, tone, g);
  }

  /** Drop a transient voice's nodes the moment it finishes sounding, so hours
   * of bars don't pile up a graph the GC can't reach past a live connection.
   * Every transient oscillator gets one of these — a node still connected to
   * the bus is still reachable, however long ago it stopped making sound. */
  private disposeWith(osc: OscillatorNode | undefined, ...nodes: AudioNode[]): void {
    if (!osc) return;
    osc.onended = () => {
      for (const node of nodes) {
        try {
          node.disconnect();
        } catch {
          /* already gone — fine. */
        }
      }
    };
  }

  /* ── The arc ───────────────────────────────────────────────────────── */

  private scheduleMacro(): void {
    this.macroTimer = this.setTimer(() => {
      this.applyMacro();
      if (this.playing) this.scheduleMacro();
    }, MACRO_TICK_MS);
  }

  /** Ease the filter centre, the noise bed, the sub level and how often plucks
   * fire toward wherever the arc has reached. */
  private applyMacro(): void {
    const ctx = this.ctx;
    if (!ctx) return;
    const levels = macroLevels(ctx.currentTime - this.arcOrigin);
    this.pluckChance = levels.pluckChance;
    const now = ctx.currentTime;
    const ease = (param: AudioParam | undefined, target: number): void => {
      if (!param) return;
      try {
        param.setValueAtTime(param.value, now);
        param.linearRampToValueAtTime(target, now + MACRO_RAMP_S);
      } catch {
        /* a stub without ramps — the arc simply doesn't move. */
      }
    };
    ease(this.padFilter?.frequency, levels.lowpassHz);
    ease(this.noiseGain?.gain, levels.noiseGain);
    ease(this.subOut?.gain, levels.subLevel);
  }

  /* ── Bells and root drift ──────────────────────────────────────────── */

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
      this.disposeWith(shimmer, shimmer, shimmerGain);
      this.disposeWith(osc, osc, g);
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

  /** Move to a related root: build the next pad fading in and hand the current
   * one its fade-out, so the two overlap. Only the pad changes; the noise bed
   * is pitchless and stays, and the sub/pluck/bell voices read `rootHz` when
   * each one fires. */
  private driftRoot(): void {
    const ctx = this.ctx;
    const padSum = this.padSum;
    if (!ctx || !padSum || !this.playing) return;
    try {
      const stops = this.droneStops;
      this.droneStops = [];
      this.rootHz = nextRootHz(this.rootHz, this.random);
      this.startDrone(ctx, padSum, this.rootHz, true);
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
    for (const handle of [this.bellTimer, this.rootTimer, this.gridTimer, this.macroTimer]) {
      if (handle !== null) this.clearTimer(handle);
    }
    this.bellTimer = null;
    this.rootTimer = null;
    this.gridTimer = null;
    this.macroTimer = null;
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
