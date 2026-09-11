import { useEffect, useMemo, useState } from "react";
import {
  Accordion, Alert, Button, Center, Group, Loader, Stack, Text, TextInput, Title,
} from "@mantine/core";
import { IconBook2, IconSearch } from "@tabler/icons-react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import { GlossaryBody } from "../components/glossaryMarkdown";
import { QueryError } from "../components/QueryError";
import { filterGlossary } from "../glossarySearch";

// "What does this word mean?", answered inside the app.
//
// The glossary is the oldest beginner-facing thing in this repo and, until now,
// the web app had no way to reach it: it lived in `docs/`, which the Dockerfile
// does not copy, and only the historical desktop GUI's F1 key ever opened it. So
// the one UI the owner actually runs said "FWHM", "drizzle", "sigma clipping"
// and "panel depth" on screen with no page anywhere that defines them.
//
// **It is a list of headings, not 38 open entries** — and that is a measurement,
// not a preference. The first build rendered every explanation eagerly and came
// out at **8,194 px on a 420 px phone**, nearly three times the tallest page in
// the app, on the one product whose standing owner complaint is *"I have to
// scroll a fair bit to get to the actual info"*. Collapsed, the whole vocabulary
// fits on about two screens and the word you want is one tap away — the same
// trade `LifeList`'s TODO_PREVIEW and `FrameColumnGuide` already make, and
// nothing is removed (AGENTS.md §1): every entry is still here, "Open them all"
// still reads it end to end, and a `#fwhm` link opens its own entry.

export function GlossaryView() {
  const [query, setQuery] = useState("");
  const [opened, setOpened] = useState<string[]>([]);
  const glossary = useQuery({
    queryKey: ["glossary"],
    queryFn: api.getGlossary,
    // It is a file inside the image: it cannot change while the app runs.
    staleTime: Infinity,
  });

  const terms = glossary.data?.terms ?? [];
  const shown = useMemo(() => filterGlossary(terms, query), [terms, query]);

  // Deep links are the point of the anchors, and the browser cannot honour
  // `#fwhm` on first paint: the entry does not exist yet, and once it does it is
  // closed. So open it and scroll to it ourselves, once the terms land.
  useEffect(() => {
    if (!terms.length) return;
    const hash = decodeURIComponent(window.location.hash.slice(1));
    if (!hash || !terms.some((t) => t.slug === hash)) return;
    setOpened((prev) => (prev.includes(hash) ? prev : [...prev, hash]));
    document.getElementById(`glossary-term-${hash}`)
      ?.scrollIntoView({ block: "start" });
  }, [terms]);

  // A search that lands on exactly one term is a question with one answer, so
  // show it rather than making them tap the thing they just found.
  useEffect(() => {
    if (query.trim() && shown.length === 1) {
      setOpened((prev) => (prev.includes(shown[0].slug) ? prev : [...prev, shown[0].slug]));
    }
  }, [query, shown]);

  if (glossary.isLoading) {
    return <Center h="40vh"><Loader /></Center>;
  }
  if (glossary.isError) {
    return <QueryError error={glossary.error} onRetry={() => glossary.refetch()} />;
  }

  const allOpen = shown.length > 0 && shown.every((t) => opened.includes(t.slug));

  return (
    <Stack gap="md">
      <Group gap="xs">
        <IconBook2 size={22} />
        <Title order={2}>Glossary</Title>
      </Group>
      {glossary.data?.intro ? (
        <Text c="dimmed" component="div"><GlossaryBody body={glossary.data.intro} /></Text>
      ) : null}

      <TextInput
        value={query}
        onChange={(e) => setQuery(e.currentTarget.value)}
        leftSection={<IconSearch size={16} />}
        label="Find a term"
        description="Searches the explanations as well as the names — “satellite” finds the ones about satellite trails."
        placeholder="e.g. drizzle, FWHM, sigma clipping"
        data-testid="glossary-search"
      />

      {!terms.length ? (
        <Alert color="yellow" variant="light" title="The glossary didn’t load">
          <Text size="sm">
            This build doesn’t have the glossary file. Nothing else is affected —
            it’s a reference page, not part of processing.
          </Text>
        </Alert>
      ) : !shown.length ? (
        <Alert color="gray" variant="light" title={`Nothing here matches “${query}”`}>
          <Text size="sm">
            Try a shorter word, or clear the box to read the whole list. If a term
            you saw in the app really is missing, it belongs here — the list is
            meant to cover everything the interface says out loud.
          </Text>
        </Alert>
      ) : (
        <>
          <Group justify="space-between" align="center">
            <Text size="xs" c="dimmed">
              {query.trim()
                ? `${shown.length} of ${terms.length} terms`
                : `${terms.length} terms · tap one to read it`}
            </Text>
            <Button size="compact-xs" variant="subtle"
                    data-testid="glossary-open-all"
                    onClick={() => setOpened(allOpen ? [] : shown.map((t) => t.slug))}>
              {allOpen ? "Close them all" : "Open them all"}
            </Button>
          </Group>
          <Accordion multiple variant="separated" value={opened} onChange={setOpened}>
            {shown.map((t) => (
              // The anchor lives on the item, not on the control, so a browser
              // that *does* honour `#fwhm` lands on the whole entry.
              <Accordion.Item key={t.slug} value={t.slug} id={`glossary-term-${t.slug}`}
                              style={{ scrollMarginTop: 70 }}>
                <Accordion.Control data-testid={`glossary-control-${t.slug}`}>
                  <Text fw={600} size="sm">{t.term}</Text>
                </Accordion.Control>
                <Accordion.Panel>
                  <GlossaryBody body={t.body} />
                </Accordion.Panel>
              </Accordion.Item>
            ))}
          </Accordion>
        </>
      )}
    </Stack>
  );
}
