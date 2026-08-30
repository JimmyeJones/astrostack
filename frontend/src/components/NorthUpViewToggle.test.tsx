import { MantineProvider } from "@mantine/core";
import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import {
  NORTH_UP_VIEW_KEY, NorthUpViewToggle, loadNorthUpView, saveNorthUpView,
} from "./NorthUpViewToggle";

afterEach(() => localStorage.clear());

// The control itself shipped in v0.308.0 with its behaviour covered from the
// card that uses it. These are the cases a component test can reach and that
// one can't: what the *stored* preference does when the store misbehaves, and
// what the control tells a screen reader.
describe("the remembered North-up preference", () => {
  it("defaults to the saved orientation — an upgrade sees what it saw before", () => {
    expect(loadNorthUpView()).toBe(false);
  });

  it("round-trips a choice, and can be turned back off", () => {
    saveNorthUpView(true);
    expect(loadNorthUpView()).toBe(true);
    saveNorthUpView(false);
    expect(loadNorthUpView()).toBe(false);
  });

  it("reads an unrecognised stored value as off rather than as on", () => {
    // A value from a build that spelled this differently, or a hand-edited
    // store. Anything that isn't the written form means "we don't know", and
    // the safe answer is the orientation the owner saved.
    for (const junk of ["true", "yes", "{}", ""]) {
      localStorage.setItem(NORTH_UP_VIEW_KEY, junk);
      expect(loadNorthUpView()).toBe(false);
    }
  });

  it("survives a store that refuses to answer (private mode, site data off)", () => {
    // The documented promise is that the toggle still works for the session and
    // simply isn't remembered — never that the page breaks.
    const get = Storage.prototype.getItem;
    const set = Storage.prototype.setItem;
    Storage.prototype.getItem = () => { throw new Error("denied"); };
    Storage.prototype.setItem = () => { throw new Error("denied"); };
    try {
      expect(loadNorthUpView()).toBe(false);
      expect(() => saveNorthUpView(true)).not.toThrow();
    } finally {
      Storage.prototype.getItem = get;
      Storage.prototype.setItem = set;
    }
  });
});

describe("NorthUpViewToggle", () => {
  const renderToggle = (on: boolean, onChange: (v: boolean) => void) => render(
    <MantineProvider>
      <NorthUpViewToggle on={on} onChange={onChange} />
    </MantineProvider>,
  );

  it("hands the caller the opposite of what it is showing", () => {
    const seen: boolean[] = [];
    renderToggle(false, (v) => seen.push(v));
    const btn = screen.getByTestId("north-up-view");
    // It is an icon button, so the label is the only thing a screen reader has —
    // and it must name the action, not the state, or it reads as a status.
    expect(btn).toHaveAccessibleName("Turn the picture so North is up");
    expect(btn).toHaveAttribute("aria-pressed", "false");
    fireEvent.click(btn);
    expect(seen).toEqual([true]);
  });

  it("says it is on, and offers the way back", () => {
    const seen: boolean[] = [];
    renderToggle(true, (v) => seen.push(v));
    const btn = screen.getByTestId("north-up-view");
    expect(btn).toHaveAccessibleName("Show the picture as saved");
    expect(btn).toHaveAttribute("aria-pressed", "true");
    fireEvent.click(btn);
    expect(seen).toEqual([false]);
  });
});
