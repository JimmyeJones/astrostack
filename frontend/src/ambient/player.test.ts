import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { FakeAudioContext } from "./fakeAudio";
import { AmbientPlayer, ambientPlayer, ambientSupported, resetAmbientPlayer } from "./player";
import {
  DELAY_FEEDBACK,
  DUCK_DEPTH,
  FADE_SECONDS,
  MASTER_GAIN_CEILING,
  MIN_GAIN,
  SUB_ATTACK_S,
  SUB_GAIN,
  beatSeconds,
  dottedEighthSeconds,
} from "./voicing";

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

function mkPlayer(volume = 0.5, random: () => number = () => 0.5) {
  const ctx = new FakeAudioContext();
  const clock = new FakeClock();
  const player = new AmbientPlayer(volume, {
    contextFactory: () => ctx as unknown as AudioContext,
    random,
    setTimer: clock.set,
    clearTimer: clock.clear,
  });
  return { player, ctx, clock };
}

/** Every gain ramp the graph has scheduled, in the order they were made. */
function allRamps(ctx: FakeAudioContext) {
  return ctx.gains.flatMap((g) => g.gain.ramps);
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
    const ramped = ctx.gains.flatMap((g) => g.gain.ramps);
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
    const target = MASTER_GAIN_CEILING * 0.25;
    const before = allRamps(ctx);
    expect(before.some((r) => Math.abs(r.target - target) < 1e-9)).toBe(false);
    player.setVolume(0.25);
    const after = allRamps(ctx);
    expect(after.length).toBeGreaterThan(before.length);
    // The new ramp is the master's, aimed at the new volume — asserted by
    // target rather than by position, because the grid schedules envelopes of
    // its own on other gains while the bed plays.
    const ramp = after.find((r) => Math.abs(r.target - target) < 1e-9);
    expect(ramp).toBeDefined();
    // …and it gets there over the fade, so the change is never a jump.
    expect(ramp!.at).toBeCloseTo(FADE_SECONDS, 6);
  });

  it("is remembered for the next start when stopped", async () => {
    const { player, ctx } = mkPlayer(1);
    player.setVolume(0.5);
    await player.start();
    const ramps = ctx.gains.flatMap((g) => g.gain.ramps);
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
});

describe("the heartbeat", () => {
  it("pulses the sub on the very first downbeat, without waiting for a timer", async () => {
    const { player, ctx } = mkPlayer();
    await player.start();
    // start() runs the first scheduler tick itself: beat 0 is a downbeat, so
    // the sub envelope is already scheduled at full strength.
    const pulse = allRamps(ctx).find((r) => Math.abs(r.target - SUB_GAIN) < 1e-9);
    expect(pulse).toBeDefined();
    // …and it decays again rather than droning.
    expect(allRamps(ctx).some((r) => r.target === MIN_GAIN)).toBe(true);
  });

  it("breathes: the bed dips under the pulse and comes all the way back", async () => {
    const { player, ctx } = mkPlayer();
    await player.start();
    const ramps = allRamps(ctx);
    const dip = ramps.findIndex((r) => Math.abs(r.target - (1 - DUCK_DEPTH)) < 1e-9);
    expect(dip).toBeGreaterThanOrEqual(0);
    const back = ramps.slice(dip + 1).find((r) => r.target === 1);
    expect(back).toBeDefined();
    // The duck is a dip, never a mute and never a boost.
    expect(1 - DUCK_DEPTH).toBeGreaterThan(0.5);
    for (const r of ramps) expect(r.target).toBeLessThanOrEqual(1);
  });

  it("places grid events on the audio clock, not on the timer that scheduled them", async () => {
    const { player, ctx, clock } = mkPlayer();
    // The grid is anchored to the clock reading at start, wherever that is.
    ctx.currentTime = 6;
    await player.start();
    const origin = 6;
    const beat = beatSeconds();
    // Let the clock run on and tick again, so a later downbeat is placed too.
    ctx.currentTime = origin + beat * 3.5;
    clock.flush();
    const at = allRamps(ctx)
      .filter((r) => Math.abs(r.target - SUB_GAIN) < 1e-9)
      .map((r) => r.at);
    expect(at.length).toBeGreaterThan(1);
    for (const t of at) {
      // Each pulse's attack sits a fixed offset after a whole beat of the grid,
      // and never in the past — timer jitter can't reach the pulse.
      const beats = (t - SUB_ATTACK_S - origin) / beat;
      expect(Math.abs(beats - Math.round(beats))).toBeLessThan(1e-6);
      expect(t).toBeGreaterThanOrEqual(origin);
    }
  });

  it("re-joins the grid after a throttled background tab instead of bursting", async () => {
    const { player, ctx, clock } = mkPlayer();
    await player.start();
    const before = allRamps(ctx).filter((r) => Math.abs(r.target - SUB_GAIN) < 1e-9).length;
    // A background tab gets its timers throttled to about once a minute; that
    // is ~76 beats of grid that went by unscheduled.
    ctx.currentTime = 60;
    clock.flush();
    const after = allRamps(ctx).filter((r) => Math.abs(r.target - SUB_GAIN) < 1e-9).length;
    // At most the handful of downbeats inside the lookahead window — not a
    // minute's worth fired at once.
    expect(after - before).toBeLessThanOrEqual(1);
    expect(player.state).toBe("playing");
  });

  it("keeps re-arming the grid, and stops dead when the bed stops", async () => {
    const { player, clock } = mkPlayer();
    await player.start();
    const armed = clock.pending.size;
    clock.flush();
    expect(clock.pending.size).toBeGreaterThanOrEqual(armed - 1);
    const stopping = player.stop();
    clock.flush();
    await stopping;
    expect(clock.pending.size).toBe(0);
  });

  it("fires sparse plucks into a dotted-eighth ping-pong delay", async () => {
    // A low random source makes every eligible beat pluck, so one tick is enough.
    const { player, ctx, clock } = mkPlayer(0.5, () => 0.01);
    await player.start();
    const oscBefore = ctx.oscillators.length;
    // Move the clock on so a non-downbeat falls inside the lookahead window.
    ctx.currentTime = 5;
    clock.flush();
    expect(ctx.oscillators.length).toBeGreaterThan(oscBefore);

    const dotted = dottedEighthSeconds();
    const pingPong = ctx.delays.filter((d) => Math.abs(d.delayTime.value - dotted) < 1e-9);
    expect(pingPong).toHaveLength(2); // one per side, cross-fed
    for (const g of ctx.gains) {
      // Feedback must always decay — a loop at or above unity runs away.
      if (Math.abs(g.gain.value - DELAY_FEEDBACK) < 1e-9) expect(g.gain.value).toBeLessThan(1);
    }
    expect(DELAY_FEEDBACK).toBeLessThan(1);
  });

  it("is wide: the pad is panned across the field and chorused", async () => {
    const { player, ctx } = mkPlayer();
    await player.start();
    const pans = ctx.panners.map((p) => p.pan.value);
    expect(pans.some((p) => p < -0.05)).toBe(true);
    expect(pans.some((p) => p > 0.05)).toBe(true);
    // Short modulated delay lines are the chorus; long ones are the echo.
    expect(ctx.delays.some((d) => d.delayTime.value > 0 && d.delayTime.value < 0.05)).toBe(true);
  });

  it("keeps the sub alive across a root drift, sliding its pitch instead", async () => {
    const { player, ctx, clock } = mkPlayer();
    await player.start();
    // An octave under the 55 Hz root, and the only oscillator down there: the
    // LFOs are all well under 1 Hz and the pad starts at the root itself.
    const subs = ctx.oscillators.filter(
      (o) => o.frequency.value >= 20 && o.frequency.value <= 40,
    );
    expect(subs).toHaveLength(1);
    const sub = subs[0];
    clock.flush(); // bell + root drift + grid
    // A stopped oscillator can never be restarted, so the sub must be ramped,
    // not rebuilt — otherwise the bottom end vanishes for the rest of the night.
    expect(sub.stopped).toBe(0);
    expect(sub.frequency.ramps.length).toBeGreaterThan(0);
    expect(player.state).toBe("playing");
  });

  it("holds its node count steady while it plays — an hours-long tab must not grow", async () => {
    const { player, ctx, clock } = mkPlayer();
    await player.start();
    const persistent = ctx.oscillators.length + ctx.gains.length
      + ctx.delays.length + ctx.panners.length;
    // Ten scheduler ticks with the clock standing still place no new events.
    for (let i = 0; i < 10; i++) {
      const pending = [...clock.pending.entries()];
      clock.pending.clear();
      // Only the grid tick, so bells/drift don't muddy the count.
      for (const [, fn] of pending.slice(-1)) fn();
    }
    const after = ctx.oscillators.length + ctx.gains.length
      + ctx.delays.length + ctx.panners.length;
    expect(after).toBe(persistent);
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
