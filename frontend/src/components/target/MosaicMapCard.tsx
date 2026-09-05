import { Box, Group, Paper, Stack, Text, ThemeIcon, Tooltip } from "@mantine/core";
import { IconGridDots } from "@tabler/icons-react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../../api/client";
import { panelGrid, panelShade, panelTooltip } from "./mosaicMap";

/**
 * "Your mosaic, panel by panel" — a small map of where the mosaic is thin.
 *
 * The readiness figure already scales a mosaic's goal by its panel count, so a
 * 4-panel mosaic with an hour on each honestly reads "a quarter done". That says
 * *how much* is left; this says **where**. For a heavy mosaic user shooting one
 * target across many nights, a mosaic whose total looks healthy can still have
 * one corner at a fifth of the others — and that corner is grainier than the
 * rest of the picture however good the total is. Working that out today means
 * reading the frames table and doing the geometry by eye.
 *
 * Read-only, nothing to configure, and **self-hiding**: the endpoint returns
 * `null` unless the target is clearly a mosaic (the engine's own shared panel
 * gate, the same one QC grading uses), so a single-field target — and an older
 * backend without the endpoint — sees nothing at all.
 *
 * Drawn North-up and East-left, the orientation every astro image is in, so the
 * grid matches the picture above it rather than a table of numbers.
 */
export function MosaicMapCard({ safe }: { safe: string }) {
  const q = useQuery({
    queryKey: ["mosaic-map", safe],
    queryFn: () => api.mosaicMap(safe),
    enabled: !!safe,
    retry: false,
  });

  const map = q.data;
  if (!map || !map.panels.length || map.rows < 1 || map.cols < 1) return null;
  const grid = panelGrid(map);

  return (
    <Paper withBorder p="sm" radius="md" mt="xs">
      <Group gap="sm" wrap="nowrap" align="flex-start">
        <ThemeIcon size={22} radius="xl" variant="light" color="indigo"
          style={{ flexShrink: 0, marginTop: 2 }}>
          <IconGridDots size={14} />
        </ThemeIcon>
        <Stack gap={6} style={{ flex: 1, minWidth: 0 }}>
          <Text size="sm" fw={500}>Your mosaic, panel by panel</Text>
          <Text size="xs" c="dimmed">{map.text}</Text>
          {/* The grid itself. Capped in width so a wide mosaic stays a map
              rather than stretching into a banner on a phone. */}
          <Box
            data-testid="mosaic-panel-grid"
            style={{
              display: "grid",
              gridTemplateColumns: `repeat(${map.cols}, minmax(0, 1fr))`,
              gap: 3,
              maxWidth: Math.min(320, map.cols * 56),
              marginTop: 2,
            }}
          >
            {grid.flatMap((cells, row) =>
              cells.map((panel, col) => {
                if (!panel) {
                  // A gap in the mosaic: drawn, not squeezed out, so the panels
                  // that *are* there stay where they are in the sky.
                  return (
                    <Box
                      key={`${row}-${col}`}
                      aria-hidden
                      style={{
                        height: 26, borderRadius: 4,
                        border: "1px dashed var(--mantine-color-dimmed)",
                        opacity: 0.25,
                      }}
                    />
                  );
                }
                const shade = panelShade(panel, map);
                const isThin = !!map.thin
                  && map.thin.row === row && map.thin.col === col;
                const tip = panelTooltip(panel, map);
                return (
                  <Tooltip key={`${row}-${col}`} label={tip} withArrow openDelay={200}>
                    <Box
                      aria-label={tip}
                      style={{
                        height: 26,
                        borderRadius: 4,
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "center",
                        // Deeper panel = more solid indigo; the thin one stays
                        // pale, which is the whole point of looking at this.
                        backgroundColor: `rgba(76, 110, 245, ${0.12 + shade * 0.78})`,
                        border: isThin
                          ? "2px solid var(--mantine-color-orange-5)"
                          : "1px solid transparent",
                        color: shade > 0.5 ? "white" : "var(--mantine-color-dimmed)",
                        fontSize: 10,
                        fontWeight: isThin ? 700 : 500,
                      }}
                    >
                      {isThin ? "thin" : ""}
                    </Box>
                  </Tooltip>
                );
              }),
            )}
          </Box>
        </Stack>
      </Group>
    </Paper>
  );
}
