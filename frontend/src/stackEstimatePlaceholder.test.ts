import { describe, expect, it } from "vitest";
import {
  STACK_ESTIMATE_QUERY_KEY, estimateIsForTarget,
} from "./stackEstimatePlaceholder";

describe("estimateIsForTarget", () => {
  const key = (safe: string, ...rest: unknown[]) =>
    [STACK_ESTIMATE_QUERY_KEY, safe, ...rest] as const;

  it("holds an answer about the target on screen", () => {
    expect(estimateIsForTarget(key("M_42", false, 1.5, 3.0), "M_42")).toBe(true);
  });

  it("refuses another target's answer", () => {
    // The whole reason this is a predicate and not `keepPreviousData`: the
    // route does not remount when only `:safe` changes, so this is the case
    // that would put M 42's frame count under NGC 7000's title.
    expect(estimateIsForTarget(key("M_42", false), "NGC_7000")).toBe(false);
  });

  it("refuses a key belonging to some other query", () => {
    expect(estimateIsForTarget(["frames", "M_42"], "M_42")).toBe(false);
  });

  it("refuses when there is nothing held yet", () => {
    expect(estimateIsForTarget(undefined, "M_42")).toBe(false);
    expect(estimateIsForTarget([], "M_42")).toBe(false);
    expect(estimateIsForTarget([STACK_ESTIMATE_QUERY_KEY], "M_42")).toBe(false);
  });

  it("refuses before the route param is known", () => {
    // `useParams` defaults `safe` to "" on the way in; an empty name must not
    // match an entry whose own name is missing for some other reason.
    expect(estimateIsForTarget(key(""), "")).toBe(false);
  });
});
