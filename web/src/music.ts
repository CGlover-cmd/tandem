// What the Music tab and the now-playing bar show (Phase 6). Kept apart from React so it's
// tested. Titles are personal: they go on screen only, never to a log.

import type { Music, MusicCommand } from "./types";

/** The artwork's address on Tandem's own server. It needs this launch's token, taken from
 *  the page's own address; `version` changes with the artwork, so a new one is fetched. */
export function artworkUrl(search: string, version: number): string {
  const token = new URLSearchParams(search).get("token") ?? "";
  return `/artwork?token=${encodeURIComponent(token)}&v=${version}`;
}

/** Where playback is now: the app reports the position only now and then, so we count on. */
export function musicPosition(music: Music, elapsedSeconds: number): number | null {
  if (music.position === null) return null;
  const moving = music.state === "playing" ? Math.max(0, elapsedSeconds) : 0;
  const position = music.position + moving;
  return music.duration === null ? position : Math.min(position, music.duration);
}

/** The line under the title: "Artist · Album", or whichever of the two there is. */
export function musicSubtitle(music: Music): string | null {
  const parts = [music.artist, music.album].filter((part): part is string => !!part);
  return parts.length > 0 ? parts.join(" · ") : null;
}

export function isPlaying(music: Music): boolean {
  return music.state === "playing";
}

export function allows(music: Music, command: MusicCommand): boolean {
  return music.commands.includes(command);
}

/** A slider when the app lets us seek, a bar when it only tells us, nothing for live streams. */
export function progressKind(music: Music): "seek" | "bar" | "live" {
  if (music.duration === null || music.duration <= 0 || music.position === null) return "live";
  return music.canSeek ? "seek" : "bar";
}
