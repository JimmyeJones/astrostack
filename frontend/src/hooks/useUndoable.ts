import { useCallback, useMemo, useReducer } from "react";

/** How long after the previous keyed set a same-key set still coalesces into it.
 * A continuous gesture (slider/curve drag) fires ticks milliseconds apart, so
 * they stay well inside this window; two *separate* uses of the same control are
 * divided by the release + re-grab, which takes far longer. The window is what
 * ends a gesture — releasing a slider fires no event of its own — so without it a
 * second drag of the same control would silently merge into the first. */
const COALESCE_WINDOW_MS = 500;

const MAX_HISTORY = 100;

interface HistoryState<T> {
  value: T;
  past: T[];
  future: T[];
  lastKey: string | null;
  lastTime: number;
}

type Action<T> =
  | { type: "set"; next: T | ((prev: T) => T); coalesceKey?: string; now: number }
  | { type: "reset"; value: T }
  | { type: "undo" }
  | { type: "redo" };

/** The reducer is **pure** — no ref mutation, no `Date.now()`, no side effects —
 * so it is safe under React's StrictMode double-invoke and any future concurrent
 * re-render (which may run a reducer more than once or discard a run). An earlier
 * ref-based version mutated the history *inside* the state updater, so StrictMode
 * double-pushed/​double-popped and undo misbehaved in dev. `now` is computed by the
 * caller and passed in the action to keep this function pure. */
function reducer<T>(s: HistoryState<T>, action: Action<T>): HistoryState<T> {
  switch (action.type) {
    case "set": {
      const value =
        typeof action.next === "function"
          ? (action.next as (p: T) => T)(s.value)
          : action.next;
      const key = action.coalesceKey ?? null;
      if (Object.is(value, s.value)) {
        // No value change, but still record this set's key/time so a following
        // keyed set coalesces (or doesn't) against it exactly as before.
        return { ...s, lastKey: key, lastTime: action.now };
      }
      const coalesce =
        action.coalesceKey != null &&
        action.coalesceKey === s.lastKey &&
        action.now - s.lastTime < COALESCE_WINDOW_MS;
      // On a discrete (non-coalescing) set, push the previous value and cap the
      // history to the most recent MAX_HISTORY entries.
      const past = coalesce ? s.past : [...s.past, s.value].slice(-MAX_HISTORY);
      return { value, past, future: [], lastKey: key, lastTime: action.now };
    }
    case "reset":
      return { value: action.value, past: [], future: [], lastKey: null, lastTime: s.lastTime };
    case "undo": {
      if (s.past.length === 0) return s;
      const previous = s.past[s.past.length - 1];
      return {
        value: previous,
        past: s.past.slice(0, -1),
        future: [...s.future, s.value],
        lastKey: null,
        lastTime: s.lastTime,
      };
    }
    case "redo": {
      if (s.future.length === 0) return s;
      const next = s.future[s.future.length - 1];
      return {
        value: next,
        past: [...s.past, s.value],
        future: s.future.slice(0, -1),
        lastKey: null,
        lastTime: s.lastTime,
      };
    }
    default:
      return s;
  }
}

/** useState with undo/redo history. The setter accepts a value or updater (like
 * useState); `reset` replaces the value AND clears history (e.g. on load). */
export function useUndoable<T>(initial: T) {
  const [s, dispatch] = useReducer(
    reducer as (s: HistoryState<T>, a: Action<T>) => HistoryState<T>,
    initial,
    (init: T): HistoryState<T> => ({
      value: init,
      past: [],
      future: [],
      lastKey: null,
      lastTime: 0,
    }),
  );

  /** Set the value, optionally coalescing with the previous set. When `coalesceKey`
   * is given, matches the immediately-preceding set's key, *and* lands within
   * `COALESCE_WINDOW_MS` of it, the state updates in place *without* pushing a new
   * history entry — so a continuous interaction (a slider drag or a curve-point
   * drag firing dozens of onChange ticks) collapses to a single undoable step
   * instead of flooding (and evicting) the history. A discrete action (no key, a
   * different key, or the same key after the gesture-ending time gap) always starts
   * a fresh entry, so undo never over-reverts past a released control. */
  const set = useCallback((next: T | ((prev: T) => T), coalesceKey?: string) => {
    dispatch({ type: "set", next, coalesceKey, now: Date.now() });
  }, []);

  const reset = useCallback((value: T) => {
    dispatch({ type: "reset", value });
  }, []);

  const undo = useCallback(() => {
    dispatch({ type: "undo" });
  }, []);

  const redo = useCallback(() => {
    dispatch({ type: "redo" });
  }, []);

  return useMemo(
    () => ({
      state: s.value,
      set,
      reset,
      undo,
      redo,
      canUndo: s.past.length > 0,
      canRedo: s.future.length > 0,
    }),
    [s.value, s.past.length, s.future.length, set, reset, undo, redo],
  );
}
