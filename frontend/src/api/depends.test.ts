import { describe, expect, it } from "vitest";
import { dependencyMet } from "./depends";

describe("dependencyMet", () => {
  const get = (v: Record<string, unknown>) => (k: string) => v[k];

  it("is met when there is no dependency", () => {
    expect(dependencyMet(null, get({}))).toBe(true);
    expect(dependencyMet(undefined, get({}))).toBe(true);
    expect(dependencyMet("", get({}))).toBe(true);
  });

  it("treats a bare key as a truthiness check (existing boolean form)", () => {
    expect(dependencyMet("drizzle", get({ drizzle: true }))).toBe(true);
    expect(dependencyMet("drizzle", get({ drizzle: false }))).toBe(false);
    expect(dependencyMet("drizzle", get({}))).toBe(false);
  });

  it("matches a specific enum value with the key=value form", () => {
    expect(dependencyMet("mode=asinh", get({ mode: "asinh" }))).toBe(true);
    expect(dependencyMet("mode=asinh", get({ mode: "stf" }))).toBe(false);
    expect(dependencyMet("mode=stf", get({ mode: "stf" }))).toBe(true);
  });

  it("stringifies the looked-up value before comparing", () => {
    expect(dependencyMet("n=2", get({ n: 2 }))).toBe(true);
    expect(dependencyMet("n=2", get({ n: 3 }))).toBe(false);
  });
});
