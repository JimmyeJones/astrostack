import { describe, expect, it } from "vitest";
import {
  readonlyAllowedReads,
  readonlyCurlExample,
  readonlyTokenBlurb,
} from "./readonlyToken";

describe("readonlyTokenBlurb", () => {
  it("names every read the token is allowed", () => {
    const text = readonlyTokenBlurb();
    for (const what of readonlyAllowedReads) expect(text).toContain(what);
  });

  it("says what it cannot do, which is the half that matters", () => {
    // The token exists so the owner can hand it to something without handing
    // over the credential that stacks, edits and deletes. A blurb that only
    // listed the reads would leave the reader to assume the limits.
    const text = readonlyTokenBlurb();
    expect(text).toMatch(/cannot/i);
    for (const verb of ["stack", "change a setting", "upload", "delete"]) {
      expect(text).toContain(verb);
    }
    // And that the reserved username is not a way round them — the one thing
    // someone might reasonably try.
    expect(text).toMatch(/even with your password's own username/i);
  });

  it("reads as a sentence, not a path list", () => {
    const text = readonlyTokenBlurb();
    expect(text).not.toContain("/api/");
    expect(text).not.toContain("GET");
  });
});

describe("readonlyCurlExample", () => {
  it("uses this install's own address and the username it is told", () => {
    expect(readonlyCurlExample("readonly", "http://nas.local:8000")).toBe(
      "curl -u readonly:YOUR_TOKEN http://nas.local:8000/api/logs",
    );
  });

  it("does not double the slash on an origin that carries one", () => {
    expect(readonlyCurlExample("readonly", "http://nas.local/")).toContain(
      "http://nas.local/api/logs",
    );
  });

  it("leaves the token a placeholder rather than pasting the real one", () => {
    // Shown right under the token itself, so it must not be a second copy of it
    // — a shell history is not where a secret should end up by default.
    expect(readonlyCurlExample("readonly", "http://x")).toContain("YOUR_TOKEN");
  });

  it("checks a path the token is actually allowed to read", () => {
    // A demo command that 403s would read as the feature being broken.
    expect(readonlyCurlExample("readonly", "http://x")).toContain("/api/logs");
    expect(readonlyAllowedReads).toContain("logs");
  });
});
