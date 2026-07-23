import { describe, expect, it } from "vitest";
import { absoluteLanUrl, qrMatrix } from "./qr";

describe("absoluteLanUrl", () => {
  it("anchors a relative download path to the given origin", () => {
    expect(
      absoluteLanUrl("/api/targets/M_42/stack-runs/5/jpeg", "http://192.168.1.50:8000"),
    ).toBe("http://192.168.1.50:8000/api/targets/M_42/stack-runs/5/jpeg");
  });

  it("normalises a double slash between origin and path", () => {
    expect(absoluteLanUrl("/x/y", "http://host:8000/")).toBe("http://host:8000/x/y");
    expect(absoluteLanUrl("x/y", "http://host:8000")).toBe("http://host:8000/x/y");
  });

  it("preserves query parameters (north-up / nameplate variants)", () => {
    expect(
      absoluteLanUrl(
        "/api/targets/M_31/stack-runs/9/jpeg?north_up=true&nameplate=true",
        "http://astrostack.local:8000",
      ),
    ).toBe(
      "http://astrostack.local:8000/api/targets/M_31/stack-runs/9/jpeg?north_up=true&nameplate=true",
    );
  });

  it("leaves an already-absolute URL untouched", () => {
    const abs = "https://example.com:9000/pic.jpg";
    expect(absoluteLanUrl(abs, "http://192.168.1.50:8000")).toBe(abs);
  });

  it("falls back to the raw path when there is no origin", () => {
    expect(absoluteLanUrl("/pic.jpg", "")).toBe("/pic.jpg");
  });
});

describe("qrMatrix", () => {
  it("encodes a picture URL into a square dark/light module grid", () => {
    const m = qrMatrix("http://192.168.1.50:8000/api/targets/M_42/stack-runs/5/jpeg");
    // A valid QR is at least version 1 (21×21) and odd-sized.
    expect(m.size).toBeGreaterThanOrEqual(21);
    expect(m.size % 4).toBe(1); // QR sizes are 21, 25, 29, … (4n+1)
    // The three finder patterns' top-left corner modules are always dark.
    expect(m.isDark(0, 0)).toBe(true);
    expect(m.isDark(0, m.size - 7)).toBe(true);
    expect(m.isDark(m.size - 7, 0)).toBe(true);
    // A real payload has a healthy mix of dark and light modules.
    let dark = 0;
    for (let r = 0; r < m.size; r++) {
      for (let c = 0; c < m.size; c++) if (m.isDark(r, c)) dark++;
    }
    const frac = dark / (m.size * m.size);
    expect(frac).toBeGreaterThan(0.2);
    expect(frac).toBeLessThan(0.8);
  });

  it("grows to a larger version for a longer URL", () => {
    const short = qrMatrix("http://host:8000/a/1/jpeg");
    const long = qrMatrix(
      "http://astrostack.local:8000/api/targets/NGC_7000_North_America_Nebula/" +
        "stack-runs/123/jpeg?north_up=true&nameplate=true",
    );
    expect(long.size).toBeGreaterThan(short.size);
  });

  it("is deterministic for the same input", () => {
    const a = qrMatrix("http://host:8000/api/targets/M_13/stack-runs/2/jpeg");
    const b = qrMatrix("http://host:8000/api/targets/M_13/stack-runs/2/jpeg");
    expect(a.size).toBe(b.size);
    for (let r = 0; r < a.size; r++) {
      for (let c = 0; c < a.size; c++) expect(a.isDark(r, c)).toBe(b.isDark(r, c));
    }
  });
});
