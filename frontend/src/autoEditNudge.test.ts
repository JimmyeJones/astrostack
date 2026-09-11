import { describe, expect, it } from "vitest";
import { autoEditNudge } from "./autoEditNudge";

describe("autoEditNudge", () => {
  it("offers the switch when the scan stacked targets and finished none", () => {
    const s = autoEditNudge({
      autoEditOnAutostack: false, autoStacked: 4, autoEdited: 0,
    });
    expect(s).toContain("stacked 4 of your targets");
    // The *behaviour*, not a promise about the result.
    expect(s).toContain("Auto-process");
    // And the way back out, in the offer rather than as a follow-up: the owner
    // made "easy to override" the condition of turning this on at all.
    expect(s).toContain("never written over");
  });

  it("counts only what was left unfinished, not everything stacked", () => {
    // A target finished by its own per-target preference is finished — blaming
    // the switch for it would over-claim.
    const s = autoEditNudge({
      autoEditOnAutostack: false, autoStacked: 5, autoEdited: 3,
    });
    expect(s).toContain("stacked 2 of your targets");
  });

  it("reads as one picture in the singular", () => {
    const s = autoEditNudge({
      autoEditOnAutostack: false, autoStacked: 1, autoEdited: 0,
    });
    expect(s).toContain("stacked one of your targets");
    expect(s).toContain("It is the plain stack");
    expect(s).not.toContain("1 of your targets");
  });

  it("says nothing when auto-editing is already on", () => {
    expect(autoEditNudge({
      autoEditOnAutostack: true, autoStacked: 4, autoEdited: 0,
    })).toBeNull();
  });

  it("says nothing while the setting is unknown", () => {
    // An unresolved query must not flash an offer onto every Dashboard load.
    expect(autoEditNudge({ autoStacked: 4, autoEdited: 0 })).toBeNull();
  });

  it("says nothing when the scan stacked nothing itself", () => {
    // With auto-stack off there is nothing for this switch to finish, and
    // `autoStackNudge` is the note that fits that install.
    expect(autoEditNudge({
      autoEditOnAutostack: false, autoStacked: 0, autoEdited: 0,
    })).toBeNull();
  });

  it("says nothing when it finished everything it stacked", () => {
    expect(autoEditNudge({
      autoEditOnAutostack: false, autoStacked: 3, autoEdited: 3,
    })).toBeNull();
  });

  it("says nothing against a backend that doesn't send the tallies", () => {
    // Absent is "nothing to say", never "zero stacked and zero finished, so
    // complain" — and never a negative left-over count.
    expect(autoEditNudge({ autoEditOnAutostack: false })).toBeNull();
    expect(autoEditNudge({
      autoEditOnAutostack: false, autoStacked: 2, autoEdited: 9,
    })).toBeNull();
  });

  it("survives junk tallies rather than printing one", () => {
    // The tallies come off a job record the app wrote months ago; a shape an
    // older build wrote must read as "nothing to say".
    expect(autoEditNudge({
      autoEditOnAutostack: false,
      autoStacked: Number.NaN, autoEdited: Number.NaN,
    })).toBeNull();
    expect(autoEditNudge({
      autoEditOnAutostack: false, autoStacked: -3, autoEdited: 0,
    })).toBeNull();
    // A fractional count would otherwise reach the sentence verbatim.
    expect(autoEditNudge({
      autoEditOnAutostack: false, autoStacked: 2.7, autoEdited: 0,
    })).toContain("stacked 2 of your targets");
  });
});
