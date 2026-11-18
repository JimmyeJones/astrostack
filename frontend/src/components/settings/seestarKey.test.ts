import { describe, expect, it } from "vitest";
import { seestarKeyError, seestarKeyLine } from "./seestarKey";

describe("seestarKeyLine", () => {
  it("says plainly what no key means (broadcast-only)", () => {
    const line = seestarKeyLine({ installed: false, problem: null });
    expect(line).toMatch(/can only listen to what the telescope announces/);
    expect(line).not.toMatch(/broadcast|RSA|PKCS/);
  });

  it("promises privacy once a key is installed", () => {
    expect(seestarKeyLine({ installed: true, problem: null }))
      .toMatch(/never shown again, sent anywhere or included in a settings backup/);
  });

  it("passes the server's problem through when a stored key can't be read", () => {
    expect(seestarKeyLine({ installed: false, problem: "Upload it again." })).toBe("Upload it again.");
  });

  it("has a loading line before the first answer", () => {
    expect(seestarKeyLine(undefined)).toMatch(/Checking/);
  });
});

describe("seestarKeyError", () => {
  it("drops the status prefix req() adds", () => {
    expect(seestarKeyError(new Error("400: This is the public half of a key.")))
      .toBe("This is the public half of a key.");
    expect(seestarKeyError("plain")).toBe("plain");
  });
});
