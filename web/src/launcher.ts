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

// Rearranging: hold an app to lift it, then drag it into place.

/** Hold this long to lift an app (shorter is a tap that opens it). */
export const HOLD_TO_LIFT_MS = 400;
/** Moving further than this before the hold completes cancels it (the user is scrolling). */
export const DRAG_SLOP_PX = 8;

/** A copy of `list` with the item at `from` moved to `to`. */
export function moveItem<T>(list: readonly T[], from: number, to: number): T[] {
  const result = [...list];
  if (from < 0 || from >= list.length) return result;
  const [item] = result.splice(from, 1);
  const target = Math.max(0, Math.min(to, result.length));
  result.splice(target, 0, item as T);
  return result;
}

/** The grid's layout: where the first cell starts and the size of a cell, gaps included. */
export interface GridLayout {
  originX: number;
  originY: number;
  cellWidth: number;
  cellHeight: number;
  columns: number;
  count: number;
}

/** Which slot a point over the grid falls in, clamped to the slots there are. */
export function slotAt(x: number, y: number, grid: GridLayout): number {
  if (grid.count <= 0) return 0;
  const columns = Math.max(1, grid.columns);
  const column = Math.max(0, Math.min(columns - 1, Math.floor((x - grid.originX) / grid.cellWidth)));
  const row = Math.max(0, Math.floor((y - grid.originY) / grid.cellHeight));
  return Math.min(grid.count - 1, row * columns + column);
}

/** Where Ctrl+Arrow moves a focused app: one step left or right, or a row up or down. */
export function keyboardMove(key: string, index: number, columns: number, count: number): number | null {
  const step = { ArrowLeft: -1, ArrowRight: 1, ArrowUp: -columns, ArrowDown: columns }[key];
  if (step === undefined) return null;
  const target = Math.max(0, Math.min(count - 1, index + step));
  return target === index ? null : target;
}
