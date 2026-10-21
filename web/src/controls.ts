// What the remote sheet shows for a device's controls. Kept apart from React so it's tested.

import type { Controls, MediaCommand, NowPlaying } from "./types";

/** "1:05" or "1:02:03". */
export function formatTime(seconds: number): string {
  const s = Math.max(0, Math.floor(seconds));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = String(s % 60).padStart(2, "0");
  return h > 0 ? `${h}:${String(m).padStart(2, "0")}:${sec}` : `${m}:${sec}`;
}

/** Where playback is now: devices push the position only now and then, so we count on. */
export function estimatePosition(playing: NowPlaying, elapsedSeconds: number): number | null {
  if (playing.position === null) return null;
  const moving = playing.state === "playing" ? elapsedSeconds : 0;
  const position = playing.position + moving;
  return playing.totalTime === null ? position : Math.min(position, playing.totalTime);
}

/** The second line under the title: artist, or series, or album. */
export function subtitle(playing: NowPlaying): string | null {
  return playing.artist ?? playing.series ?? playing.album ?? null;
}

/** Media buttons in the order they sit, left to right, showing only what the device offers. */
export function mediaButtons(controls: Controls): MediaCommand[] {
  const order: MediaCommand[] = ["previous", "skip_backward", "play_pause", "skip_forward", "next"];
  return order.filter((command) => controls.media.includes(command));
}

/** A press shorter than this is a tap; longer is a hold (like the Siri Remote). */
export const HOLD_MS = 600;

export function pressAction(heldMs: number): "tap" | "hold" {
  return heldMs >= HOLD_MS ? "hold" : "tap";
}

/** Keyboard shortcuts on the remote sheet. */
export function keyFor(key: string): "up" | "down" | "left" | "right" | "select" | "menu" | null {
  switch (key) {
    case "ArrowUp":
      return "up";
    case "ArrowDown":
      return "down";
    case "ArrowLeft":
      return "left";
    case "ArrowRight":
      return "right";
    case "Enter":
      return "select";
    case "Backspace":
      return "menu";
    default:
      return null;
  }
}
