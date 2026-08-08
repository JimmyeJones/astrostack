import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { FakeAudioContext, FakeCompressor } from "./fakeAudio";
import { AmbientPlayer, ambientPlayer, ambientSupported, resetAmbientPlayer } from "./player";
import {
  CHORUS_TAPS,
  DELAY_FEEDBACK,
  FADE_SECONDS,
  MACRO_PERIOD_S,
  MASTER_GAIN_CEILING,
  MIN_GAIN,
  ROOT_CROSSFADE_S,
  SUB_BEATS,
  barSeconds,
  beatSeconds,
  delaySeconds,
  macroLevels,
} from "./voicing";

/** The master is the one gain feeding the safety limiter. Found by shape rather
 * than by creation order, so the graph can grow without stranding the test. */
function masterGain(ctx: FakeAudioContext) {
  const master = ctx.gains.find((g) => g.connected.some((n) => n instanceof FakeCompressor));
  expect(master).toBeDefined();
  return master!;
}

/** Timers we drive by hand, so a 25 s bell gap costs a test nothing. */
class FakeClock {
  private next = 1;
  pending = new Map<number, () => void>();
  set = (fn: () => void, ms: number): number => {
    const h = this.next++;
    this.pending.set(h, fn);
    this.delays.set(h, ms);
    return h;
  };
  clear = (h: number): void => {
    this.pending.delete(h);
  };
  delays = new Map<number, number>();
  /** Fire every timer currently pending (not the ones they schedule). */
  flush(): void {
    const now = [...this.pending.entries()];
    this.pending.clear();
    for (const [, fn] of now) fn();
  }
}

function mkPlayer(volume = 0.5) {
  const ctx = new FakeAudioContext();
  const clock = new FakeClock();
  const player = new AmbientPlayer(volume, {
    contextFactory: () => ctx as unknown as AudioContext,
    random: () => 0.5,
    setTimer: clock.set,
    clearTimer: clock.clear,
  });
  return { player, ctx, clock };
}

afterEach(() => resetAmbientPlayer());

describe("AmbientPlayer.start", () => {
  it("starts stopped — nothing sounds until asked", () => {
    const { player, ctx } = mkPlayer();
    expect(player.state).toBe("stopped");
    // The context isn't even created before the (user-gesture) start.
    expect(ctx.resumes).toBe(0);
  });

  it("resumes the context and reports playing", async () => {
    const { player, ctx } = mkPlayer();
    await expect(player.start()).resolves.toBe(true);
    expect(ctx.resumes).toBe(1);
    expect(ctx.state).toBe("running");
    expect(player.state).toBe("playing");
  });

  it("fades up to the volume's master gain rather than jumping", async () => {
    const { player, ctx } = mkPlayer(1);
    await player.start();
    // The master gain is the one ramped toward the ceiling over the fade.
    const ramped = masterGain(ctx).gain.ramps;
    const target = ramped.find((r) => Math.abs(r.target - MASTER_GAIN_CEILING) < 1e-9);
    expect(target).toBeDefined();
    expect(target!.at).toBeCloseTo(FADE_SECONDS, 6);
  });

  it("builds the graph once — a second start reuses it", async () => {
    const { player, ctx } = mkPlayer();
    await player.start();
    const oscCount = ctx.oscillators.length;
    expect(oscCount).toBeGreaterThan(4); // pad voices + swells + LFOs
    await player.start();
    expect(ctx.oscillators.length).toBe(oscCount);
    expect(ctx.resumes).toBe(2);
  });

  it("stays off and says so when the browser blocks playback", async () => {
    const { player, ctx } = mkPlayer();
    ctx.resumeRejects = true;
    await expect(player.start()).resolves.toBe(false);
    expect(player.state).toBe("stopped");
  });
});

describe("AmbientPlayer.stop", () => {
  it("fades toward silence and then suspends — not just mutes", async () => {
    const { player, ctx, clock } = mkPlayer();
    await player.start();
    const stopping = player.stop();
    // Reported off immediately, so the button never lags the user.
    expect(player.state).toBe("stopped");
    expect(ctx.suspends).toBe(0); // still fading
    clock.flush(); // the fade timer
    await stopping;
    expect(ctx.suspends).toBe(1);
    expect(ctx.state).toBe("suspended");
  });

  it("never ramps gain to exactly zero", async () => {
    const { player, ctx, clock } = mkPlayer();
    await player.start();
    const stopping = player.stop();
    clock.flush();
    await stopping;
    for (const g of ctx.gains) {
      for (const r of g.gain.ramps) expect(r.target).toBeGreaterThanOrEqual(MIN_GAIN);
    }
  });

  it("lets a restart during the fade win — it must not suspend underneath it", async () => {
    const { player, ctx, clock } = mkPlayer();
    await player.start();
    const stopping = player.stop();
    await player.start();
    clock.flush();
    await stopping;
    expect(ctx.suspends).toBe(0);
    expect(player.state).toBe("playing");
  });

  it("is a no-op before anything ever started", async () => {
    const { player, ctx } = mkPlayer();
    await player.stop();
    expect(player.state).toBe("stopped");
    expect(ctx.suspends).toBe(0);
  });
});

describe("AmbientPlayer.setVolume", () => {
  it("ramps immediately while playing", async () => {
    const { player, ctx } = mkPlayer(1);
    await player.start();
    const master = masterGain(ctx);
    const before = master.gain.ramps.length;
    player.setVolume(0.25);
    const after = master.gain.ramps;
    expect(after.length).toBeGreaterThan(before);
    expect(after[after.length - 1].target).toBeCloseTo(MASTER_GAIN_CEILING * 0.25, 6);
  });

  it("is remembered for the next start when stopped", async () => {
    const { player, ctx } = mkPlayer(1);
    player.setVolume(0.5);
    await player.start();
    const ramps = masterGain(ctx).gain.ramps;
    expect(ramps.some((r) => Math.abs(r.target - MASTER_GAIN_CEILING * 0.5) < 1e-9)).toBe(true);
  });
});

describe("the running bed", () => {
  it("keeps ringing bells for as long as it plays", async () => {
    const { player, ctx, clock } = mkPlayer();
    await player.start();
    const before = ctx.oscillators.length;
    clock.flush(); // bell + root-drift timers
    expect(ctx.oscillators.length).toBeGreaterThan(before);
    // …and re-armed itself rather than falling silent after one ping.
    expect(clock.pending.size).toBeGreaterThan(0);
  });

  it("stops scheduling once stopped", async () => {
    const { player, clock } = mkPlayer();
    await player.start();
    const stopping = player.stop();
    clock.flush();
    await stopping;
    expect(clock.pending.size).toBe(0);
  });

  it("keeps the noise bed alive across a root drift", async () => {
    const { player, ctx, clock } = mkPlayer();
    await player.start();
    const noise = ctx.bufferSources;
    expect(noise).toHaveLength(1);
    expect(noise[0].started).toBe(1);
    const padBefore = ctx.oscillators.length;
    // Both timers fire: the drift tears the pad down and rebuilds it on a new
    // root. The pitchless noise loop must NOT be torn down with it — a stopped
    // AudioBufferSourceNode can never be restarted, so the bed would silently
    // lose its texture for the rest of the session.
    clock.flush();
    expect(ctx.oscillators.length).toBeGreaterThan(padBefore);
    expect(ctx.bufferSources[0].stopped).toBe(0);
    expect(player.state).toBe("playing");
  });

  it("crossfades a root drift instead of cutting the pad off", async () => {
    const { player, ctx, clock } = mkPlayer();
    await player.start();
    const padOscs = ctx.oscillators.filter((o) => o.started > 0).length;
    const gainsBefore = ctx.gains.length;
    clock.flush(); // fires the root drift
    const drifted = ctx.oscillators.filter((o) => o.started > 0).length;
    expect(drifted).toBeGreaterThan(padOscs);
    // Nothing is stopped on the spot: cutting a live sawtooth stack clicks.
    expect(ctx.oscillators.every((o) => o.stopped === 0 || o.stopTimes.some((t) => t !== undefined)))
      .toBe(true);
    // The outgoing pad's group is on its way down…
    const at = (r: { at: number }) => Math.abs(r.at - ROOT_CROSSFADE_S) < 1e-9;
    const out = ctx.gains.slice(0, gainsBefore)
      .filter((g) => g.gain.ramps.some((r) => r.target === MIN_GAIN && at(r)));
    expect(out).toHaveLength(1);
    // …while the incoming one, built by the drift, comes up over the same span.
    const incoming = ctx.gains.slice(gainsBefore)
      .filter((g) => g.gain.ramps.some((r) => r.target === 1 && at(r)));
    expect(incoming).toHaveLength(1);
    // …and only when the fade has finished are the old voices actually stopped.
    clock.flush();
    expect(ctx.oscillators.some((o) => o.stopped > 0 && o.stopTimes.every((t) => t === undefined)))
      .toBe(true);
    expect(player.state).toBe("playing");
  });
});

/** The sub's fundamental sits an octave under the root, so its oscillators are
 * the pulse made visible: one per scheduled thump. */
function subPulseTimes(ctx: FakeAudioContext, rootHz = 55): number[] {
  return ctx.oscillators
    .filter((o) => Math.abs(o.frequency.value - rootHz / 2) < 1e-6)
    .flatMap((o) => o.startTimes.filter((t): t is number => t !== undefined))
    .sort((a, b) => a - b);
}

describe("the pulse", () => {
  it("lays the heartbeat on the grid, bars ahead of the clock", async () => {
    const { player, ctx } = mkPlayer();
    await player.start();
    const beat = beatSeconds();
    const bar = barSeconds();
    // Two bars of lookahead, each carrying the plan's two sub beats.
    expect(subPulseTimes(ctx)).toEqual([
      SUB_BEATS[0] * beat,
      SUB_BEATS[1] * beat,
      bar + SUB_BEATS[0] * beat,
      bar + SUB_BEATS[1] * beat,
    ]);
  });

  it("keeps topping the schedule up as the clock advances", async () => {
    const { player, ctx, clock } = mkPlayer();
    await player.start();
    const scheduled = subPulseTimes(ctx).length;
    ctx.currentTime = barSeconds() * 3;
    clock.flush();
    const later = subPulseTimes(ctx);
    expect(later.length).toBeGreaterThan(scheduled);
    // Still on the same grid — the new bars line up with the old ones.
    for (const t of later) {
      const beatsIn = t / beatSeconds();
      expect(Math.abs(beatsIn - Math.round(beatsIn * 2) / 2)).toBeLessThan(1e-6);
    }
  });

  it("does not fire a burst of catch-up pulses after a long suspend", async () => {
    const { player, ctx, clock } = mkPlayer();
    await player.start();
    const stopping = player.stop();
    clock.flush();
    await stopping;
    // Hours later (the tab was left open), the bed is switched back on.
    const before = subPulseTimes(ctx).length;
    ctx.currentTime = 9999;
    await player.start();
    const fresh = subPulseTimes(ctx).slice(before);
    // A couple of bars of lookahead, not the thousands of bars that "elapsed"
    // while the bed was off — and every one of them in the future.
    expect(fresh.length).toBeGreaterThan(0);
    expect(fresh.length).toBeLessThanOrEqual(SUB_BEATS.length * 4);
    for (const t of fresh) {
      expect(t).toBeGreaterThanOrEqual(9999);
      expect(t).toBeLessThan(9999 + barSeconds() * 4);
    }
  });

  it("ducks the pad under each pulse and lets it back up", async () => {
    const { player, ctx } = mkPlayer();
    await player.start();
    // The duck is the gain that dips below 1 and returns to exactly 1.
    const duck = ctx.gains.find((g) => g.gain.ramps.some((r) => r.target > 0 && r.target < 1)
      && g.gain.ramps.some((r) => r.target === 1));
    expect(duck).toBeDefined();
    const dips = duck!.gain.ramps.filter((r) => r.target < 1);
    // One dip per scheduled pulse…
    expect(dips.length).toBe(subPulseTimes(ctx).length);
    // …and it is a dip, not a gate.
    for (const dip of dips) expect(dip.target).toBeGreaterThan(0.5);
  });

  it("gives every per-bar voice a way to drop its nodes when it ends", async () => {
    const { player, ctx, clock } = mkPlayer();
    await player.start();
    ctx.currentTime = barSeconds() * 3;
    clock.flush();
    const transient = ctx.oscillators.filter((o) => o.stopTimes.some((t) => t !== undefined));
    expect(transient.length).toBeGreaterThan(0);
    // A tab open all night must not accumulate a graph: each finished voice
    // disconnects itself rather than staying reachable from the bus.
    for (const osc of transient) expect(typeof osc.onended).toBe("function");
    // …and the persistent pad/LFO oscillators are *not* given stop times.
    expect(ctx.oscillators.length).toBeGreaterThan(transient.length);
  });
});

describe("the delay and the width", () => {
  it("builds a dotted-eighth ping-pong that decays instead of building up", async () => {
    const { player, ctx } = mkPlayer();
    await player.start();
    const echo = ctx.delays.filter((d) => Math.abs(d.delayTime.value - delaySeconds()) < 1e-9);
    expect(echo).toHaveLength(2); // one line per side
    const feedback = ctx.gains.find((g) => Math.abs(g.gain.value - DELAY_FEEDBACK) < 1e-9);
    expect(feedback).toBeDefined();
    expect(DELAY_FEEDBACK).toBeLessThan(1);
    // The two taps are panned apart — that is what makes it ping-pong.
    const hard = ctx.panners.map((p) => p.pan.value).filter((v) => Math.abs(v) >= 0.8);
    expect(hard.some((v) => v < 0)).toBe(true);
    expect(hard.some((v) => v > 0)).toBe(true);
  });

  it("runs the chorus taps at their own short delays", async () => {
    const { player, ctx } = mkPlayer();
    await player.start();
    for (const tap of CHORUS_TAPS) {
      expect(ctx.delays.some((d) => Math.abs(d.delayTime.value - tap.delayS) < 1e-9)).toBe(true);
    }
  });

  it("places every pad voice somewhere in the stereo field", async () => {
    const { player, ctx } = mkPlayer();
    await player.start();
    // Chorus (2) + ping-pong (2) + one per pad voice, and never off the field.
    expect(ctx.panners.length).toBeGreaterThan(4);
    for (const p of ctx.panners) expect(Math.abs(p.pan.value)).toBeLessThanOrEqual(1);
  });
});

describe("the macro arc", () => {
  it("eases the filter and the layers toward wherever the arc has reached", async () => {
    const { player, ctx, clock } = mkPlayer();
    await player.start();
    const padFilter = ctx.filters.find((f) => f.type === "lowpass");
    expect(padFilter).toBeDefined();
    expect(padFilter!.frequency.value).toBeCloseTo(macroLevels(0).lowpassHz, 6);
    // Half a period on, the bed should be heading for its most open.
    ctx.currentTime = MACRO_PERIOD_S / 2;
    clock.flush();
    const ramps = padFilter!.frequency.ramps;
    const open = ramps[ramps.length - 1];
    expect(open).toBeDefined();
    expect(open!.target).toBeCloseTo(macroLevels(MACRO_PERIOD_S / 2).lowpassHz, 6);
  });

  it("measures the arc from the start, so a resumed bed opens from the top", async () => {
    const { player, ctx, clock } = mkPlayer();
    await player.start();
    const stopping = player.stop();
    clock.flush();
    await stopping;
    ctx.currentTime = MACRO_PERIOD_S / 2; // would be wide open on an absolute clock
    await player.start();
    const padFilter = ctx.filters.find((f) => f.type === "lowpass")!;
    const ramps = padFilter.frequency.ramps;
    expect(ramps[ramps.length - 1].target).toBeCloseTo(macroLevels(0).lowpassHz, 6);
  });
});

describe("the shared player", () => {
  beforeEach(() => resetAmbientPlayer());
  it("hands the same instance to the header toggle and the settings slider", () => {
    const ctx = new FakeAudioContext();
    const opts = { contextFactory: () => ctx as unknown as AudioContext };
    expect(ambientPlayer(0.4, opts)).toBe(ambientPlayer(0.9, opts));
  });
  it("notifies subscribers when it starts and stops", async () => {
    const { player, clock } = mkPlayer();
    let calls = 0;
    const unsubscribe = player.subscribe(() => calls++);
    await player.start();
    expect(calls).toBe(1);
    const stopping = player.stop();
    clock.flush();
    await stopping;
    expect(calls).toBe(2);
    unsubscribe();
    await player.start();
    expect(calls).toBe(2);
  });
});

describe("ambientSupported", () => {
  it("is false in an environment with no Web Audio (jsdom)", () => {
    expect(ambientSupported()).toBe(false);
  });
});
