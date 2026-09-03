import { describe, expect, it } from "vitest";
import sharedCases from "../../tests/fixtures/folder_conflict.json";
import { folderConflict, settingsErrorMessage } from "./settingsFolders";

type Case = {
  incoming: string; library: string; data_root: string;
  verdict: "both" | "neither" | "server"; field?: string;
};

describe("folderConflict", () => {
  // The same table `tests/webapp/test_config_upgrade.py` reads against the server
  // guard that actually refuses the save. This side is only allowed to be
  // *quieter* than that one (the "server" cases), never louder: claiming a
  // conflict the server would accept would block a perfectly good layout on a
  // guess a browser is not equipped to make.
  it("agrees with the server guard on the shared table", () => {
    const cases = sharedCases.cases as Case[];
    expect(cases.length).toBeGreaterThanOrEqual(10);
    for (const c of cases) {
      const got = folderConflict(c.incoming, c.library, c.data_root);
      const where = `${c.incoming} | ${c.library} | ${c.data_root}`;
      if (c.verdict === "both") {
        expect(got, where).not.toBeNull();
        expect(got?.field, where).toBe(c.field);
      } else {
        expect(got, where).toBeNull();
      }
    }
  });

  it("says the same thing the server says", () => {
    const got = folderConflict("/data/incoming", "/data/incoming/lib", "/data");
    expect(got?.message).toContain("would sit inside the incoming folder");
    expect(got?.message).toContain("/data/incoming");
    expect(got?.message).toContain("only copy of your raw frames");
  });

  it("never treats the root as a parent", () => {
    // "/" contains everything, so a stray "/" in the incoming field must not
    // condemn every other folder on the box.
    expect(folderConflict("/", "/data/library", "/data")).toBeNull();
  });

  it("follows the field being typed, not the last save", () => {
    // A blank library resolves under whatever data root is in the box *now*.
    expect(folderConflict("/data/incoming", "", "/data")).toBeNull();
    expect(folderConflict("/data/incoming", "", "/data/incoming/x")).not.toBeNull();
  });

  it("ignores trailing slashes and surrounding space", () => {
    expect(folderConflict(" /data/incoming/ ", " /data/incoming/lib ", "/data"))
      .not.toBeNull();
    expect(folderConflict("/data/incoming/", "/data/library/", "/data")).toBeNull();
  });
});

describe("settingsErrorMessage", () => {
  it("drops the status code in front of a plain-language reason", () => {
    expect(settingsErrorMessage(
      "422: Your library folder would sit inside the incoming folder (/data/incoming). "
      + "Pick a folder outside it."))
      .toBe("Your library folder would sit inside the incoming folder (/data/incoming). "
        + "Pick a folder outside it.");
  });

  it("keeps the code when the detail is not a sentence", () => {
    // A beginner reporting "500" is more use than one reporting nothing, so the
    // number only goes when there is a real sentence behind it.
    expect(settingsErrorMessage("500: Internal Server Error"))
      .toBe("500: Internal Server Error");
    expect(settingsErrorMessage("422: ValueError: bad value for x in y"))
      .toBe("422: ValueError: bad value for x in y");
    expect(settingsErrorMessage("400: nope")).toBe("400: nope");
  });

  it("leaves anything without a status prefix alone", () => {
    expect(settingsErrorMessage("Failed to fetch")).toBe("Failed to fetch");
    expect(settingsErrorMessage("")).toBe("");
  });
});
