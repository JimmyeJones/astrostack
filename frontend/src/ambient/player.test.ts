import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { FakeAudioContext } from "./fakeAudio";
import { AmbientPlayer, ambientPlayer, ambientSupported, resetAmbientPlayer } from "./player";
import { FADE_SECONDS, MASTER_GAIN_CEILING, MIN_GAIN } from "./voicing";

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
    const before = ctx.gains.flatMap((g) => g.gain.ramps).length;
    player.setVolume(0.25);
    const after = ctx.gains.flatMap((g) => g.gain.ramps);
    expect(after.length).toBeGreaterThan(before);
    expect(after[after.length - 1].target).toBeCloseTo(MASTER_GAIN_CEILING * 0.25, 6);
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
