// The app launcher and text entry on the remote sheet. Kept apart from React so it's tested.

import type { AppInfo } from "./types";

/** Lower case with accents removed, so "cafe" finds "Café". */
function fold(text: string): string {
  return text.normalize("NFD").replace(/\p{Diacritic}/gu, "").toLocaleLowerCase();
}

/** Apps whose name contains every word typed, in the order given. */
export function filterApps(apps: AppInfo[], query: string): AppInfo[] {
  const words = fold(query).split(/\s+/).filter(Boolean);
  if (words.length === 0) return apps;
  return apps.filter((app) => {
    const name = fold(app.name);
    return words.every((word) => name.includes(word));
  });
}

/** One or two letters for an app's tile: the first letters of its first two words. */
export function monogram(name: string): string {
  const words = name.trim().split(/\s+/).filter(Boolean);
  const letters = words.slice(0, 2).map((word) => Array.from(word)[0] ?? "");
  return letters.join("").toLocaleUpperCase() || "?";
}

/** Tile colours. White text on each passes WCAG AA (launcher.test.ts checks). */
export const TILE_COLOURS = [
  "#2557c4",
  "#4b44b5",
  "#7a35a8",
  "#a82f66",
  "#b0362d",
  "#9a4a14",
  "#23653a",
  "#0f6c66",
] as const;

/** Apps built into tvOS that aren't on the App Store: Tandem draws their icons. Keep in step
 *  with DRAWN in tandem/ui/app_icons.py. */
export type Glyph = "settings" | "search" | "store" | "arcade" | "computers";
export const DRAWN_APPS: Record<string, { glyph: Glyph; colour: string }> = {
  "com.apple.TVSettings": { glyph: "settings", colour: "#4a5363" },
  "com.apple.TVSearch": { glyph: "search", colour: "#4a5363" },
  "com.apple.TVAppStore": { glyph: "store", colour: "#2557c4" },
  "com.apple.Arcade": { glyph: "arcade", colour: "#b0362d" },
  "com.apple.TVHomeSharing": { glyph: "computers", colour: "#0f6c66" },
};

/** The same app always gets the same colour. */
export function tileColour(appId: string): string {
  let hash = 0;
  for (const char of appId) hash = (hash * 31 + char.codePointAt(0)!) >>> 0;
  return TILE_COLOURS[hash % TILE_COLOURS.length]!;
}

/** Wait this long after the last keystroke before sending text to the TV. */
export const TYPING_PAUSE_MS = 250;

/** The longest text sent to a device (Python's MAX_TEXT in tandem.ui.backend). */
export const MAX_TEXT = 500;
