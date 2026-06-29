import { useCallback, useRef, useState } from "react";

/** useState with undo/redo history. The setter accepts a value or updater (like
 * useState); `reset` replaces the value AND clears history (e.g. on load). */
export function useUndoable<T>(initial: T) {
  const [state, setStateRaw] = useState<T>(initial);
  const past = useRef<T[]>([]);
  const future = useRef<T[]>([]);
  const [, force] = useState(0);

  const set = useCallback((next: T | ((prev: T) => T)) => {
    setStateRaw((prev) => {
      const value = typeof next === "function" ? (next as (p: T) => T)(prev) : next;
      if (Object.is(value, prev)) return prev;
      past.current.push(prev);
      if (past.current.length > 100) past.current.shift();
      future.current = [];
      return value;
    });
  }, []);

  const reset = useCallback((value: T) => {
    past.current = [];
    future.current = [];
    setStateRaw(value);
  }, []);

  const undo = useCallback(() => {
    setStateRaw((prev) => {
      if (!past.current.length) return prev;
      const previous = past.current.pop()!;
      future.current.push(prev);
      force((n) => n + 1);
      return previous;
    });
  }, []);

  const redo = useCallback(() => {
    setStateRaw((prev) => {
      if (!future.current.length) return prev;
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
