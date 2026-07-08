import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { useJobEvents } from "./useJobEvents";

// Minimal EventSource mock (readyState + terminal constant mirror the browser
// API so the transient-vs-permanent error handling can be exercised).
class MockEventSource {
  static instances: MockEventSource[] = [];
  static readonly CONNECTING = 0;
  static readonly OPEN = 1;
  static readonly CLOSED = 2;
  url: string;
  readyState = MockEventSource.CONNECTING;
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
    this.readyState = MockEventSource.CLOSED;
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

  it("keeps the stream alive on a transient drop so a reconnect can still resolve the job", async () => {
    vi.stubGlobal("EventSource", MockEventSource);
    const { result } = renderHook(() => useJobEvents("abc"));
    const es = MockEventSource.instances[0];
    act(() => es.emit("progress", { id: "abc", state: "running", done: 2, total: 10 }));
    await waitFor(() => expect(result.current?.done).toBe(2));

    // A transient network drop mid-job: readyState stays CONNECTING and the
    // browser will auto-reconnect. The hook must NOT close the stream, or the job
    // could never resolve (the classic "finished while disconnected" freeze).
    es.readyState = MockEventSource.CONNECTING;
    act(() => es.onerror?.());
    expect(es.closed).toBe(false);

    // On reconnect the backend re-sends the current state, including the terminal
    // `done` if the job finished while we were disconnected.
    act(() => es.emit("done", { id: "abc", state: "done", done: 10, total: 10 }));
    await waitFor(() => expect(result.current?.state).toBe("done"));
    expect(es.closed).toBe(true);
  });

  it("clears the previous job's snapshot immediately when jobId changes to a new id", async () => {
    vi.stubGlobal("EventSource", MockEventSource);
    const { result, rerender } = renderHook(({ id }) => useJobEvents(id), {
      initialProps: { id: "job1" as string | null },
    });
    const es1 = MockEventSource.instances[0];
    act(() => es1.emit("done", { id: "job1", state: "done", done: 10, total: 10 }));
    await waitFor(() => expect(result.current?.state).toBe("done"));

    // Start a fresh job. The panel must not keep showing job1's stale "done"
    // snapshot (with its result button) until job2's first event arrives.
    rerender({ id: "job2" });
    expect(result.current).toBeNull();

    const es2 = MockEventSource.instances[1];
    act(() => es2.emit("progress", { id: "job2", state: "queued", done: 0, total: 10 }));
    await waitFor(() => expect(result.current?.state).toBe("queued"));
  });
});
