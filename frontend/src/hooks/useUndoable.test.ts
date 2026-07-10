import { StrictMode } from "react";
import { act, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { useUndoable } from "./useUndoable";

describe("useUndoable", () => {
  afterEach(() => { vi.useRealTimers(); });

  it("tracks history and undoes/redoes", () => {
    const { result } = renderHook(() => useUndoable<number[]>([]));
    expect(result.current.canUndo).toBe(false);

    act(() => result.current.set([1]));
    act(() => result.current.set((p) => [...p, 2]));
    expect(result.current.state).toEqual([1, 2]);
    expect(result.current.canUndo).toBe(true);

    act(() => result.current.undo());
    expect(result.current.state).toEqual([1]);
    act(() => result.current.undo());
    expect(result.current.state).toEqual([]);
    expect(result.current.canUndo).toBe(false);

    act(() => result.current.redo());
    expect(result.current.state).toEqual([1]);
  });

  it("reset clears history", () => {
    const { result } = renderHook(() => useUndoable<number[]>([]));
    act(() => result.current.set([1]));
    act(() => result.current.reset([9]));
    expect(result.current.state).toEqual([9]);
    expect(result.current.canUndo).toBe(false);
  });

  it("coalesces consecutive sets sharing a key into one undo step", () => {
    const { result } = renderHook(() => useUndoable<number[]>([0]));
    // Simulate a slider drag firing many ticks under one coalesce key.
    act(() => result.current.set([1], "strength"));
    act(() => result.current.set([2], "strength"));
    act(() => result.current.set([3], "strength"));
    expect(result.current.state).toEqual([3]);
    // A single undo jumps back to before the whole drag, not one tick.
    act(() => result.current.undo());
    expect(result.current.state).toEqual([0]);
    expect(result.current.canUndo).toBe(false);
  });

  it("does not coalesce across different keys or discrete (keyless) sets", () => {
    const { result } = renderHook(() => useUndoable<number[]>([0]));
    act(() => result.current.set([1], "black"));   // drag param A
    act(() => result.current.set([2], "white"));   // drag param B (different key)
    act(() => result.current.set([3]));            // discrete edit (no key)
    // Three separate history entries → three undos to unwind.
    act(() => result.current.undo());
    expect(result.current.state).toEqual([2]);
    act(() => result.current.undo());
    expect(result.current.state).toEqual([1]);
    act(() => result.current.undo());
    expect(result.current.state).toEqual([0]);
  });

  it("does not merge two separate drags of the same control (gesture boundary)", () => {
    // Regression: coalescing keyed only off the previous set's key, with no
    // gesture-end signal, silently merged a *second* drag of the same slider into
    // the first — its intermediate value then unreachable by undo. Releasing a
    // slider fires no event, so the time gap between gestures is what ends one.
    vi.useFakeTimers();
    const { result } = renderHook(() => useUndoable<number[]>([3]));
    // First drag of the "strength" slider: 3 → 5, several ticks close in time.
    act(() => result.current.set([4], "strength"));
    act(() => result.current.set([5], "strength"));
    // The user releases the slider; time passes before a second, separate drag.
    act(() => { vi.advanceTimersByTime(1000); });
    // Second drag of the *same* slider: 5 → 7.
    act(() => result.current.set([6], "strength"));
    act(() => result.current.set([7], "strength"));
    expect(result.current.state).toEqual([7]);
    // One undo returns to the value *between* the gestures (5), not before the
    // first drag (3) — each gesture is its own undoable step.
    act(() => result.current.undo());
    expect(result.current.state).toEqual([5]);
    act(() => result.current.undo());
    expect(result.current.state).toEqual([3]);
    expect(result.current.canUndo).toBe(false);
  });

  it("undo/redo work correctly under StrictMode's double-invoke", () => {
    // Regression: the history used to be kept in refs mutated *inside* the state
    // updater, so React StrictMode's dev double-invocation double-pushed/​popped
    // and undo silently no-op'd after a single edit (the whole app renders under
    // <StrictMode>, so this broke undo in `npm run dev`). A pure reducer is
    // idempotent under a repeated invoke, so history stays consistent. This test
    // FAILS on the old ref-based hook and PASSES on the reducer version.
    const { result } = renderHook(() => useUndoable<number[]>([]), {
      wrapper: StrictMode,
    });
    act(() => result.current.set([1]));
    expect(result.current.state).toEqual([1]);
    expect(result.current.canUndo).toBe(true);

    act(() => result.current.set((p) => [...p, 2]));
    expect(result.current.state).toEqual([1, 2]);

    // Exactly one undo per edit — no phantom duplicate entries.
    act(() => result.current.undo());
    expect(result.current.state).toEqual([1]);
    act(() => result.current.undo());
    expect(result.current.state).toEqual([]);
    expect(result.current.canUndo).toBe(false);

    // Redo steps forward one at a time too.
    act(() => result.current.redo());
    expect(result.current.state).toEqual([1]);
    act(() => result.current.redo());
    expect(result.current.state).toEqual([1, 2]);
    expect(result.current.canRedo).toBe(false);
  });

  it("coalesces a keyed drag into one step even under StrictMode", () => {
    const { result } = renderHook(() => useUndoable<number[]>([0]), {
      wrapper: StrictMode,
    });
    act(() => result.current.set([1], "strength"));
    act(() => result.current.set([2], "strength"));
    act(() => result.current.set([3], "strength"));
    expect(result.current.state).toEqual([3]);
    act(() => result.current.undo());
    expect(result.current.state).toEqual([0]);
    expect(result.current.canUndo).toBe(false);
  });

  it("starts a fresh entry for a keyed set right after an undo", () => {
    const { result } = renderHook(() => useUndoable<number[]>([0]));
    act(() => result.current.set([1], "g"));
    act(() => result.current.undo());
    expect(result.current.state).toEqual([0]);
    // The same key again after an undo must not silently merge into the popped
    // entry; it is a new, independently-undoable change.
    act(() => result.current.set([5], "g"));
    act(() => result.current.undo());
    expect(result.current.state).toEqual([0]);
  });
});
