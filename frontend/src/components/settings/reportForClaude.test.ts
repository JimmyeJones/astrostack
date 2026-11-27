import { describe, expect, it } from "vitest";
import type { Job } from "../../api/client";
import { reportDownloadable, reportStatusLine } from "./reportForClaude";

const job = (state: string, detail = ""): Job => ({
  id: "j", kind: "diagnostics_report", target: null, state, phase: "", done: 1, total: 4,
  detail, created_utc: null, started_utc: null, finished_utc: null, error: null, result: null,
} as Job);

describe("report for Claude", () => {
  it("explains itself before it has run, and promises nothing personal", () => {
    expect(reportStatusLine(null)).toMatch(/no location/);
    expect(reportDownloadable(null)).toBe(false);
  });
  it("shows the running step", () => {
    expect(reportStatusLine(job("running", "hot_pixel_census (3/9)"))).toContain("hot_pixel_census");
    expect(reportDownloadable(job("running"))).toBe(false);
  });
  it("offers the download once finished, cancelled or failed", () => {
    for (const s of ["done", "cancelled", "error"]) expect(reportDownloadable(job(s))).toBe(true);
    expect(reportStatusLine(job("done"))).toMatch(/ready/);
  });
});
