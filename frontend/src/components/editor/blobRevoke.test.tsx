// Regression for the editor's blob-URL lifecycle: the live-preview (and the five
// sibling overlay/compare) queries fetch a PNG as a Blob, mint an object URL per
// fetch, and revoke it the instant the query's `data` changes. React Query caches
// a query's result by key, so a later undo/redo — which reproduces a *prior*
// recipe and therefore a prior query key — could re-serve a URL that was already
// revoked, blanking the preview. Setting `gcTime: 0` drops a superseded blob query
// immediately so its revoked URL is never re-served. This test exercises the exact
// react-query + revoke-effect interaction (not the whole 1900-line Editor) and
// proves the fix, with a control showing the bug when the entry is cached.
import { QueryClient, QueryClientProvider, keepPreviousData, useQuery } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import { useEffect } from "react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

let counter = 0;
const revoked = new Set<string>();

beforeEach(() => {
  counter = 0;
  revoked.clear();
  // jsdom lacks revokeObjectURL; record what gets revoked so we can assert a
  // displayed URL is still live.
  vi.stubGlobal("URL", Object.assign(URL, {
    revokeObjectURL: (u: string) => { revoked.add(u); },
  }));
});

// Mirrors the editor's blob-query shape: unique URL per fetch, keepPreviousData to
// avoid a flash, and the revoke-on-`data`-change effect.
function useBlobQuery(keyVal: string, gcTime: number) {
  const q = useQuery({
    queryKey: ["blob-probe", keyVal],
    gcTime,
    placeholderData: keepPreviousData,
    queryFn: async () => `blob:url-${counter++}`,
  });
  useEffect(() => {
    const u = q.data;
    return () => { if (u) URL.revokeObjectURL(u); };
  }, [q.data]);
  return q.data;
}

function makeWrapper() {
  // staleTime mirrors the app's global 10s, so returning to a recent key is
  // "fresh" and would be served straight from cache without a refetch.
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: 10_000 } },
  });
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
}

describe("editor blob-URL revocation across undo/redo (recurring query keys)", () => {
  it("with gcTime: 0, returning to a prior key serves a fresh (un-revoked) URL", async () => {
    const { result, rerender } = renderHook(
      ({ k }: { k: string }) => useBlobQuery(k, 0),
      { wrapper: makeWrapper(), initialProps: { k: "A" } },
    );
    await waitFor(() => expect(result.current).toBe("blob:url-0"));

    rerender({ k: "B" });
    await waitFor(() => expect(result.current).toBe("blob:url-1"));
    expect(revoked.has("blob:url-0")).toBe(true); // leaving A revoked its URL

    // Undo back to A: the entry was GC'd immediately, so it refetches a fresh URL
    // instead of re-serving the revoked one.
    rerender({ k: "A" });
    await waitFor(() => expect(result.current).toBe("blob:url-2"));
    expect(revoked.has(result.current!)).toBe(false); // the shown URL is live
  });

  it("control: with the entry cached (gcTime ∞), undo re-serves the REVOKED URL — the bug", async () => {
    const { result, rerender } = renderHook(
      ({ k }: { k: string }) => useBlobQuery(k, Infinity),
      { wrapper: makeWrapper(), initialProps: { k: "A" } },
    );
    await waitFor(() => expect(result.current).toBe("blob:url-0"));

    rerender({ k: "B" });
    await waitFor(() => expect(result.current).toBe("blob:url-1"));
    expect(revoked.has("blob:url-0")).toBe(true);

    // Undo to A: fresh (<10s) + cached → served from cache with no refetch, so the
    // displayed URL is the one already revoked when we left A. This is exactly the
    // defect gcTime: 0 fixes.
    rerender({ k: "A" });
    await waitFor(() => expect(result.current).toBe("blob:url-0"));
    expect(revoked.has(result.current!)).toBe(true);
  });
});
