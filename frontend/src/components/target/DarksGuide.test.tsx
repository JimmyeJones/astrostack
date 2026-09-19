import { MantineProvider } from "@mantine/core";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import {
  DarksGuide, darkSpecGains, darkSpecLengths, darkSpecPerSettingNote, formatDarkSpec,
} from "./DarksGuide";

describe("formatDarkSpec", () => {
  it("joins exposure and gain into a match-these-numbers phrase", () => {
    expect(formatDarkSpec({ exposure_s: 10, gain: 80 })).toBe("10 s at gain 80");
  });
  it("keeps one decimal for a fractional exposure and rounds gain", () => {
    expect(formatDarkSpec({ exposure_s: 2.5, gain: 79.6 })).toBe("2.5 s at gain 80");
  });
  it("uses whatever single value is known", () => {
    expect(formatDarkSpec({ exposure_s: 30, gain: null })).toBe("30 s");
    expect(formatDarkSpec({ exposure_s: null, gain: 100 })).toBe("gain 100");
  });
  it("returns null when nothing usable is known (generic fallback)", () => {
    expect(formatDarkSpec({ exposure_s: null, gain: null })).toBeNull();
    expect(formatDarkSpec({ exposure_s: 0, gain: null })).toBeNull();
    expect(formatDarkSpec(null)).toBeNull();
    expect(formatDarkSpec(undefined)).toBeNull();
  });
});

function renderGuide(
  spec: Parameters<typeof DarksGuide>[0]["spec"],
  backgroundClean?: boolean | null,
) {
  return render(
    <MantineProvider>
      <DarksGuide spec={spec} backgroundClean={backgroundClean} />
    </MantineProvider>,
  );
}

describe("DarksGuide", () => {
  it("expands the three steps with the target's own numbers pre-filled", () => {
    renderGuide({ exposure_s: 10, gain: 80 });
    fireEvent.click(screen.getByText("How to add darks →"));
    expect(
      screen.getByText(/same settings as your subs — 10 s at gain 80/),
    ).toBeInTheDocument();
    // Cap-the-scope step and the drop-folder step are present too.
    expect(screen.getByText(/Cap the scope/)).toBeInTheDocument();
    expect(screen.getByText(/AstroStack builds the master dark/)).toBeInTheDocument();
  });

  it("keeps its toggle hugging its own text, not stretched across the column", () => {
    // It is a real <button>, and a Stack stretches its children — so it filled
    // the note's whole width and took the browser's centred button text with it,
    // leaving one centred line in an otherwise left-aligned note (measured 707 px
    // wide on a desktop; 109 px after). jsdom has no layout, so the test holds the
    // mechanism that stops it.
    renderGuide({ exposure_s: 10, gain: 80 });
    expect(screen.getByRole("button", { name: "How to add darks →" }))
      .toHaveStyle({ alignSelf: "flex-start" });
  });

  it("falls back to generic wording when exposure/gain are unknown", () => {
    renderGuide({ exposure_s: null, gain: null });
    fireEvent.click(screen.getByText("How to add darks →"));
    expect(
      screen.getByText(/same exposure and gain as your subs\./),
    ).toBeInTheDocument();
  });
});


// A target is one *folder*, never one exposure. Shoot it at 10 s on a bright
// night and 30 s on a faint one and the median is 20 s — which this guide would
// then offer under the words "at the same settings as your subs".

describe("a target shot at more than one sub length", () => {
  it("names both lengths, never the median between them", () => {
    expect(formatDarkSpec({ exposure_s: 20, gain: 80, exposures_s: [10, 30] }))
      .toBe("10 s and 30 s at gain 80");
  });
  it("lists three the way a sentence does", () => {
    expect(formatDarkSpec({ exposure_s: 20, gain: null, exposures_s: [10, 20, 30] }))
      .toBe("10 s, 20 s and 30 s");
  });
  it("adds the sentence that says one dark can't cover both", () => {
    const note = darkSpecPerSettingNote({
      exposure_s: 20, gain: 80, exposures_s: [10, 30],
    });
    expect(note).toContain("2 different sub lengths");
    expect(note).toContain("a set of darks at each");
  });
  it("shows both lengths in the rendered step, and not the median", async () => {
    renderGuide({ exposure_s: 20, gain: 80, exposures_s: [10, 30] });
    fireEvent.click(screen.getByRole("button", { name: /How to add darks/ }));
    const step = await screen.findByText(/Shoot about 20–30 dark frames/);
    expect(step.textContent).toContain("10 s and 30 s at gain 80");
    expect(step.textContent).toContain("a set of darks at each");
    expect(step.textContent).not.toContain("20 s at gain 80");
  });
});

describe("the ordinary single-length target is untouched", () => {
  it("keeps the exact sentence it had", () => {
    expect(formatDarkSpec({ exposure_s: 10, gain: 80, exposures_s: [10] }))
      .toBe("10 s at gain 80");
    expect(darkSpecPerSettingNote({ exposure_s: 10, gain: 80, exposures_s: [10] }))
      .toBe("");
  });
  it("falls back to the median against an older backend with no set", () => {
    expect(formatDarkSpec({ exposure_s: 10, gain: 80 })).toBe("10 s at gain 80");
    expect(darkSpecPerSettingNote({ exposure_s: 10, gain: 80 })).toBe("");
  });
  it("ignores an unusable length rather than printing it", () => {
    expect(darkSpecLengths({ exposure_s: 10, gain: null, exposures_s: [0, -1] }))
      .toEqual([10]);
    expect(darkSpecLengths({ exposure_s: null, gain: null, exposures_s: [] }))
      .toEqual([]);
  });
});

// The guide sits directly under the "How's my stack?" calibration note, and that
// note now reads the run's measured background σ before it says anything about
// grain (`seestack.stackhealth.background_reads_clean`). The lead sentence here
// used to re-assert the magnitude the note had just withdrawn.
describe("DarksGuide — the lead sentence agrees with the note above it", () => {
  it("drops the noisy-image claim once the background measures clean", () => {
    renderGuide({ exposure_s: 10, gain: 80 }, true);
    fireEvent.click(screen.getByText("How to add darks →"));
    expect(screen.queryByText(/single biggest cleanup/)).not.toBeInTheDocument();
    // It says what darks *do* here rather than restating the note's verdict:
    // sigma is a whole-canvas figure, and the note above scopes it on a mosaic
    // ("across most of it"), so an unqualified copy down here would reintroduce
    // exactly the over-claim this pair of fixes removed.
    expect(
      screen.getByText(/mostly means hot pixels rather than less grain/),
    ).toBeInTheDocument();
    expect(screen.queryByText(/background already measures clean/)).toBeNull();
    // The how-to itself is untouched — this changes one sentence, not the offer.
    expect(screen.getByText(/Cap the scope/)).toBeInTheDocument();
    expect(
      screen.getByText(/same settings as your subs — 10 s at gain 80/),
    ).toBeInTheDocument();
  });

  it("keeps today's wording when the background is grainy, unmeasured, or the "
    + "backend is older", () => {
    for (const flag of [false, null, undefined] as const) {
      const { unmount } = renderGuide({ exposure_s: 10, gain: 80 }, flag);
      fireEvent.click(screen.getByText("How to add darks →"));
      expect(screen.getByText(/single biggest cleanup/)).toBeInTheDocument();
      expect(
        screen.queryByText(/mostly means hot pixels/),
      ).not.toBeInTheDocument();
      unmount();
    }
  });
});

describe("the gain half of 'at the same settings as your subs'", () => {
  it("names every gain the target was shot at, never their midpoint", () => {
    // A gain is a *setting*: 80 and 200 have a median of 140, which — unlike a
    // sub length no frame happened to use — is a number no camera can be dialled
    // to at all, printed under an instruction to dial it in.
    expect(
      formatDarkSpec({ exposure_s: 10, gain: 140, gains: [80, 200] }),
    ).toBe("10 s at gain 80 and 200");
    expect(
      formatDarkSpec({ exposure_s: 10, gain: 80, gains: [80] }),
    ).toBe("10 s at gain 80");
  });

  it("asks for a set of darks per gain, and says why nothing rescales one", () => {
    const note = darkSpecPerSettingNote({
      exposure_s: 10, gain: 140, exposures_s: [10], gains: [80, 200],
    });
    expect(note).toContain("2 different gains");
    expect(note).toContain("a set of darks at each");
    expect(note).toContain("nothing rescales it");
  });

  it("gives one instruction, not two, when both settings moved", () => {
    const note = darkSpecPerSettingNote({
      exposure_s: 20, gain: 140, exposures_s: [10, 30], gains: [80, 200],
    });
    expect(note).toContain("2 different sub lengths and 2 different gains");
    expect(note).toContain("each combination you used");
    // One sentence: the reader gets a single instruction to follow.
    expect(note.match(/You shot this target/g)).toHaveLength(1);
  });

  it("is silent on the ordinary target, and against an older backend", () => {
    for (const spec of [
      { exposure_s: 10, gain: 80, exposures_s: [10], gains: [80] },
      { exposure_s: 10, gain: 80 }, // older backend: no sets at all
    ]) {
      expect(darkSpecPerSettingNote(spec)).toBe("");
      expect(formatDarkSpec(spec)).toBe("10 s at gain 80");
    }
  });

  it("reads the set when there is one and the single value otherwise", () => {
    expect(darkSpecGains({ exposure_s: 10, gain: 140, gains: [80, 200] }))
      .toEqual([80, 200]);
    expect(darkSpecGains({ exposure_s: 10, gain: 80 })).toEqual([80]);
    // Gain 0 is a real setting and must survive; a negative never is.
    expect(darkSpecGains({ exposure_s: 10, gain: null, gains: [0, -5] }))
      .toEqual([0]);
    expect(darkSpecGains({ exposure_s: 10, gain: null, gains: [] })).toEqual([]);
    expect(darkSpecGains(null)).toEqual([]);
  });

  it("shows both gains in the rendered step, and not the midpoint", async () => {
    renderGuide({ exposure_s: 10, gain: 140, exposures_s: [10], gains: [80, 200] });
    fireEvent.click(screen.getByRole("button", { name: /How to add darks/ }));
    const step = await screen.findByText(/Shoot about 20–30 dark frames/);
    expect(step.textContent).toContain("10 s at gain 80 and 200");
    expect(step.textContent).not.toContain("gain 140");
    expect(step.textContent).toContain("a set of darks at each");
  });
});
