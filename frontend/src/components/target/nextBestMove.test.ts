import { describe, it, expect } from "vitest";
import {
  nextBestMove,
  integrationBars,
  LOCATE_MIN_UNSOLVED,
  SHORT_INTEGRATION_S,
  DEEP_INTEGRATION_S,
  type NextBestMoveKind,
} from "./nextBestMove";
import { integrationReadiness, type ReadinessLevel } from "../../readiness";

const HOUR = 60 * 60;

describe("nextBestMove", () => {
  it("returns null when nothing has been stacked yet", () => {
    expect(nextBestMove({})).toBeNull();
    expect(nextBestMove({ nFramesUsed: null })).toBeNull();
    expect(nextBestMove({ nFramesUsed: undefined })).toBeNull();
  });

  it("flags plate-solve as the top lever when a real share of subs are unsolved", () => {
    // 30 used, 30 unsolved → half the session left out.
    const tip = nextBestMove({ nFramesUsed: 30, nUnsolved: 30, integrationS: 5 * HOUR });
    expect(tip?.kind).toBe("locate");
    // Names the honest counts and points at the fix.
    expect(tip?.phrase).toContain("30 of your 60");
    expect(tip?.phrase.toLowerCase()).toContain("star database");
  });

  it("does not flag locate for just a stray unsolved sub or two", () => {
    // 40 used, 2 unsolved → below the count floor; falls through to depth advice.
    const tip = nextBestMove({ nFramesUsed: 40, nUnsolved: LOCATE_MIN_UNSOLVED - 1, integrationS: 2 * HOUR });
    expect(tip?.kind).not.toBe("locate");
  });

  it("does not flag locate when unsolved is a tiny fraction even if above the count floor", () => {
    // 100 used, 4 unsolved → 4/104 < 25%; not the top lever.
    const tip = nextBestMove({ nFramesUsed: 100, nUnsolved: 4, integrationS: 2 * HOUR });
    expect(tip?.kind).not.toBe("locate");
  });

  it("flags a thin stack (add more subs) when very few frames combined", () => {
    const single = nextBestMove({ nFramesUsed: 1 });
    expect(single?.kind).toBe("thin");
    expect(single?.phrase).toContain("1 sub");
    const thin = nextBestMove({ nFramesUsed: 3 });
    expect(thin?.kind).toBe("thin");
    expect(thin?.phrase).toContain("3 subs");
  });

  it("prioritises locate over thin when both apply", () => {
    // 3 used, 20 unsolved → thin AND mostly-unsolved; locate is the higher lever.
    const tip = nextBestMove({ nFramesUsed: 3, nUnsolved: 20 });
    expect(tip?.kind).toBe("locate");
  });

  it("advises a refocus when a healthy stack came out softer than usual", () => {
    const tip = nextBestMove({
      nFramesUsed: 40,
      integrationS: 2 * HOUR,
      softStars: { currentFwhmPx: 4.5, typicalFwhmPx: 3.0 },
    });
    expect(tip?.kind).toBe("soft");
    expect(tip?.phrase).toContain("4.5 px");
    expect(tip?.phrase).toContain("3.0 px");
    expect(tip?.phrase.toLowerCase()).toContain("refocus");
  });

  it("fires the soft rung even when integration time is unknown", () => {
    const tip = nextBestMove({
      nFramesUsed: 40,
      integrationS: null,
      softStars: { currentFwhmPx: 5.0, typicalFwhmPx: 3.0 },
    });
    expect(tip?.kind).toBe("soft");
  });

  it("prioritises locate and thin over soft-stars", () => {
    const soft = { currentFwhmPx: 5.0, typicalFwhmPx: 3.0 };
    // A thin stack that's also soft → thin outranks soft.
    expect(nextBestMove({ nFramesUsed: 2, softStars: soft })?.kind).toBe("thin");
    // Mostly-unsolved AND soft → locate is still the top lever.
    expect(nextBestMove({ nFramesUsed: 30, nUnsolved: 30, softStars: soft })?.kind).toBe("locate");
  });

  it("prefers the refocus nudge over add-time advice when both apply", () => {
    // Healthy count, under an hour, AND soft stars → soft outranks integration.
    const tip = nextBestMove({
      nFramesUsed: 40,
      integrationS: 18 * 60,
      softStars: { currentFwhmPx: 5.0, typicalFwhmPx: 3.0 },
    });
    expect(tip?.kind).toBe("soft");
  });

  it("advises more time for a healthy stack under an hour", () => {
    const tip = nextBestMove({ nFramesUsed: 40, integrationS: 18 * 60 }); // 18 min
    expect(tip?.kind).toBe("integration");
    expect(tip?.phrase).toContain("18 min so far");
  });

  it("stays silent when integration time is unknown for a healthy stack", () => {
    // No total_exposure_s → don't guess depth advice.
    expect(nextBestMove({ nFramesUsed: 40, integrationS: null })).toBeNull();
  });

  it("gives an encouraging note for a decent (1–3h) result", () => {
    const tip = nextBestMove({ nFramesUsed: 120, integrationS: 2 * HOUR });
    expect(tip?.kind).toBe("good");
    expect(tip?.phrase.toLowerCase()).toContain("solid result");
  });

  it("stays silent once a stack is genuinely deep and healthy", () => {
    expect(nextBestMove({ nFramesUsed: 300, integrationS: DEEP_INTEGRATION_S })).toBeNull();
    expect(nextBestMove({ nFramesUsed: 300, integrationS: 5 * HOUR })).toBeNull();
  });

  it("respects the ladder ordering across the boundaries", () => {
    // Just over the thin cap and just under the short-integration cap → integration.
    const tip = nextBestMove({ nFramesUsed: 5, integrationS: SHORT_INTEGRATION_S - 1 });
    expect(tip?.kind).toBe("integration");
    // At exactly the short cap → not short anymore, and below deep → good.
    const good = nextBestMove({ nFramesUsed: 50, integrationS: SHORT_INTEGRATION_S });
    expect(good?.kind).toBe("good");
  });

  it("treats a stray negative/NaN input as missing rather than erroring", () => {
    expect(nextBestMove({ nFramesUsed: -1 })).toBeNull();
    expect(nextBestMove({ nFramesUsed: 40, nUnsolved: NaN, integrationS: 2 * HOUR })?.kind).toBe("good");
  });

  // Every "how much have I got?" rung is a claim about the part of the picture
  // the beginner is looking at. On a mosaic the target's totals are not that,
  // and always in the flattering direction — the owner shoots 5x5 and 12x8
  // rasters, where a "3 h" target is under two minutes a panel.
  describe("a mosaic's rungs are asked of one part of the picture", () => {
    it("nudges more time on a mosaic the totals called genuinely deep", () => {
      // 9 panels, 4.5 h total → 30 min a panel. Read off the total this cleared
      // DEEP_INTEGRATION_S and the card said nothing at all.
      expect(nextBestMove({
        nFramesUsed: 540, integrationS: 4.5 * HOUR,
      })).toBeNull();  // …which is the bug, stated.
      const tip = nextBestMove({
        nFramesUsed: 540, integrationS: 4.5 * HOUR, fieldFulls: 9,
      });
      expect(tip?.kind).toBe("integration");
      // Names both figures, so it reconciles with the "4.5 h" the same page prints.
      expect(tip?.phrase).toContain("4.5 h is spread across about 9 fields of sky");
      expect(tip?.phrase).toContain("30 min so far");
    });

    it("calls a mosaic one sub deep everywhere thin, not healthy", () => {
      const tip = nextBestMove({
        nFramesUsed: 9, integrationS: 9 * 60, fieldFulls: 9,
      });
      expect(tip?.kind).toBe("thin");
      expect(tip?.phrase).toContain("about 1 sub on it");
      // Without the figure the same run reads as a healthy 9-frame stack.
      expect(nextBestMove({ nFramesUsed: 9, integrationS: 9 * 60 })?.kind)
        .toBe("integration");
    });

    it("still goes quiet on a mosaic that is genuinely deep per panel", () => {
      // 2x2, 12 h total → 3 h a panel: deep by the bar that means something.
      expect(nextBestMove({
        nFramesUsed: 1440, integrationS: 12 * HOUR, fieldFulls: 4,
      })).toBeNull();
    });

    it("leaves the locate rung on the honest counts, which are not per-pixel", () => {
      // "Only N of your M subs were located" is arithmetic about the session,
      // not about a pixel — dividing it would print a number nothing else shows.
      const tip = nextBestMove({
        nFramesUsed: 30, nUnsolved: 30, integrationS: HOUR, fieldFulls: 9,
      });
      expect(tip?.kind).toBe("locate");
      expect(tip?.phrase).toContain("Only 30 of your 60 subs");
    });

    it("is byte-for-byte the single-field ladder for any non-mosaic figure", () => {
      for (const input of [
        { nFramesUsed: 3, integrationS: 5 * 60 },
        { nFramesUsed: 40, integrationS: 18 * 60 },
        { nFramesUsed: 120, integrationS: 2 * HOUR },
        { nFramesUsed: 300, integrationS: 5 * HOUR },
      ]) {
        const plain = nextBestMove(input);
        for (const ff of [null, undefined, 0, 0.5, 1]) {
          expect(nextBestMove({ ...input, fieldFulls: ff })).toEqual(plain);
        }
      }
    });
  });

  // The two time rungs are the readiness card's own ladder boundaries (0.25 and
  // 0.75 of the goal) read at its default 4 h goal — which is why they were
  // right for a nebula and wrong for everything else. These pin the two
  // surfaces to one answer, so neither can drift away from the other again.
  describe("how much is enough is asked of the object, not of a nebula", () => {
    it("keeps today's 1 h / 3 h bars for a target with no catalogue match", () => {
      expect(integrationBars(undefined)).toEqual({
        shortS: SHORT_INTEGRATION_S, deepS: DEEP_INTEGRATION_S,
      });
      for (const t of [null, "", "Nebula", "Emission Nebula", "Supernova Remnant"]) {
        expect(integrationBars(t)).toEqual({
          shortS: SHORT_INTEGRATION_S, deepS: DEEP_INTEGRATION_S,
        });
      }
    });

    it("never tells a star cluster it is a galaxy or a nebula", () => {
      // Fails before: the phrase asserted "Galaxies and nebulae reward hours"
      // about every object, including the one bucket the app's own
      // target_difficulty calls uniformly easy.
      const tip = nextBestMove({
        nFramesUsed: 20, integrationS: 10 * 60, objectType: "Open Cluster",
      });
      expect(tip?.kind).toBe("integration");
      expect(tip?.phrase.toLowerCase()).not.toContain("galaxies and nebulae");
      expect(tip?.phrase.toLowerCase()).toContain("clusters come up quickly");
      // …and it asks for the rest of a night, not "another clear night or two".
      expect(tip?.phrase.toLowerCase()).not.toContain("night or two");
    });

    it("stops nagging a cluster that the readiness card calls nearly there", () => {
      // 50 min on an open cluster: goal 1.5 h → ratio 0.56, i.e. "solid" on the
      // readiness card. Fails before: the ladder said "add more time — another
      // clear night or two", two inches under a badge reading "usually looks
      // good in well under an hour".
      const tip = nextBestMove({
        nFramesUsed: 60, integrationS: 50 * 60, objectType: "Open Cluster",
      });
      expect(tip?.kind).toBe("good");
    });

    it("stops calling a galaxy at 1.2 h a finished job", () => {
      // Goal 6 h → ratio 0.2, "a good start" on the readiness card. Fails
      // before: the ladder's universal 1 h bar called it "a solid result —
      // plenty of subs went in".
      const tip = nextBestMove({
        nFramesUsed: 150, integrationS: 1.2 * HOUR, objectType: "Galaxy",
      });
      expect(tip?.kind).toBe("integration");
      expect(tip?.phrase.toLowerCase()).toContain("galaxies and nebulae");
    });

    it("agrees with the readiness card on every bucket, at every depth", () => {
      // The property the three cases above are instances of, stated once: the
      // rung the coaching line picks and the verdict the card prints are the
      // same judgement, so a beginner can hold both at the same time.
      const expected: Record<ReadinessLevel, NextBestMoveKind | null> = {
        starting: "integration",  // under 0.25 of the goal
        solid: "good",            // 0.25 – 0.75
        close: null,              // 0.75 – 1: deep enough to stop nudging
        plenty: null,
      };
      for (const type of ["Galaxy", "Emission Nebula", "Open Cluster", "Quasar", null]) {
        for (const hours of [0.1, 0.3, 0.6, 1.2, 2, 3.5, 5, 8]) {
          const seconds = hours * HOUR;
          const card = integrationReadiness(seconds, type);
          const tip = nextBestMove({
            // A healthy frame count and no other lever, so the time rungs are
            // the only ones that can fire.
            nFramesUsed: 200, integrationS: seconds, objectType: type,
          });
          expect(
            [type, hours, tip?.kind ?? null],
          ).toEqual([type, hours, expected[card!.level]]);
        }
      }
    });

    it("follows the goal when the vetted difficulty sharpens it", () => {
      // The same agreement property, asked across the *other* axis the goal
      // moves on. A curated verdict changes what "enough" means, and a ladder
      // that kept the per-type bars would contradict the card again — this time
      // on M31 and M33 rather than on a star cluster.
      const expected: Record<ReadinessLevel, NextBestMoveKind | null> = {
        starting: "integration",
        solid: "good",
        close: null,
        plenty: null,
      };
      for (const level of ["easy", "moderate", "challenging"]) {
        const difficulty = { level, curated: true };
        for (const type of ["Galaxy", "Emission Nebula", "Quasar"]) {
          for (const hours of [0.3, 1.2, 2, 3.5, 5, 8, 12]) {
            const seconds = hours * HOUR;
            const card = integrationReadiness(seconds, type, null, null, difficulty);
            const tip = nextBestMove({
              nFramesUsed: 200, integrationS: seconds, objectType: type,
              difficulty,
            });
            expect(
              [level, type, hours, tip?.kind ?? null],
            ).toEqual([level, type, hours, expected[card!.level]]);
          }
        }
      }
    });

    it("moves the bars with the curated verdict, and only with it", () => {
      // Fails before: `integrationBars` took the per-type goal whatever the
      // catalog knew about the object, so an easy galaxy's rungs sat at a
      // challenging one's.
      const easy = integrationBars("Galaxy", { level: "easy", curated: true });
      const hard = integrationBars("Galaxy", { level: "challenging", curated: true });
      expect(easy.shortS).toBeCloseTo(0.25 * 3 * HOUR, 6);
      expect(hard.shortS).toBeCloseTo(0.25 * 9 * HOUR, 6);
      // The cluster type rule restates the bucket, so it moves nothing…
      expect(integrationBars("Open Cluster", { level: "easy", curated: false }))
        .toEqual(integrationBars("Open Cluster"));
      // …and so does every shape of "no verdict".
      for (const d of [null, undefined, { level: "easy" }]) {
        expect(integrationBars("Galaxy", d as never))
          .toEqual(integrationBars("Galaxy"));
      }
    });

    it("asks the same question of one panel of a mosaic", () => {
      // The card scales the goal by field-fulls; this ladder divides the light
      // by them instead. Same ratio, so the agreement above must survive it.
      const seconds = 4 * HOUR;
      const fieldFulls = 4;
      const card = integrationReadiness(seconds, "Galaxy", null, fieldFulls);
      expect(card?.level).toBe("starting");
      expect(
        nextBestMove({
          nFramesUsed: 400, integrationS: seconds, fieldFulls,
          objectType: "Galaxy",
        })?.kind,
      ).toBe("integration");
    });
  });
});
