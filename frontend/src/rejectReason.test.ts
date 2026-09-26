import { describe, it, expect } from "vitest";
import {
  EXACT_LABELS, HANDLED_PREFIXES, METRIC_LABEL, rejectReasonLabel,
} from "./rejectReason";

describe("rejectReasonLabel", () => {
  it("names the app's own decisions in words, not in their internal code", () => {
    // Both of these used to fall through to the generic `auto:` branch and
    // reach the owner's frames table as "Auto: seestar_output" / "Auto:
    // file_missing" — the identifier, verbatim, on a beginner's screen.
    expect(rejectReasonLabel("auto:seestar_output")).toBe("Seestar's own stack");
    expect(rejectReasonLabel("auto:file_missing")).toBe("File missing");
    for (const reason of ["auto:seestar_output", "auto:file_missing"]) {
      expect(rejectReasonLabel(reason)).not.toContain("_");
      expect(rejectReasonLabel(reason)).not.toContain(":");
    }
  });

  it("still answers everything it answered before", () => {
    expect(rejectReasonLabel("user")).toBe("Manual reject");
    expect(rejectReasonLabel("bulk:streaked")).toBe("Streaked (bulk)");
    expect(rejectReasonLabel("bulk:trailed")).toBe("Trailed (bulk)");
    expect(rejectReasonLabel("auto:streak")).toBe("Auto: streak");
    expect(rejectReasonLabel("auto:grade:fwhm_px")).toBe("Auto-grade: FWHM");
    expect(rejectReasonLabel("qc:sky_adu_median")).toBe("QC: sky level");
    expect(rejectReasonLabel("bulk:star_count")).toBe("Worst star count (bulk)");
    expect(rejectReasonLabel("qc_error_final:ValueError: nope")).toBe("QC error");
    expect(rejectReasonLabel("solve_failed:no stars")).toBe("Plate-solve failed");
  });

  it("shows a reason that is already a sentence exactly as written", () => {
    // The stacker writes this one for this badge (`stacker.run_stack`'s
    // bad-plate-solve exclusion), so the fall-through is the right answer.
    const sentence = "bad plate-solve (footprint far from the group)";
    expect(rejectReasonLabel(sentence)).toBe(sentence);
  });

  it("every declared namespace really is handled", () => {
    // HANDLED_PREFIXES is what `tests/test_reject_reason_labels.py` checks the
    // engine's namespaces against, so a prefix listed here that the function
    // does not actually recognise would silently excuse a raw code.
    for (const prefix of HANDLED_PREFIXES) {
      const raw = `${prefix}zzz_unknown`;
      expect(rejectReasonLabel(raw), prefix).not.toBe(raw);
    }
  });

  it("keeps the exact table and the function in step", () => {
    for (const [reason, label] of Object.entries(EXACT_LABELS)) {
      expect(rejectReasonLabel(reason)).toBe(label);
    }
  });

  it("falls back to the metric's own name rather than dropping it", () => {
    // An engine metric the label table has not heard of must still say which
    // metric fired — "Auto-grade: " with nothing after it says nothing.
    expect(rejectReasonLabel("auto:grade:some_new_metric"))
      .toBe("Auto-grade: some_new_metric");
    expect(Object.keys(METRIC_LABEL)).toContain("transparency_score");
  });
});
