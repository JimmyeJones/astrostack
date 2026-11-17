import { Center, Loader, Stack, Title } from "@mantine/core";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import { QueryError } from "../components/QueryError";
import { AtAGlance } from "../components/dashboard/AtAGlance";
import { DashboardInsights } from "../components/dashboard/DashboardInsights";
import { DashboardNotices } from "../components/dashboard/DashboardNotices";
import { GettingStarted } from "../components/dashboard/GettingStarted";
import { YourPictures } from "../components/dashboard/YourPictures";

// Kept importable from here: the recent-picture download helper predates the
// split of this page into its groups.
export { triggerPictureDownload } from "../components/dashboard/YourPictures";

/**
 * The home page, in **five top-level groups** — the owner's "recursive
 * organization" rule (AGENTS.md §1, 2026-11-17), checked by
 * `Dashboard.test.tsx` ("five groups"):
 *
 * 1. **Notices** — one prioritised board for every setup problem, fault and
 *    offer; the top two inline, the rest folded behind "N more notes".
 * 2. **Getting started** — the first-run map and the sample image (both
 *    self-hide on an established install).
 * 3. **At a glance** — the stat tiles, then the sky-coverage and life-list lines.
 * 4. **Your pictures** — newest and best, as two tabs of one section.
 * 5. **Insights** — tonight / recent / progress, as tabs.
 *
 * Each group lives in `components/dashboard/`. **A new Dashboard feature joins
 * one of these groups**: a warning goes on the notice board, a number into At a
 * glance, an analysis card into an Insights tab. It never goes onto this page as
 * a block of its own.
 */
export function Dashboard() {
  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: ["stats"], queryFn: api.getStats, refetchInterval: 10_000,
  });

  if (isError && !data) {
    return <QueryError error={error} onRetry={() => refetch()} />;
  }
  if (isLoading || !data) {
    return <Center h={300}><Loader /></Center>;
  }

  return (
    <Stack data-testid="dashboard">
      {/* Above the title on purpose: a blocking setup problem is the first
          thing the page says. */}
      <DashboardNotices />
      <Title order={2}>Dashboard</Title>
      <GettingStarted />
      <AtAGlance data={data} />
      <YourPictures stats={data} />
      <DashboardInsights />
    </Stack>
  );
}
