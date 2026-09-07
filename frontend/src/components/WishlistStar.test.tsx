import { MantineProvider } from "@mantine/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { WishlistStar } from "./WishlistStar";
import * as client from "../api/client";
import type { Wishlist, WishlistItem } from "../api/client";

function item(over: Partial<WishlistItem> = {}): WishlistItem {
  return {
    catalog_id: "M31", name: "Andromeda Galaxy", type: "galaxy", con: "And",
    blurb: "", size_arcmin: null, added_utc: "2026-09-07T00:00:00Z",
    captured: false, safe_name: null, target_name: null, thumbnail_url: null,
    ...over,
  };
}

function wishlist(items: WishlistItem[]): Wishlist {
  return { items, counts: { saved: items.length, captured: 0 } };
}

function renderStar(catalogId = "M31") {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <MantineProvider>
      <QueryClientProvider client={qc}>
        <WishlistStar catalogId={catalogId} label="M31 (Andromeda Galaxy)" />
      </QueryClientProvider>
    </MantineProvider>,
  );
}

afterEach(() => vi.restoreAllMocks());

describe("WishlistStar", () => {
  it("offers to save an object that isn't on the list yet", async () => {
    vi.spyOn(client.api, "getWishlist").mockResolvedValue(wishlist([]));
    renderStar();

    const star = await screen.findByTestId("wishlist-star-M31");
    await waitFor(() => expect(star).toHaveAttribute("aria-pressed", "false"));
    expect(star).toHaveAttribute(
      "aria-label", "Add M31 (Andromeda Galaxy) to your wishlist");
  });

  it("shows an already-saved object as saved, and offers to remove it", async () => {
    vi.spyOn(client.api, "getWishlist").mockResolvedValue(wishlist([item()]));
    renderStar();

    const star = await screen.findByTestId("wishlist-star-M31");
    await waitFor(() => expect(star).toHaveAttribute("aria-pressed", "true"));
    expect(star).toHaveAttribute(
      "aria-label", "Remove M31 (Andromeda Galaxy) from your wishlist");
  });

  it("saves on click and flips without a second fetch", async () => {
    vi.spyOn(client.api, "getWishlist").mockResolvedValue(wishlist([]));
    const add = vi.spyOn(client.api, "addToWishlist")
      .mockResolvedValue(wishlist([item()]));
    renderStar();

    const star = await screen.findByTestId("wishlist-star-M31");
    await waitFor(() => expect(star).toHaveAttribute("aria-pressed", "false"));
    fireEvent.click(star);

    await waitFor(() => expect(star).toHaveAttribute("aria-pressed", "true"));
    expect(add).toHaveBeenCalledWith("M31");
    // The toggle's own response is the new list — the list is never re-fetched.
    expect(client.api.getWishlist).toHaveBeenCalledTimes(1);
  });

  it("un-saves an object that is already on the list", async () => {
    vi.spyOn(client.api, "getWishlist").mockResolvedValue(wishlist([item()]));
    const remove = vi.spyOn(client.api, "removeFromWishlist")
      .mockResolvedValue(wishlist([]));
    renderStar();

    const star = await screen.findByTestId("wishlist-star-M31");
    await waitFor(() => expect(star).toHaveAttribute("aria-pressed", "true"));
    fireEvent.click(star);

    await waitFor(() => expect(star).toHaveAttribute("aria-pressed", "false"));
    expect(remove).toHaveBeenCalledWith("M31");
  });

  it("still renders on a backend that has never heard of a wishlist", async () => {
    // An older backend 404s the endpoint. The star must degrade to an unsaved,
    // clickable control rather than throwing an error at someone who only
    // wanted to tick a box.
    vi.spyOn(client.api, "getWishlist").mockRejectedValue(new Error("404: Not Found"));
    renderStar();

    const star = await screen.findByTestId("wishlist-star-M31");
    await waitFor(() => expect(star).toHaveAttribute("aria-pressed", "false"));
  });
});
