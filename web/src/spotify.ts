// Small helpers for the Spotify parts of the window. Python keeps the state; these only shape
// what is shown.

import { formatTime } from "./controls";
import { strings } from "./strings";
import type { Spotify, SpotifyItem } from "./types";

const words = strings.spotify;

/** The artwork address on Tandem's own server (the page may load images only from Tandem). */
export function spotifyArtUrl(search: string, id: string): string {
  const token = encodeURIComponent(new URLSearchParams(search).get("token") ?? "");
  return `/spotify-art/${encodeURIComponent(id)}?token=${token}`;
}

/** The line under an item's title: who made it, its album or year, and its length. */
export function itemDetail(item: SpotifyItem): string {
  const parts = [item.kind === "track" ? null : words.kind[item.kind], item.subtitle || null];
  if (item.duration !== null) parts.push(formatTime(item.duration));
  if (item.count !== null) parts.push(words.tracks(item.count));
  return parts.filter(Boolean).join(" · ");
}

/** Which part of the setup walkthrough is next. */
export type SetupStep = "clientId" | "signIn" | "done";

export function setupStep(spotify: Spotify): SetupStep {
  switch (spotify.state) {
    case "not_set_up":
      return "clientId";
    case "signed_out":
    case "signing_in":
      return "signIn";
    case "signed_in":
      return "done";
  }
}

/** The name of the device "Play" uses, if any. */
export function targetName(spotify: Spotify): string | null {
  return spotify.devices.find((d) => d.id === spotify.target)?.name ?? null;
}

/** A Client ID as Spotify shows it: 32 hex characters (spaces around it are fine). */
export function looksLikeClientId(text: string): boolean {
  return /^[0-9a-f]{32}$/i.test(text.trim());
}
