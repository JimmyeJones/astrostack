import { ActionIcon, Tooltip } from "@mantine/core";
import { IconStar, IconStarFilled } from "@tabler/icons-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, type Wishlist } from "../api/client";

/**
 * "☆ I want to shoot this" — the one-tap toggle behind My wishlist.
 *
 * The app could already tell you what is *up* and which famous objects you have
 * *got*, but there was nowhere to put the most natural planning thought a
 * beginner has: "I want to shoot the Andromeda Galaxy next." This is that
 * button; the Tonight page then tells you, on the right night, that the thing
 * you asked for is well placed.
 *
 * Every star on a page shares one `["wishlist"]` query (TanStack dedupes by key,
 * so a hundred tiles cost one fetch), and each toggle's response *is* the new
 * list — so the whole page updates from a single round trip with no refetch.
 *
 * Best-effort by design: on an older backend the fetch fails, `saved` reads
 * false and a click simply doesn't stick — no error state is thrown at someone
 * who only wanted to tick a star.
 */
export function WishlistStar({ catalogId, label, size = "sm" }: {
  catalogId: string;
  /** What to call the object in the tooltip ("M31 (Andromeda Galaxy)"). */
  label?: string;
  size?: "xs" | "sm" | "md";
}) {
  const qc = useQueryClient();
  const list = useQuery({
    queryKey: ["wishlist"],
    queryFn: () => api.getWishlist().catch(() => null),
    staleTime: 60_000,
    retry: false,
  });

  const saved = !!list.data?.items.some((i) => i.catalog_id === catalogId);

  const toggle = useMutation({
    mutationFn: () =>
      saved ? api.removeFromWishlist(catalogId) : api.addToWishlist(catalogId),
    onSuccess: (next: Wishlist) => {
      qc.setQueryData(["wishlist"], next);
      // The Tonight card reads a different endpoint over the same list, so it
      // has to be told the list changed rather than waiting out its own stale
      // time — otherwise starring something and walking to Tonight shows the
      // old answer.
      qc.invalidateQueries({ queryKey: ["wishlist-tonight"] });
    },
  });

  const name = label || catalogId;
  const tip = saved ? `Remove ${name} from your wishlist` : `Add ${name} to your wishlist`;
  return (
    <Tooltip label={tip} openDelay={400} withinPortal>
      <ActionIcon
        variant={saved ? "filled" : "default"}
        color={saved ? "yellow" : undefined}
        size={size}
        radius="xl"
        aria-label={tip}
        aria-pressed={saved}
        data-testid={`wishlist-star-${catalogId}`}
        loading={toggle.isPending}
        onClick={(e) => {
          // The star often sits on top of a tile that is itself a link to the
          // picture; a tap on the star must not also navigate away.
          e.preventDefault();
          e.stopPropagation();
          toggle.mutate();
        }}
      >
        {saved ? <IconStarFilled size={13} /> : <IconStar size={13} />}
      </ActionIcon>
    </Tooltip>
  );
}
