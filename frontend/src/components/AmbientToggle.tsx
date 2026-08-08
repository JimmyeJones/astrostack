/** Header speaker button for the optional "space ambient" soundbed.
 *
 * One click to start, one click to silence — no menu-diving, which is the whole
 * bargain for a feature that makes noise. Off on a fresh install; the opt-in is
 * remembered per device (`ambient/prefs.ts`), never on the server.
 *
 * Autoplay policy shapes the two behaviours worth knowing about:
 *  - the `AudioContext` is only ever created/resumed inside this click handler,
 *    and the button shows "on" only if that actually succeeded — it never lies
 *    about playing;
 *  - after a reload, a device that had it on can't just start (browsers refuse),
 *    so it waits for the first click or keypress anywhere in the app and picks
 *    up from there.
 */
import { ActionIcon, Tooltip } from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { IconMusic, IconMusicOff } from "@tabler/icons-react";
import { useCallback, useEffect, useState, useSyncExternalStore } from "react";

import { ambientPlayer, ambientSupported } from "../ambient/player";
import { ambientVolume, isAmbientEnabled, setAmbientEnabled } from "../ambient/prefs";

export function AmbientToggle() {
  const player = ambientPlayer(ambientVolume());
  const [busy, setBusy] = useState(false);
  const state = useSyncExternalStore(
    useCallback((cb: () => void) => player.subscribe(cb), [player]),
    () => player.state,
    () => "stopped" as const,
  );
  const playing = state === "playing";

  // Resume a remembered opt-in on the first gesture after a reload. Not autoplay:
  // the user turned this on, on this device, and nothing sounds until they touch
  // the page again.
  useEffect(() => {
    if (!ambientSupported() || !isAmbientEnabled()) return;
    const onGesture = () => {
      window.removeEventListener("pointerdown", onGesture);
      window.removeEventListener("keydown", onGesture);
      void player.start();
    };
    window.addEventListener("pointerdown", onGesture);
    window.addEventListener("keydown", onGesture);
    return () => {
      window.removeEventListener("pointerdown", onGesture);
      window.removeEventListener("keydown", onGesture);
    };
  }, [player]);

  if (!ambientSupported()) return null;

  const toggle = async () => {
    setBusy(true);
    try {
      if (playing) {
        // Persist first: the fade-out takes a couple of seconds and a reload
        // during it should still come back silent.
        setAmbientEnabled(false);
        await player.stop();
      } else {
        const started = await player.start();
        setAmbientEnabled(started);
        if (!started) {
          notifications.show({
            color: "yellow",
            title: "Couldn't start the ambient sound",
            message: "This browser blocked audio playback. Try again, or check that the tab isn't muted.",
          });
        }
      }
    } finally {
      setBusy(false);
    }
  };

  const label = playing ? "Turn off ambient sound" : "Play ambient sound";
  return (
    <Tooltip
      label={
        playing
          ? "Ambient sound is playing — click to silence it"
          : "Play a quiet, slow-pulsing chill soundbed while you work (off by default)"
      }
      withArrow
    >
      <ActionIcon
        variant={playing ? "light" : "subtle"}
        color={playing ? "violet" : "gray"}
        aria-label={label}
        aria-pressed={playing}
        loading={busy}
        onClick={() => void toggle()}
        size="lg"
      >
        {playing ? <IconMusic size={18} /> : <IconMusicOff size={18} />}
      </ActionIcon>
    </Tooltip>
  );
}
