import { describe, expect, it } from "vitest";
import {
  calibrationCard, drizzleCard, outliersCard, PICTURE_CARD_FIELDS, pictureCards,
  REJECT_KEYS, savedRejection, trimCard,
} from "./picturesMade";
import { HINTS } from "../../routes/Settings";

describe("How pictures are made — the four cards", () => {
  it("are the spec's four, in its order, each on a real labelled setting", () => {
    const cards = pictureCards({});
    expect(cards.map((c) => c.id)).toEqual(["outliers", "drizzle", "trim", "calibration"]);
    for (const c of cards) {
      // Every switch is one of the page's registered settings, so `lbl()` stamps
      // it and the "nothing was removed" guard can see it.
      expect(Object.keys(HINTS)).toContain(c.field);
      expect(PICTURE_CARD_FIELDS).toContain(c.field);
      expect(c.was).not.toBe("");
    }
  });

  it("speak plain words outside the Was: line", () => {
    for (const c of pictureCards({})) {
      const text = [c.title, c.desc, c.value, c.note, c.switchLabel].join(" ");
      expect(text).not.toMatch(/\b(QC|ASTAP|FOV|pixfrac|sigma|κ|kappa|drizzle)\b/i);
    }
  });

  it("matches the fresh-install defaults the server ships", () => {
    // auto_drizzle and auto_crop_border default on (read as `!== false`, so an
    // absent key is on); the other two default off (`webapp/config.py`).
    const [out, driz, trim, cal] = pictureCards({});
    expect([out.checked, driz.checked, trim.checked, cal.checked]).toEqual([false, true, true, false]);
    expect(out.value).toBe("Automatic");
    expect(driz.value).toBe("Automatic when it pays off");
    expect(trim.value).toBe("On");
    expect(cal.value).toBe("Only when I pick them");
  });
});

describe("Remove satellites & hot pixels — true of walkaway.apply_unattended_rejection", () => {
  it("names the same three keys the server reads as a choice", () => {
    expect([...REJECT_KEYS]).toEqual(["auto_reject", "sigma_clip", "min_max_reject"]);
  });

  it("is automatic while the stacking defaults name no method", () => {
    expect(savedRejection({ default_stack_options: { drizzle: true } })).toBeNull();
    expect(outliersCard({ default_stack_options: { quality_weighted: true } }).value)
      .toBe("Automatic");
  });

  it("is the saved method once the defaults name one, and says so", () => {
    const c = outliersCard({ default_stack_options: { sigma_clip: true } });
    expect(c.value).toBe("Your choice: drop the odd ones out");
    expect(c.note).toMatch(/can miss a lone satellite trail/);
    const mm = outliersCard({ default_stack_options: { min_max_reject: true, sigma_clip: true } });
    // min/max takes precedence in `combine_method`, and works on a thin stack.
    expect(mm.value).toBe("Your choice: drop the brightest and darkest");
    expect(mm.note).not.toMatch(/thin night/);
  });

  it("reads an absent sigma_clip as StackOptions' own default — on", () => {
    // A saved `auto_reject: false` alone is a choice, and it still clips.
    expect(savedRejection({ default_stack_options: { auto_reject: false } }))
      .toBe("drop the odd ones out");
    expect(savedRejection({ default_stack_options: { sigma_clip: false } })).toBe("none");
    expect(outliersCard({ default_stack_options: { sigma_clip: false } }).value)
      .toBe("Off — your stacking defaults");
  });

  it("is automatic again, over the saved method, with the switch on", () => {
    const c = outliersCard({
      auto_reject_on_unattended: true, default_stack_options: { sigma_clip: true },
    });
    expect(c.checked).toBe(true);
    expect(c.value).toBe("Automatic");
    expect(c.note).toMatch(/even over the one saved/);
  });

  it("is automatic when the defaults themselves ask for automatic", () => {
    expect(outliersCard({ default_stack_options: { auto_reject: true } }).value).toBe("Automatic");
  });
});

describe("Sharper, bigger picture — true of walkaway.apply_auto_drizzle", () => {
  it("is off when the switch is off and nothing is saved", () => {
    const c = drizzleCard({ auto_drizzle: false });
    expect(c.value).toBe("Off");
    expect(c.overruled).toBeNull();
  });

  it("says a saved drizzle wins, on or off, and the switch does nothing", () => {
    const on = drizzleCard({ auto_drizzle: true, default_stack_options: { drizzle: true } });
    expect(on.value).toBe("Always — your stacking defaults");
    expect(on.overruled?.text).toMatch(/no effect/);
    const off = drizzleCard({ auto_drizzle: true, default_stack_options: { drizzle: false } });
    expect(off.value).toBe("Never — your stacking defaults");
    expect(off.overruled).not.toBeNull();
  });

  it("hands the choice back by dropping only the saved drizzle key", () => {
    const form = {
      auto_drizzle: false,
      default_stack_options: { drizzle: true, quality_weighted: true, drizzle_scale: 2 },
    };
    const patch = drizzleCard(form).overruled!.patch;
    expect(patch).toEqual({
      default_stack_options: { quality_weighted: true, drizzle_scale: 2 },
      auto_drizzle: true,
    });
    // The form it was built from is untouched — a preview until Save.
    expect(form.default_stack_options).toHaveProperty("drizzle", true);
    expect(drizzleCard({ ...form, ...patch }).value).toBe("Automatic when it pays off");
  });

  it("survives a malformed default_stack_options", () => {
    expect(drizzleCard({ default_stack_options: null }).value).toBe("Automatic when it pays off");
    expect(savedRejection({ default_stack_options: [] as unknown })).toBeNull();
  });
});

describe("Trim and calibration", () => {
  it("reads each switch both ways", () => {
    expect(trimCard({ auto_crop_border: false }).value).toBe("Off");
    expect(trimCard({ auto_crop_border: true }).value).toBe("On");
    expect(calibrationCard({ auto_bind_calibration: true }).value).toBe("Automatic");
    // Off does not ask anybody anything — the mockup's "Ask me" was not true.
    expect(calibrationCard({ auto_bind_calibration: false }).value).not.toMatch(/ask/i);
  });

  it("promises only a confident match, never a forced one", () => {
    // `pipeline._confident_master_binding` leaves a stack uncalibrated rather
    // than bind a master it is unsure of.
    expect(calibrationCard({ auto_bind_calibration: true }).note).toMatch(/No confident match, no calibration/);
  });
});
