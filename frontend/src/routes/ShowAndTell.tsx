import { useCallback, useEffect, useRef, useState } from "react";
import {
  ActionIcon, Anchor, Box, Button, Center, Group, Loader, Stack, Text, Title, Tooltip,
} from "@mantine/core";
import {
  IconArrowsMaximize, IconChevronLeft, IconChevronRight, IconPlayerPause,
  IconPlayerPlay, IconSparkles, IconX,
} from "@tabler/icons-react";
import { useQuery } from "@tanstack/react-query";
import { Link, useSearchParams } from "react-router-dom";
import { api } from "../api/client";
import { QueryError } from "../components/QueryError";
import { SLIDE_MS, buildSlides, nextIndex, startIndexFor } from "../showAndTell";

/**
 * Hold the screen awake while the show is playing.
 *
 * The whole point of the feature is "point a screen at it and walk away", and a
 * tablet or laptop dimming three pictures in is the one failure that makes it
 * feel broken in the room. Every call is guarded: the Screen Wake Lock API is
 * absent on some browsers (and in the test DOM), and it *rejects* when the page
 * isn't visible — a slideshow that throws on the way to the TV is worse than one
 * that lets the screen dim. Browsers also drop the lock whenever the tab is
 * hidden, so it is re-requested on `visibilitychange`; nothing is persisted and
 * nothing is configurable.
 */
function useKeepAwake(active: boolean) {
  useEffect(() => {
    if (!active) return undefined;
    const wl = (navigator as Navigator & {
      wakeLock?: { request: (t: "screen") => Promise<{ release: () => Promise<void> }> };
    }).wakeLock;
    if (!wl || typeof wl.request !== "function") return undefined;

    let released = false;
    let sentinel: { release: () => Promise<void> } | null = null;

    const acquire = async () => {
      if (released || document.visibilityState !== "visible") return;
      try {
        sentinel = await wl.request("screen");
      } catch {
        // Denied, unsupported on this surface, or the page went hidden between
        // the check and the call. Nothing to do — the screen just dims.
      }
    };
    const onVisible = () => { if (document.visibilityState === "visible") void acquire(); };

    void acquire();
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      released = true;
      document.removeEventListener("visibilitychange", onVisible);
      try {
        void sentinel?.release();
      } catch {
        // A lock the browser already dropped throws on release; harmless.
      }
    };
  }, [active]);
}

/**
 * "Show and tell" — a hands-off, room-filling slideshow of your best pictures.
 *
 * Everything else the app offers for *enjoying* a finished picture is either one
 * artefact at a time (share JPEG, wallpaper, print) or a grid you have to click
 * through. This is the thing a proud beginner actually wants when someone says
 * "show me what you've shot": point a screen at it and it plays — big picture,
 * big caption, no configuration, forever.
 *
 * Read-only over endpoints that already exist (the ranked "My best pictures"
 * wall and the finished Moon/Sun stills), so it renders no masters and touches
 * nothing on disk. It paints a fixed full-viewport layer over the app shell
 * rather than living inside it, because a slideshow with a sidebar isn't one.
 *
 * Only the picture on screen is ever mounted, so a big library doesn't pull
 * thirty previews at once; the next one is warmed in a hidden preloader so the
 * dissolve never lands on a blank frame.
 */
export function ShowAndTellView() {
  const best = useQuery({ queryKey: ["galleryBest"], queryFn: () => api.getGalleryBest() });
  const gallery = useQuery({ queryKey: ["gallery"], queryFn: api.getGallery });

  const [index, setIndex] = useState(0);
  const [paused, setPaused] = useState(false);
  const rootRef = useRef<HTMLDivElement | null>(null);
  const [params] = useSearchParams();
  const from = params.get("from");

  const slides = buildSlides(best.data?.items, gallery.data?.videos);
  const count = slides.length;

  // "Show me this one": opened from a lightbox, the show starts on that picture
  // and keeps looping through everything after it. Applied once, the first time
  // the slides arrive — after that the user is driving, and a background refetch
  // must never yank them back to where they came in.
  const startedFrom = useRef(false);
  useEffect(() => {
    if (startedFrom.current || count === 0) return;
    startedFrom.current = true;
    setIndex(startIndexFor(slides, from));
  }, [count, from, slides]);

  // Keep the screen awake while the show is actually playing — not while it's
  // paused, which is someone stopping to look, or on an empty show.
  useKeepAwake(count > 0 && !paused);

  const go = useCallback((step: number) => {
    setIndex((i) => nextIndex(i, count, step));
  }, [count]);

  // Auto-advance. A single picture simply rests — there is nothing to cross-fade
  // to, and a one-slide "show" that flickered would look broken.
  useEffect(() => {
    if (paused || count < 2) return undefined;
    const t = setInterval(() => go(1), SLIDE_MS);
    return () => clearInterval(t);
  }, [paused, count, go]);

  // Keyboard: the controls a room expects without hunting for a button.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === " " || e.key === "k") {
        e.preventDefault();
        setPaused((p) => !p);
      } else if (e.key === "ArrowRight") {
        go(1);
      } else if (e.key === "ArrowLeft") {
        go(-1);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [go]);

  const goFullscreen = () => {
    const el = rootRef.current;
    // Guarded: not every browser (and no test DOM) has the Fullscreen API, and a
    // slideshow that throws on the way to the TV is worse than one that doesn't
    // offer the button.
    if (el && typeof el.requestFullscreen === "function") void el.requestFullscreen();
  };

  if (best.isError && !best.data && gallery.isError && !gallery.data) {
    return <QueryError error={best.error} onRetry={() => { void best.refetch(); void gallery.refetch(); }} />;
  }
  if (best.isLoading || gallery.isLoading) {
    return <Center h={300}><Loader /></Center>;
  }

  if (count === 0) {
    return (
      <Stack>
        <Group gap="xs">
          <IconSparkles size={24} />
          <Title order={2}>Show and tell</Title>
        </Group>
        <Text c="dimmed">
          Nothing to show yet. Once you&apos;ve finished stacking a target — or
          made a Moon or Sun picture — this plays them full-screen, one after
          another, with their names on. It&apos;s the easy way to show someone
          what you&apos;ve been shooting.
        </Text>
        <Group>
          <Button component={Link} to="/library" variant="light">Go to your library</Button>
        </Group>
      </Stack>
    );
  }

  // A background refetch can shrink the list under us (a preview deleted, a
  // target pruned), so never index past the end — the show just lands on the
  // last picture instead of crashing on an undefined slide.
  const at = Math.min(index, count - 1);
  const current = slides[at];
  const upcoming = count > 1 ? slides[nextIndex(at, count, 1)] : null;

  return (
    <Box
      ref={rootRef}
      data-testid="show-and-tell"
      style={{
        position: "fixed", inset: 0, zIndex: 300, background: "#000",
        display: "flex", flexDirection: "column",
      }}
    >
      {/* One picture at a time, dissolving in from the black behind it. Keyed on
          the slide so the animation re-runs on every change. */}
      <style>
        {"@keyframes astrostack-show-fade{from{opacity:0}to{opacity:1}}"}
      </style>
      <Box style={{ position: "relative", flex: 1, minHeight: 0 }}>
        <img
          key={current.key}
          src={current.src}
          alt={current.title}
          style={{
            position: "absolute", inset: 0, width: "100%", height: "100%",
            objectFit: "contain",
            animation: "astrostack-show-fade 1.2s ease",
          }}
        />
        {/* Warm the next picture so the dissolve never lands on a blank. */}
        {upcoming && upcoming.key !== current.key ? (
          <img src={upcoming.src} alt="" aria-hidden style={{ display: "none" }} />
        ) : null}
      </Box>

      <Box px="lg" pb="md" pt="xs" style={{ background: "#000", color: "#fff" }}>
        <Title order={2} c="#fff">{current.title}</Title>
        {current.fact ? (
          <Text size="lg" c="#dfd8ff" mt={4}>{current.fact}</Text>
        ) : null}
        <Group justify="space-between" mt="xs" wrap="nowrap" gap="sm">
          <Text size="sm" c="dimmed">
            {current.meta}
            {count > 1 ? `${current.meta ? "  ·  " : ""}${at + 1} of ${count}` : ""}
          </Text>
          <Group gap={4} wrap="nowrap">
            {current.href ? (
              <Anchor component={Link} to={current.href} size="sm" c="#dfd8ff">
                About this picture
              </Anchor>
            ) : null}
            <Tooltip label="Previous">
              <ActionIcon
                variant="subtle" color="gray" aria-label="Previous picture"
                onClick={() => go(-1)} disabled={count < 2}
              >
                <IconChevronLeft size={18} />
              </ActionIcon>
            </Tooltip>
            <Tooltip label={paused ? "Play" : "Pause"}>
              <ActionIcon
                variant="subtle" color="gray"
                aria-label={paused ? "Play slideshow" : "Pause slideshow"}
                onClick={() => setPaused((p) => !p)} disabled={count < 2}
              >
                {paused ? <IconPlayerPlay size={18} /> : <IconPlayerPause size={18} />}
              </ActionIcon>
            </Tooltip>
            <Tooltip label="Next">
              <ActionIcon
                variant="subtle" color="gray" aria-label="Next picture"
                onClick={() => go(1)} disabled={count < 2}
              >
                <IconChevronRight size={18} />
              </ActionIcon>
            </Tooltip>
            <Tooltip label="Full screen">
              <ActionIcon
                variant="subtle" color="gray" aria-label="Full screen"
                onClick={goFullscreen}
              >
                <IconArrowsMaximize size={18} />
              </ActionIcon>
            </Tooltip>
            <Tooltip label="Close the slideshow">
              <ActionIcon
                variant="subtle" color="gray" aria-label="Close the slideshow"
                component={Link} to="/best"
              >
                <IconX size={18} />
              </ActionIcon>
            </Tooltip>
          </Group>
        </Group>
      </Box>
    </Box>
  );
}
