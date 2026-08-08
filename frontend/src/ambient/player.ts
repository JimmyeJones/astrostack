/** The Web Audio half of the ambient soundbed: turns `voicing.ts`'s decisions
 * into a running node graph.
 *
 * Shape of the graph:
 *
 *     pad (detuned saw pairs, panned) ─> lowpass ─> chorus ─┐
 *     brown-noise loop ────────────────────────────────────-┼─> duck ─┐
 *                                                                     │
 *     sparse off-grid bells ──────────────────────────────────────────┤
 *     sparse plucks ─> dry ───────────────────────────────────────────┤
 *                   └─> ping-pong delay (dotted eighth) ──────────────┤
 *                                                                     │
 *                                          bus <────────────────────-─┘
 *                                           ├─> convolver (generated IR) ─┐
 *                                           └────────── dry ─────────────-┴─> master
 *     sub pulse (on the grid, no reverb) ───────────────────────────────────> master
 *                                                                  master ─> limiter ─> out
 *
 * The bed has a **heartbeat**: a lookahead scheduler walks a 76 BPM grid and
 * places the sub pulse, its sidechain-style duck of everything above it, and the
 * occasional pluck at exact audio-clock times. Timer jitter therefore never
 * reaches the grid — the timer only decides *when to think*.
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
 *   4. **Bounded, constant node count.** The pad, chorus, delay and sub are
 *      built once and reused; only the short-lived bells and plucks allocate,
 *      and each stops itself at the end of its own decay.
 *
 * The constructor takes its `AudioContext` from an injectable factory so tests
 * can pass a stub — jsdom has no Web Audio, and asserting on rendered sound
 * isn't the point: that `resume`/`suspend` happen at the right moments is.
 */
import {
  BELL_DECAY_S,
  BELL_GAIN,
  CHORUS_DELAY_S,
  CHORUS_DEPTH_S,
  CHORUS_DRY,
  CHORUS_PAN,
  CHORUS_RATE_HZ,
  CHORUS_WET,
  DELAY_DRY,
  DELAY_FEEDBACK,
  DELAY_WET,
  DUCK_DEPTH,
  DUCK_RELEASE_S,
  FADE_SECONDS,
  LOWPASS_LFO_HZ,
  LOWPASS_SWEEP_HZ,
  MAX_BEATS_PER_TICK,
  MIN_GAIN,
  NOISE_BANDPASS_HZ,
  NOISE_GAIN,
  NOISE_LFO_HZ,
  NOISE_Q,
  NOISE_SWEEP_HZ,
  PAD_GAIN,
  PLUCK_DECAY_S,
  PLUCK_GAIN,
  REVERB_SECONDS,
  ROOT_HZ,
  SCHEDULER_TICK_MS,
  SCHEDULE_AHEAD_S,
  SUB_ATTACK_S,
  SUB_DECAY_S,
  SUB_GAIN,
  beatSeconds,
  bellFreqHz,
  brownNoise,
  dottedEighthSeconds,
  droneVoices,
  impulseResponse,
  macroFilterHz,
  macroPluckDensity,
  masterGainFor,
  nextBellGapS,
  nextRootHoldS,
  nextRootHz,
  pluckFreqHz,
  shouldPluckOnBeat,
  subPulseGainForBeat,
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
  /** 0–1 source for the un-gridded bell timing and for every pitch/density
   * choice. Injectable so a test can make the schedule deterministic. */
  random?: () => number;
  /** Injectable timers so a test can drive the bell/root/grid schedule with a
   * fake clock instead of waiting 25 real seconds. */
  setTimer?: (fn: () => void, ms: number) => number;
  clearTimer?: (handle: number) => void;
}

export class AmbientPlayer {
  private ctx: AudioContext | null = null;
  private master: GainNode | null = null;
  private bus: GainNode | null = null;
  /** Everything the sub pulse breathes against: pad + noise, but not the sub
   * itself and not the bells (a ducked bell tail reads as a fault). */
  private duck: GainNode | null = null;
  /** Input to the persistent chorus/width stage; the pad's filter connects here
   * and is the only part rebuilt on a root drift. */
  private chorusIn: GainNode | null = null;
  private pluckIn: GainNode | null = null;
  private padFilter: BiquadFilterNode | null = null;
  private subOsc: OscillatorNode | null = null;
  private subEnv: GainNode | null = null;
  private rootHz: number = ROOT_HZ[0];
  // Kept apart on purpose: a root drift tears down and rebuilds the *pad* only.
  // Folding the (pitchless, always-on) noise bed into the same list would stop
  // it on the first drift and never bring it back.
  private droneStops: Array<() => void> = [];
  private noiseStops: Array<() => void> = [];
  private bellTimer: number | null = null;
  private rootTimer: number | null = null;
  private gridTimer: number | null = null;
  /** Audio-clock time of beat 0 of the current run, and the next beat still to
   * be scheduled. Reset on every start, so the grid always begins with the fade. */
  private gridOrigin = 0;
  private nextBeat = 0;
  private startedAt = 0;
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
        // A suspended context's clock is frozen, so a restart would otherwise
        // resume the grid mid-bar minutes later. Re-anchor both clocks instead:
        // the macro arc then opens from the bottom alongside the fade-up.
        this.startedAt = this.ctx.currentTime;
        this.gridOrigin = this.ctx.currentTime;
        this.nextBeat = 0;
        this.scheduleBell();
        this.scheduleRootDrift();
        this.tickGrid();
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
    // Safety limiter: no combination of pad + noise + sub + overlapping bells,
    // plucks and delay repeats can spike, however many tails are ringing.
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

    // The breathing stage. Pad and noise pass through it; the sub that causes
    // the dip does not, so the pulse itself stays solid.
    const duck = ctx.createGain();
    duck.gain.value = 1;
    duck.connect(bus);

    this.master = master;
    this.bus = bus;
    this.duck = duck;
    this.chorusIn = this.buildChorus(ctx, duck);
    this.pluckIn = this.buildPluckDelay(ctx, bus);
    this.startDrone(ctx, this.chorusIn, this.rootHz);
    this.startSubBass(ctx, master, this.rootHz);
    this.startNoiseBed(ctx, duck);
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

  /** Two short modulated delay lines panned apart, plus a dry path. Built once
   * and kept — the pad reconnects to its input across a root drift. */
  private buildChorus(ctx: AudioContext, dest: AudioNode): GainNode {
    const input = ctx.createGain();
    input.gain.value = 1;

    const dry = ctx.createGain();
    dry.gain.value = CHORUS_DRY;
    input.connect(dry);
    dry.connect(dest);

    for (let i = 0; i < CHORUS_DELAY_S.length; i++) {
      const base = CHORUS_DELAY_S[i];
      const delay = ctx.createDelay(1);
      delay.delayTime.value = base;
      // A slow LFO on the delay time is the whole effect: the pitch wobbles by
      // a few cents against the dry path, which reads as width, not vibrato.
      const lfo = ctx.createOscillator();
      lfo.frequency.value = CHORUS_RATE_HZ[i];
      const depth = ctx.createGain();
      depth.gain.value = CHORUS_DEPTH_S;
      lfo.connect(depth);
      depth.connect(delay.delayTime);
      lfo.start();
      const pan = ctx.createStereoPanner();
      pan.pan.value = CHORUS_PAN[i];
      const wet = ctx.createGain();
      wet.gain.value = CHORUS_WET;
      input.connect(delay);
      delay.connect(pan);
      pan.connect(wet);
      wet.connect(dest);
    }
    return input;
  }

  /** The genre's signature trail: a dotted-eighth stereo delay with the two
   * sides cross-fed, so each repeat crosses the field as it recedes. Built once;
   * the plucks are what feed it. */
  private buildPluckDelay(ctx: AudioContext, dest: AudioNode): GainNode {
    const input = ctx.createGain();
    input.gain.value = 1;

    const dry = ctx.createGain();
    dry.gain.value = DELAY_DRY;
    input.connect(dry);
    dry.connect(dest);

    const time = dottedEighthSeconds();
    const left = ctx.createDelay(2);
    left.delayTime.value = time;
    const right = ctx.createDelay(2);
    right.delayTime.value = time;

    const send = ctx.createGain();
    send.gain.value = DELAY_WET;
    input.connect(send);
    send.connect(left);

    // Cross-feed: left's output feeds right and vice versa. Feedback is well
    // under 1, so the loop always decays.
    const fbL = ctx.createGain();
    fbL.gain.value = DELAY_FEEDBACK;
    const fbR = ctx.createGain();
    fbR.gain.value = DELAY_FEEDBACK;
    left.connect(fbL);
    fbL.connect(right);
    right.connect(fbR);
    fbR.connect(left);

    const panL = ctx.createStereoPanner();
    panL.pan.value = -0.85;
    const panR = ctx.createStereoPanner();
    panR.pan.value = 0.85;
    left.connect(panL);
    right.connect(panR);
    panL.connect(dest);
    panR.connect(dest);
    return input;
  }

  private startDrone(ctx: AudioContext, dest: AudioNode, rootHz: number): void {
    const pad = ctx.createGain();
    pad.gain.value = PAD_GAIN;
    const lowpass = ctx.createBiquadFilter();
    lowpass.type = "lowpass";
    lowpass.frequency.value = macroFilterHz(ctx.currentTime - this.startedAt);
    pad.connect(lowpass);
    lowpass.connect(dest);

    // Very slow LFO across the cutoff — the pad's "breathing in the dark". It
    // adds to whatever the macro arc has scheduled on the same parameter.
    const lfo = ctx.createOscillator();
    lfo.frequency.value = LOWPASS_LFO_HZ;
    const lfoGain = ctx.createGain();
    lfoGain.gain.value = LOWPASS_SWEEP_HZ / 2;
    lfo.connect(lfoGain);
    lfoGain.connect(lowpass.frequency);
    lfo.start();

    const stops: Array<() => void> = [
      () => lfo.stop(),
      // The old chain is dead once its oscillators stop; unhook it so a
      // multi-hour session doesn't accumulate one filter chain per drift.
      () => { lowpass.disconnect(); pad.disconnect(); },
    ];
    for (const voice of droneVoices(rootHz)) {
      const g = ctx.createGain();
      g.gain.value = voice.gain;
      const panner = ctx.createStereoPanner();
      panner.pan.value = voice.pan;
      // Each voice swells on its own clock, so the chord never sits still.
      const swell = ctx.createOscillator();
      swell.frequency.value = 1 / voice.swellPeriodS;
      const swellDepth = ctx.createGain();
      swellDepth.gain.value = voice.gain * 0.45;
      swell.connect(swellDepth);
      swellDepth.connect(g.gain);
      g.connect(panner);
      panner.connect(pad);
      // A detuned *pair* per voice — supersaw-lite. Halved, so a pair is no
      // louder than the single oscillator it replaces.
      for (const side of [-1, 1]) {
        const osc = ctx.createOscillator();
        osc.type = voice.type;
        osc.frequency.value = voice.freqHz;
        osc.detune.value = voice.detuneCents + side * voice.pairDetuneCents;
        const half = ctx.createGain();
        half.gain.value = 0.5;
        osc.connect(half);
        half.connect(g);
        osc.start();
        stops.push(() => osc.stop());
      }
      // An oscillator's phase can't be set, so de-phase the swells by starting
      // each a fraction of its own period late; until then the voice just holds
      // its base gain, which is inaudible as a difference.
      swell.start(ctx.currentTime + voice.swellPhase * voice.swellPeriodS);
      stops.push(() => swell.stop());
    }
    this.droneStops = stops;
    this.padFilter = lowpass;
  }

  /** A single persistent sine an octave under the pad root, silent until the
   * grid envelopes it. Persistent on purpose: a stopped oscillator can never be
   * restarted, so a root drift ramps its pitch instead of rebuilding it. */
  private startSubBass(ctx: AudioContext, dest: AudioNode, rootHz: number): void {
    const osc = ctx.createOscillator();
    osc.type = "sine";
    osc.frequency.value = rootHz / 2;
    const env = ctx.createGain();
    env.gain.value = MIN_GAIN;
    osc.connect(env);
    env.connect(dest);
    osc.start();
    this.subOsc = osc;
    this.subEnv = env;
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

  /** The heartbeat. Places every grid event that falls inside the lookahead
   * window at an exact audio-clock time, nudges the macro arc, and re-arms. */
  private tickGrid(): void {
    const ctx = this.ctx;
    if (!ctx || !this.playing) return;
    try {
      const beat = beatSeconds();
      // A background tab's timers are throttled to roughly once a minute. Skip
      // the beats that went by while we weren't thinking rather than firing a
      // minute of pulses at once: the same grid, just re-joined at the next
      // beat that is still ahead of us.
      const behind = ctx.currentTime - (this.gridOrigin + this.nextBeat * beat);
      if (behind > SCHEDULE_AHEAD_S) this.nextBeat += Math.ceil(behind / beat);
      const horizon = ctx.currentTime + SCHEDULE_AHEAD_S;
      let placed = 0;
      while (placed < MAX_BEATS_PER_TICK
             && this.gridOrigin + this.nextBeat * beat < horizon) {
        const at = Math.max(ctx.currentTime, this.gridOrigin + this.nextBeat * beat);
        this.scheduleBeat(this.nextBeat, at);
        this.nextBeat++;
        placed++;
      }
      this.rampMacroArc(ctx);
    } catch {
      /* one bad tick must never take the bed down — the next one re-tries. */
    }
    this.gridTimer = this.setTimer(() => this.tickGrid(), SCHEDULER_TICK_MS);
  }

  /** Ease the pad's cutoff toward where the multi-minute arc has got to. The
   * fast LFO is connected as an *input* to the same parameter, so it keeps
   * sweeping on top of whatever this schedules. */
  private rampMacroArc(ctx: AudioContext): void {
    const filter = this.padFilter;
    if (!filter) return;
    const target = macroFilterHz(ctx.currentTime - this.startedAt);
    // Ramp over slightly more than a tick, so consecutive ticks overlap into
    // one continuous move rather than a staircase.
    filter.frequency.linearRampToValueAtTime(
      target, ctx.currentTime + (SCHEDULER_TICK_MS / 1000) * 1.5,
    );
  }

  private scheduleBeat(beatIndex: number, at: number): void {
    const amount = subPulseGainForBeat(beatIndex);
    if (amount > 0) {
      this.pulseSub(at, amount);
      this.duckUnder(at, amount);
    }
    const density = this.ctx ? macroPluckDensity(this.ctx.currentTime - this.startedAt) : 1;
    if (shouldPluckOnBeat(beatIndex, this.random, density)) this.firePluck(at);
  }

  private pulseSub(at: number, amount: number): void {
    const env = this.subEnv;
    if (!env) return;
    const g = env.gain;
    g.setValueAtTime(MIN_GAIN, at);
    g.exponentialRampToValueAtTime(Math.max(MIN_GAIN, SUB_GAIN * amount), at + SUB_ATTACK_S);
    g.exponentialRampToValueAtTime(MIN_GAIN, at + SUB_DECAY_S);
  }

  /** The scheduled dip that makes the bed breathe against the pulse. Linear on
   * purpose: this parameter passes through 1, where an exponential ramp's shape
   * would be wrong (and it may never touch zero, which it doesn't). */
  private duckUnder(at: number, amount: number): void {
    const duck = this.duck;
    if (!duck) return;
    const g = duck.gain;
    g.setValueAtTime(1, at);
    g.linearRampToValueAtTime(1 - DUCK_DEPTH * amount, at + SUB_ATTACK_S);
    g.linearRampToValueAtTime(1, at + DUCK_RELEASE_S);
  }

  private firePluck(at: number): void {
    const ctx = this.ctx;
    const dest = this.pluckIn;
    if (!ctx || !dest) return;
    try {
      const osc = ctx.createOscillator();
      osc.type = "triangle";
      osc.frequency.value = pluckFreqHz(this.rootHz, this.random);
      const g = ctx.createGain();
      g.gain.setValueAtTime(MIN_GAIN, at);
      g.gain.exponentialRampToValueAtTime(PLUCK_GAIN, at + 0.008);
      g.gain.exponentialRampToValueAtTime(MIN_GAIN, at + PLUCK_DECAY_S);
      osc.connect(g);
      g.connect(dest);
      osc.start(at);
      osc.stop(at + PLUCK_DECAY_S);
    } catch {
      /* a pluck that fails to sound must never take the bed down with it. */
    }
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
   * building the next one. The pitchless noise bed stays, and the sub follows
   * by ramping its pitch rather than being rebuilt. */
  private driftRoot(): void {
    const ctx = this.ctx;
    const dest = this.chorusIn;
    if (!ctx || !dest || !this.playing) return;
    try {
      const stops = this.droneStops;
      this.droneStops = [];
      this.rootHz = nextRootHz(this.rootHz, this.random);
      this.startDrone(ctx, dest, this.rootHz);
      if (this.subOsc) {
        // Slide rather than jump: a sub that steps pitch is the one thing in
        // this bed you would actually hear happen.
        this.subOsc.frequency.linearRampToValueAtTime(
          this.rootHz / 2, ctx.currentTime + FADE_SECONDS,
        );
      }
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
    if (this.gridTimer !== null) this.clearTimer(this.gridTimer);
    this.bellTimer = null;
    this.rootTimer = null;
    this.gridTimer = null;
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
