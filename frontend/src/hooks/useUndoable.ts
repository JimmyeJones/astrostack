import { useCallback, useRef, useState } from "react";

/** useState with undo/redo history. The setter accepts a value or updater (like
 * useState); `reset` replaces the value AND clears history (e.g. on load). */
export function useUndoable<T>(initial: T) {
  const [state, setStateRaw] = useState<T>(initial);
  const past = useRef<T[]>([]);
  const future = useRef<T[]>([]);
  const lastKey = useRef<string | null>(null);
  const [, force] = useState(0);

  /** Set the value, optionally coalescing with the previous set. When `coalesceKey`
   * is given and matches the immediately-preceding set's key, the state updates in
   * place *without* pushing a new history entry — so a continuous interaction (a
   * slider drag or a curve-point drag firing dozens of onChange ticks) collapses to
   * a single undoable step instead of flooding (and evicting) the history. A
   * discrete action (no key, or a different key) always starts a fresh entry. */
  const set = useCallback((next: T | ((prev: T) => T), coalesceKey?: string) => {
    setStateRaw((prev) => {
      const value = typeof next === "function" ? (next as (p: T) => T)(prev) : next;
      const prevKey = lastKey.current;
      lastKey.current = coalesceKey ?? null;
      if (Object.is(value, prev)) return prev;
      const coalesce = coalesceKey != null && coalesceKey === prevKey;
      if (!coalesce) {
        past.current.push(prev);
        if (past.current.length > 100) past.current.shift();
      }
      future.current = [];
      return value;
    });
  }, []);

  const reset = useCallback((value: T) => {
    past.current = [];
    future.current = [];
    lastKey.current = null;
    setStateRaw(value);
  }, []);

  const undo = useCallback(() => {
    setStateRaw((prev) => {
      if (!past.current.length) return prev;
      lastKey.current = null;
      const previous = past.current.pop()!;
      future.current.push(prev);
      force((n) => n + 1);
      return previous;
    });
  }, []);

  const redo = useCallback(() => {
    setStateRaw((prev) => {
      if (!future.current.length) return prev;
      lastKey.current = null;
      const next = future.current.pop()!;
      past.current.push(prev);
      force((n) => n + 1);
      return next;
    });
  }, []);

  return {
    state, set, reset, undo, redo,
    canUndo: past.current.length > 0,
    canRedo: future.current.length > 0,
  };
}
