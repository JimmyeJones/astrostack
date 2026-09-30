import type { SystemInfo } from "./api/client";

/** One sentence about the stack memory budget, and how loudly to say it. */
export interface StackBudgetNote {
  text: string;
  /** `warning` only where the field the reader is looking at does nothing. */
  tone: "info" | "warning";
}

/**
 * "What is my stack memory budget right now, and why?"
 *
 * The Memory box shows one number you can type into and a placeholder saying
 * `auto (~70% of RAM)`. What that placeholder does not say is the consequence:
 * left blank, every stack is priced against however much memory happened to be
 * free at the minute it started, so the **same** target — same subs, same
 * options — can come out at a smaller super-resolution scale, or with less
 * outlier removal, on a busy day than on a quiet one. That is not hypothetical:
 * the same target was measured priced against ~4.1 GB in one batch and ~3.2 GB
 * in the next, a week apart, and the run itself is the only place it showed.
 * Typing a number here is the one lever that makes the answer repeatable, and
 * nothing said so.
 *
 * The other half is the env override. `ASTROSTACK_MAX_STACK_GB` silently beats
 * this field, so on an install that sets it the box is decoration — and the
 * "higher than this machine's RAM" advisory beside it was warning about a number
 * no stack would ever read.
 *
 * Which is why the source comes from the server (`stack_budget_source`, the
 * engine's own `resolve_stack_memory_budget`) rather than being re-derived from
 * the form: the browser cannot see the container's environment, and a precedence
 * rule written out twice is a precedence rule that drifts.
 *
 * Pure and null-safe: `null` on an older backend that serves neither field, and
 * on a source this build doesn't know (a newer engine's fifth source must render
 * nothing rather than half a sentence).
 */
export function stackBudgetNote(
  memory: SystemInfo["memory"] | undefined,
): StackBudgetNote | null {
  const gb = memory?.stack_budget_gb;
  const source = memory?.stack_budget_source;
  if (typeof gb !== "number" || !Number.isFinite(gb) || gb <= 0) return null;
  const n = Number(gb.toFixed(1));

  if (source === "env") {
    return {
      tone: "warning",
      text:
        `ASTROSTACK_MAX_STACK_GB is set on this install, so every stack is `
        + `priced against ${n} GB and the box above is ignored. Change it where `
        + `this container's environment is set, or unset it to use the budget here.`,
    };
  }
  if (source === "setting") {
    return {
      tone: "info",
      text:
        `Every stack is priced against this ${n} GB, whatever else the machine `
        + `happens to be doing — so the same subs with the same settings give you `
        + `the same picture every time.`,
    };
  }
  if (source === "available") {
    return {
      tone: "info",
      text:
        `Left blank, so each stack is priced against however much memory is free `
        + `when it starts — about ${n} GB right now. The same target can come out `
        + `at a smaller super-resolution scale, or with less outlier removal, on a `
        + `busy day than on a quiet one; the picture's History card says so when it `
        + `happens. Put a number here and every stack is priced against that instead.`,
    };
  }
  if (source === "fallback") {
    return {
      tone: "info",
      text:
        `This machine's free memory couldn't be read, so each stack is priced `
        + `against a fixed ${n} GB. Put a number here to set it yourself.`,
    };
  }
  return null;
}
