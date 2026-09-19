import { describe, it, expect } from "vitest";
import {
  nextBestMove,
  integrationBars,
  LOCATE_MIN_UNSOLVED,
  SHORT_INTEGRATION_S,
  DEEP_INTEGRATION_S,
  FRAMING_MAX_COVERAGE,
  readinessCanvasScope,
  framingDepthFirstClause,
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

  describe("the well-done note on an unevenly deep mosaic", () => {
    // Every figure the `good` rung reaches on is a mean over the whole raster,
    // so a mosaic that is comfortably deep on average can still hold a panel
    // that is not — and the "How's my stack?" panel further down the same page
    // says so with the depths it measured off the coverage map. "Plenty of subs
    // went in" printed above "about 23 % of the picture has 3 subs where most
    // has 6 … grain only comes down with more light" is the same whole-canvas
    // substitution v0.437.3 closed for the grain projection.
    //
    // The shape of a real one: a 3x3 raster, eight panels deep and one thin, at
    // a mean per-pixel depth and per-pixel integration that clear both the thin
    // bar and the short-integration bar. `grain_verdict` is the run's own — the
    // very value the health note reads.
    const evenMosaic = {
      nFramesUsed: 900,
      integrationS: 9 * 2 * HOUR, // 2 h per pixel over 9 fields
      fieldFulls: 9,
      objectType: "Galaxy",
    };

    it("is reached at all on a mosaic this shape", () => {
      // Guards the fixture rather than the fix: if the ladder ever stopped
      // landing on `good` here, the two tests below would pass for the wrong
      // reason (see AGENTS.md §8 on fixtures that cannot exhibit their bug).
      expect(nextBestMove(evenMosaic)?.kind).toBe("good");
    });

    it("scopes its praise and names the thin part", () => {
      // Fails before: the phrase was the unscoped "This is a solid result —
      // plenty of subs went in. More time is the main thing…", which says
      // nothing about the part of the canvas the health note is about.
      const tip = nextBestMove({ ...evenMosaic, grainVerdict: "uneven" });
      expect(tip?.kind).toBe("good");
      expect(tip?.phrase).toContain("Across most of it");
      expect(tip?.phrase).toContain("thinner than the rest");
      // The prescription has to serve both endings the health note can print
      // ("another night on that panel" / "it evens out as you keep shooting").
      expect(tip?.phrase).toContain("more passes over the same mosaic");
      // …and it must not claim the whole picture is done.
      expect(tip?.phrase).not.toContain("This is a solid result");
    });

    it("stops prescribing more passes when the thin part is a ragged edge", () => {
      // The health note withdrew "another night on that panel" on a ramping
      // canvas for the same reason: more passes do not narrow an outline whose
      // width is the spread of the pointings.
      const tip = nextBestMove({
        ...evenMosaic, grainVerdict: "uneven", grainRegion: "spread",
      });
      expect(tip?.kind).toBe("good");
      expect(tip?.phrase).toContain("Across most of it");
      expect(tip?.phrase).toContain("ragged outer edge");
      expect(tip?.phrase).toContain("cropping it away");
      expect(tip?.phrase).not.toContain("more passes over the same mosaic");
    });

    it("keeps the panel phrase for a plateau and for a backend that says nothing", () => {
      const panel = nextBestMove({
        ...evenMosaic, grainVerdict: "uneven", grainRegion: "panel",
      });
      expect(nextBestMove({ ...evenMosaic, grainVerdict: "uneven" }))
        .toEqual(panel);
      expect(panel?.phrase).toContain("more passes over the same mosaic");
      expect(panel?.phrase).not.toContain("ragged outer edge");
    });

    it("leaves every other verdict exactly as it was", () => {
      // Null, absent, a single field's None, and an older backend that sends
      // nothing all keep today's wording byte for byte — as does a *measured*
      // verdict that is not "uneven".
      const base = nextBestMove(evenMosaic);
      for (const v of [null, undefined, "", "flat", "check"]) {
        expect(nextBestMove({ ...evenMosaic, grainVerdict: v })).toEqual(base);
      }
    });

    it("never displaces a louder lever", () => {
      // The verdict only reaches the last rung, so an uneven mosaic that is also
      // thin, or losing its subs to plate-solving, still gets the bigger lever.
      expect(
        nextBestMove({ ...evenMosaic, nFramesUsed: 18, grainVerdict: "uneven" })
          ?.kind,
      ).toBe("thin");
      expect(
        nextBestMove({ ...evenMosaic, nUnsolved: 600, grainVerdict: "uneven" })
          ?.kind,
      ).toBe("locate");
      // …and a genuinely deep uneven mosaic stays silent, as it did before: the
      // health note is the surface that measures it, and repeating it here would
      // be the duplication the thin-stack suppression exists to avoid.
      expect(
        nextBestMove({
          ...evenMosaic, integrationS: 9 * 6 * HOUR, grainVerdict: "uneven",
        }),
      ).toBeNull();
    });
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

    it("never asks a night or two of a target it calls easy", () => {
      // Photographed on the bundled M42 sample by the dogfood pass: the
      // coaching card said "Galaxies and nebulae reward hours, so another clear
      // night or two on this target", the object card below it said "It usually
      // looks good in well under an hour", and the readiness card between them
      // quoted a goal of ~2 h. Those are the *same* words the cluster case above
      // was fixed for — `target_difficulty`'s `easy` verdict — and every
      // curated-easy nebula and galaxy prints them, not only clusters.
      //
      // Fails before: the phrase asked for "another clear night or two".
      const easy = { level: "easy", curated: true };
      const tip = nextBestMove({
        nFramesUsed: 6, integrationS: 60, objectType: "Nebula", difficulty: easy,
      });
      expect(tip?.kind).toBe("integration");
      expect(tip?.phrase.toLowerCase()).not.toContain("night or two");
      expect(tip?.phrase.toLowerCase()).not.toContain("galaxies and nebulae");
      expect(tip?.phrase).toContain("This one comes up quickly for a Seestar");
      // An easy *galaxy* (M31, goal 3 h) reads the same way — the contradiction
      // is the badge's, not the bucket's.
      const m31 = nextBestMove({
        nFramesUsed: 60, integrationS: 20 * 60, objectType: "Galaxy",
        difficulty: easy,
      });
      expect(m31?.kind).toBe("integration");
      expect(m31?.phrase.toLowerCase()).not.toContain("night or two");
    });

    it("still rewards hours on a target its own badge calls challenging", () => {
      // The other side, and the reason this is keyed on the verdict rather than
      // flattened: M33's badge says it "rewards a darker sky and several hours",
      // so "another clear night or two" is the true sentence there and must not
      // move. Same for a moderate verdict and for no verdict at all.
      for (const difficulty of [
        { level: "challenging", curated: true },
        { level: "moderate", curated: true },
        // An *un-curated* easy — the type rule's "every cluster is easy" —
        // reaches this branch through `cluster`, not through the verdict, so a
        // non-cluster carrying it changes nothing (`goalDifficultyFactor`
        // ignores it, exactly as the goal does).
        { level: "easy", curated: false },
        null,
        undefined,
      ]) {
        const tip = nextBestMove({
          nFramesUsed: 60, integrationS: 20 * 60, objectType: "Galaxy",
          difficulty,
        });
        expect(tip?.kind).toBe("integration");
        expect(tip?.phrase.toLowerCase()).toContain("galaxies and nebulae");
        expect(tip?.phrase.toLowerCase()).toContain("night or two");
      }
    });

    it("leaves the cluster sentences byte-for-byte what v0.429.2 shipped", () => {
      // The widening must not reword the case that was already right.
      const tip = nextBestMove({
        nFramesUsed: 20, integrationS: 10 * 60, objectType: "Open Cluster",
      });
      expect(tip?.phrase).toBe(
        "Add more time — 10 min so far. Clusters come up quickly, so even the " +
          "rest of one clear night on this target would clean up the background " +
          "nicely.",
      );
      const mosaic = nextBestMove({
        nFramesUsed: 20, integrationS: 40 * 60, objectType: "Open Cluster",
        fieldFulls: 4,
      });
      expect(mosaic?.phrase).toContain(
        "Clusters come up quickly, so even another pass or two over the same " +
          "mosaic would clean up the background.",
      );
    });

    it("stops promising a cleaner background over a card that measured it clean", () => {
      // The contradiction, on one page, one inch apart, both cards inline —
      // found by the v0.437.8 dogfood probe's prescriptive-claims block on the
      // bundled M42 sample: this rung said "even the rest of one clear night on
      // this target would clean up the background nicely" while the readiness
      // card's grain projection said "the background already looks clean at
      // 1 min (grain 0.001). More time from here mostly buys fainter detail
      // rather than a visibly cleaner picture."
      const tip = nextBestMove({
        nFramesUsed: 20, integrationS: 10 * 60, objectType: "Open Cluster",
        grainLevel: "clean",
      });
      // The lever is unchanged — under a quarter of the goal, more time is
      // still the advice, and it still buys real faint detail.
      expect(tip?.kind).toBe("integration");
      expect(tip?.phrase).toContain("Add more time");
      expect(tip?.phrase).not.toContain("clean up the background");
      expect(tip?.phrase).toContain("already looks clean");
      expect(tip?.phrase).toContain("fainter detail");
    });

    it("scopes that to most of an unevenly deep mosaic, and still points at the thin part", () => {
      // Same family as v0.437.3/v0.437.4: sigma is one estimate over the whole
      // canvas, so "already clean" describes the part that got the most subs.
      // The thin part really does only come down with more light — which is
      // what the health note beside it says — so the sentence keeps both.
      const tip = nextBestMove({
        nFramesUsed: 24, integrationS: 40 * 60, objectType: "Open Cluster",
        fieldFulls: 4, grainLevel: "clean", grainVerdict: "uneven",
      });
      expect(tip?.kind).toBe("integration");
      expect(tip?.phrase).toContain("across most of it the background already looks clean");
      expect(tip?.phrase).toContain("evens out the thinner part");
      expect(tip?.phrase).toContain("fainter detail");
      expect(tip?.phrase).not.toContain("would clean up the background");
    });

    it("keeps the cleaner-background promise wherever it is still true", () => {
      // Not clean yet, or never measured, or an older backend: the sentence is
      // byte-for-byte what v0.435.5 shipped. And the galaxy/nebula branch is
      // untouched in every case — it already said "faint detail".
      for (const grainLevel of ["some", "grainy", null, undefined] as const) {
        const tip = nextBestMove({
          nFramesUsed: 20, integrationS: 10 * 60, objectType: "Open Cluster",
          grainLevel,
        });
        expect(tip?.phrase).toBe(
          "Add more time — 10 min so far. Clusters come up quickly, so even " +
            "the rest of one clear night on this target would clean up the " +
            "background nicely.",
        );
      }
      const galaxy = nextBestMove({
        nFramesUsed: 150, integrationS: 1.2 * HOUR, objectType: "Galaxy",
        grainLevel: "clean",
      });
      expect(galaxy?.phrase.toLowerCase()).toContain("galaxies and nebulae");
      expect(galaxy?.phrase.toLowerCase()).toContain("faint detail");
    });

    it("never lets the measured grain change which rung fires", () => {
      // It chooses between two true reasons for one lever; it must not silence
      // or promote anything. Checked across the whole ladder.
      const cases = [
        { nFramesUsed: 3, integrationS: 60, nUnsolved: 9 },                 // locate
        { nFramesUsed: 2, integrationS: 60 },                               // thin
        { nFramesUsed: 20, integrationS: 10 * 60 },                         // integration
        { nFramesUsed: 60, integrationS: 50 * 60, objectType: "Open Cluster" }, // good
        { nFramesUsed: 300, integrationS: 10 * HOUR },                      // silent
      ];
      for (const base of cases) {
        for (const grainLevel of ["clean", "some", "grainy", null] as const) {
          expect(nextBestMove({ ...base, grainLevel })?.kind ?? null)
            .toBe(nextBestMove(base)?.kind ?? null);
        }
      }
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
  describe("the framing rung", () => {
    // The two sentences that filed this, both photographed in a browser on the
    // bundled samples: the coaching card said "add more time" / "another pass
    // or two over the same mosaic" while the framing note an inch below said
    // "shoot it in mosaic mode" / "adding more panels would capture the rest".
    const partial = (coverage: number, canvas: "frame" | "mosaic") => ({
      level: "partial",
      coverage,
      coverage_pct: Math.min(95, Math.max(5, Math.round(coverage * 20) * 5)),
      canvas,
      object_name: "Orion Nebula",
    });

    it("names the wider framing, not more time, on a single field with 15% of the object", () => {
      // Fails before: this was `integration` — "Add more time — 1 min so far…".
      const tip = nextBestMove({
        nFramesUsed: 6,
        integrationS: 60,
        framing: partial(0.15, "frame"),
      });
      expect(tip?.kind).toBe("framing");
      expect(tip?.phrase).toContain("Orion Nebula");
      expect(tip?.phrase).toContain("15%");
      expect(tip?.phrase).toContain("mosaic mode");
      // …and it says why more time is the *smaller* lever, rather than leaving
      // the reader to reconcile two cards.
      expect(tip?.phrase).toContain("can't bring the rest in");
    });

    it("names more panels, not more passes, on a mosaic with 55% of the object", () => {
      // Fails before: this was `integration`, "another pass or two over the
      // same mosaic" — the opposite instruction to the note below it.
      const tip = nextBestMove({
        nFramesUsed: 21,
        integrationS: 3 * HOUR,
        fieldFulls: 4,
        framing: partial(0.55, "mosaic"),
      });
      expect(tip?.kind).toBe("framing");
      expect(tip?.phrase).toContain("55%");
      expect(tip?.phrase).toContain("more panels");
      expect(tip?.phrase).not.toContain("mosaic mode");
    });

    it("stays out of the way of a well-framed target", () => {
      // The 95%-captured case the lead warned against: `partial` fires on any
      // object bigger than its canvas, so the coverage bar is what keeps this
      // from firing on most of a mosaic user's library.
      const tip = nextBestMove({
        nFramesUsed: 40,
        integrationS: 30 * 60,
        framing: partial(0.95, "frame"),
      });
      expect(tip?.kind).toBe("integration");
    });

    it("fires exactly at the bar and not a hair above it", () => {
      const at = nextBestMove({
        nFramesUsed: 40, integrationS: 30 * 60,
        framing: partial(FRAMING_MAX_COVERAGE, "frame"),
      });
      expect(at?.kind).toBe("framing");
      const above = nextBestMove({
        nFramesUsed: 40, integrationS: 30 * 60,
        framing: partial(FRAMING_MAX_COVERAGE + 0.01, "frame"),
      });
      expect(above?.kind).toBe("integration");
    });

    it("only ever answers a `partial` verdict", () => {
      // "Runs off the edge — it would fit whole, so re-centre it" and "add more
      // time" are jointly satisfiable in one session, so those two cards do not
      // compete and this rung must not steal the tip.
      for (const level of ["centred", "off_centre", "clipped"]) {
        const tip = nextBestMove({
          nFramesUsed: 40, integrationS: 30 * 60,
          framing: { ...partial(0.2, "frame"), level },
        });
        expect(tip?.kind).toBe("integration");
      }
    });

    it("outranks the time rungs and the well-done note, but not focus or depth", () => {
      const framing = partial(0.2, "frame");
      // Deep and healthy — silent before, now the framing lever.
      expect(nextBestMove({ nFramesUsed: 400, integrationS: 10 * HOUR, framing })?.kind)
        .toBe("framing");
      // …and above the "solid result" note.
      expect(nextBestMove({ nFramesUsed: 200, integrationS: 2 * HOUR, framing })?.kind)
        .toBe("framing");
      // A refocus tightens the wider session too, so it still comes first.
      expect(
        nextBestMove({
          nFramesUsed: 40, integrationS: 30 * 60, framing,
          softStars: { currentFwhmPx: 5.2, typicalFwhmPx: 3.8 },
        })?.kind,
      ).toBe("soft");
      // And so do the two "you have barely any usable subs" rungs.
      expect(nextBestMove({ nFramesUsed: 2, framing })?.kind).toBe("thin");
      expect(nextBestMove({ nFramesUsed: 30, nUnsolved: 30, framing })?.kind)
        .toBe("locate");
    });

    it("declines rather than re-rounding when the backend didn't send the percentage", () => {
      // An older backend serves `coverage` but no `coverage_pct`. Deriving it
      // here is how two cards come to print two percentages of one
      // measurement, so the rung simply stands down.
      const tip = nextBestMove({
        nFramesUsed: 40, integrationS: 30 * 60,
        framing: { level: "partial", coverage: 0.2, canvas: "frame" },
      });
      expect(tip?.kind).toBe("integration");
    });

    it("leaves every caller without a framing verdict byte-for-byte unchanged", () => {
      const base = { nFramesUsed: 40, integrationS: 30 * 60, objectType: "Galaxy" };
      const before = nextBestMove(base);
      for (const framing of [null, undefined, {}, { level: "partial" }]) {
        expect(nextBestMove({ ...base, framing })).toEqual(before);
      }
    });

    it("says it without a name rather than saying `undefined`", () => {
      const tip = nextBestMove({
        nFramesUsed: 40, integrationS: 30 * 60,
        framing: { ...partial(0.2, "frame"), object_name: "  " },
      });
      expect(tip?.phrase).toContain("this target");
      expect(tip?.phrase).not.toContain("undefined");
    });
  });

  describe("readinessCanvasScope", () => {
    // The readiness card prices "is it enough yet?" against the canvas in front
    // of it. On a fragment that is the canvas this ladder has just said to stop
    // shooting, so the two have to agree about *which* canvas — which is why
    // they share `framingIsFragment` rather than two copies of the constant.
    const partial = (coverage: number, canvas?: "frame" | "mosaic") => ({
      level: "partial", coverage, coverage_pct: 20, canvas,
      object_name: "Orion Nebula",
    });

    it("names the single field a measured fragment was shot on", () => {
      expect(readinessCanvasScope(partial(0.15, "frame")))
        .toBe("this single field");
    });

    it("names the mosaic when that is the canvas that fell short", () => {
      expect(readinessCanvasScope(partial(0.55, "mosaic"))).toBe("this mosaic");
    });

    it("reads an older backend's missing canvas as a single frame", () => {
      // `canvas` is additive; before it existed every verdict was about one
      // frame, which is what the framing note's own headings assume too.
      expect(readinessCanvasScope(partial(0.15))).toBe("this single field");
    });

    it("stays silent on a well-framed target, so an ordinary card is untouched", () => {
      // The 95 %-captured case: `partial` fires on any object bigger than its
      // canvas, and scoping the goal there would put a new clause on a card a
      // big-object owner sees constantly.
      expect(readinessCanvasScope(partial(0.95, "frame"))).toBeNull();
      for (const level of ["centred", "off_centre", "clipped"]) {
        expect(readinessCanvasScope({ ...partial(0.15, "frame"), level }))
          .toBeNull();
      }
      for (const v of [null, undefined, {}, { level: "partial" }]) {
        expect(readinessCanvasScope(v)).toBeNull();
      }
    });

    it("turns on exactly the bar the coaching card turns on", () => {
      // One gate, asked twice — a page that scoped the goal at a coverage the
      // coaching card stayed quiet about would be the same contradiction with
      // the cards swapped.
      expect(readinessCanvasScope(partial(FRAMING_MAX_COVERAGE, "frame")))
        .toBe("this single field");
      expect(readinessCanvasScope(partial(FRAMING_MAX_COVERAGE + 0.01, "frame")))
        .toBeNull();
    });

    it("declines a non-finite coverage rather than scoping from nothing", () => {
      expect(readinessCanvasScope({ ...partial(0.15, "frame"), coverage: NaN }))
        .toBeNull();
    });
  });

  describe("framingDepthFirstClause", () => {
    // The other side of the framing rung. Under the bar the coaching card *is*
    // the widen advice and the two agree; over it the coaching card has decided
    // the opposite and the framing note went on prescribing more panels, on the
    // same screen, for the same night. Photographed on the bundled 2x2 at 75 %.
    const partial = (coverage: number, canvas?: "frame" | "mosaic") => ({
      level: "partial", coverage, coverage_pct: Math.round(coverage * 100),
      canvas, object_name: "Orion Nebula",
    });

    it("puts depth first on a mosaic the coaching card is asking for more time on", () => {
      const clause = framingDepthFirstClause(partial(0.75, "mosaic"), "integration");
      expect(clause).toContain("Most of it is already in this picture");
      expect(clause).toContain("panels you already have");
      expect(clause).not.toContain("undefined");
    });

    it("names the single field's lever rather than the mosaic's", () => {
      // The widen advice on a single field is "shoot it in mosaic mode", so the
      // clause that tempers it must not talk about panels nobody has yet.
      const clause = framingDepthFirstClause(partial(0.8, "frame"), "good");
      expect(clause).toContain("more time on this framing");
      expect(clause).not.toContain("panels");
    });

    it("reads an older backend's missing canvas as a single frame", () => {
      expect(framingDepthFirstClause(partial(0.8), "integration"))
        .toContain("more time on this framing");
    });

    it("stays silent on a fragment, where the two cards already agree", () => {
      // Below the bar the coaching card carries the framing advice itself, so a
      // clause here would argue against the card it is meant to defer to.
      expect(framingDepthFirstClause(partial(0.2, "frame"), "framing")).toBeNull();
      expect(framingDepthFirstClause(partial(0.2, "frame"), "integration"))
        .toBeNull();
      expect(framingDepthFirstClause(partial(FRAMING_MAX_COVERAGE, "frame"), "good"))
        .toBeNull();
    });

    it("turns on exactly one step above the bar the coaching card turns on", () => {
      expect(
        framingDepthFirstClause(partial(FRAMING_MAX_COVERAGE + 0.01, "frame"), "good"),
      ).not.toBeNull();
    });

    it("never argues with a coaching tip that is not about more light", () => {
      // `locate` and `soft` name a setup fix; `framing` *is* the widen
      // prescription. Deferring to any of them would be a third opinion.
      for (const kind of ["locate", "soft", "framing"] as NextBestMoveKind[]) {
        expect(framingDepthFirstClause(partial(0.75, "mosaic"), kind)).toBeNull();
      }
    });

    it("is silent wherever there is no coaching card to defer to", () => {
      // The editor and History render this note with no `coachKind` at all.
      expect(framingDepthFirstClause(partial(0.75, "mosaic"), null)).toBeNull();
      expect(framingDepthFirstClause(partial(0.75, "mosaic"), undefined)).toBeNull();
    });

    it("says nothing about a verdict that isn't a measured `partial`", () => {
      for (const level of ["centred", "off_centre", "clipped"]) {
        expect(framingDepthFirstClause({ ...partial(0.75, "frame"), level }, "good"))
          .toBeNull();
      }
      expect(framingDepthFirstClause({ ...partial(0.75, "frame"), coverage: NaN }, "good"))
        .toBeNull();
      expect(framingDepthFirstClause({ level: "partial" }, "good")).toBeNull();
      expect(framingDepthFirstClause(null, "good")).toBeNull();
    });
  });
});
