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
});
