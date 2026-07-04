import { act, renderHook } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { useUndoable } from "./useUndoable";

describe("useUndoable", () => {
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
