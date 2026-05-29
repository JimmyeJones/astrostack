import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { useJobEvents } from "./useJobEvents";

// Minimal EventSource mock.
class MockEventSource {
  static instances: MockEventSource[] = [];
  url: string;
  listeners: Record<string, ((e: MessageEvent) => void)[]> = {};
  closed = false;
  onerror: (() => void) | null = null;
  constructor(url: string) {
    this.url = url;
    MockEventSource.instances.push(this);
  }
  addEventListener(type: string, cb: (e: MessageEvent) => void) {
    (this.listeners[type] ??= []).push(cb);
  }
  emit(type: string, data: unknown) {
    const e = { data: JSON.stringify(data) } as MessageEvent;
    (this.listeners[type] ?? []).forEach((cb) => cb(e));
  }
  close() {
    this.closed = true;
  }
}

afterEach(() => {
  MockEventSource.instances = [];
  vi.unstubAllGlobals();
});

describe("useJobEvents", () => {
  it("returns null when no jobId", () => {
    vi.stubGlobal("EventSource", MockEventSource);
    const { result } = renderHook(() => useJobEvents(null));
    expect(result.current).toBeNull();
    expect(MockEventSource.instances.length).toBe(0);
  });

  it("updates on progress and closes on done", async () => {
    vi.stubGlobal("EventSource", MockEventSource);
    const { result } = renderHook(() => useJobEvents("abc"));
    const es = MockEventSource.instances[0];
    expect(es.url).toContain("/api/jobs/abc/events");

    act(() => es.emit("progress", { id: "abc", state: "running", done: 2, total: 10 }));
    await waitFor(() => expect(result.current?.done).toBe(2));

    act(() => es.emit("done", { id: "abc", state: "done", done: 10, total: 10 }));
    await waitFor(() => expect(result.current?.state).toBe("done"));
    expect(es.closed).toBe(true);
  });
});
