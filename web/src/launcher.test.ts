import { describe, expect, it } from "vitest";

import { contrast, over, parseColour } from "./contrast";
import {
  DRAWN_APPS,
  filterApps,
  keyboardMove,
  monogram,
  moveItem,
  slotAt,
  TILE_COLOURS,
  tileColour,
} from "./launcher";
import type { AppInfo } from "./types";

// Invented apps (docs/PRIVACY.md).
const apps: AppInfo[] = [
  { id: "com.example.cafe", name: "Café Radio", icon: null },
  { id: "com.example.nature", name: "Nature Hour", icon: null },
  { id: "com.example.tv", name: "TV", icon: null },
  { id: "com.example.weather", name: "Weather Now", icon: null },
];

describe("filterApps", () => {
  it("returns everything for an empty search", () => {
    expect(filterApps(apps, "  ")).toEqual(apps);
  });

  it("matches parts of names, ignoring case and accents", () => {
    expect(filterApps(apps, "CAFE").map((a) => a.id)).toEqual(["com.example.cafe"]);
    expect(filterApps(apps, "ow").map((a) => a.id)).toEqual(["com.example.weather"]);
  });

  it("needs every word typed", () => {
    expect(filterApps(apps, "hour nat").map((a) => a.id)).toEqual(["com.example.nature"]);
    expect(filterApps(apps, "hour radio")).toEqual([]);
  });
});

describe("monogram", () => {
  it("takes the first letters of the first two words", () => {
    expect(monogram("Nature Hour")).toBe("NH");
    expect(monogram("weather now and later")).toBe("WN");
    expect(monogram("TV")).toBe("T");
    expect(monogram("   ")).toBe("?");
  });
});

describe("tile colours", () => {
  it("are stable for an app", () => {
    expect(tileColour("com.example.tv")).toBe(tileColour("com.example.tv"));
    expect(TILE_COLOURS).toContain(tileColour("com.example.tv"));
  });

  it("spread across the palette", () => {
    const used = new Set(apps.map((a) => tileColour(a.id)));
    expect(used.size).toBeGreaterThan(1);
  });

  it("keep white text readable, under the tile's highlight too", () => {
    const white = parseColour("#ffffff");
    const highlight = parseColour("rgba(255, 255, 255, 0.14)");
    for (const colour of [...TILE_COLOURS, ...Object.values(DRAWN_APPS).map((d) => d.colour)]) {
      const base = parseColour(colour);
      expect(contrast(white, base)).toBeGreaterThanOrEqual(4.5);
      expect(contrast(white, over(highlight, base))).toBeGreaterThanOrEqual(4.5);
    }
  });
});

describe("drawn built-in apps", () => {
  it("match the list the Python side never looks up", () => {
    // tandem/ui/app_icons.py DRAWN
    expect(Object.keys(DRAWN_APPS).sort()).toEqual([
      "com.apple.Arcade",
      "com.apple.TVAppStore",
      "com.apple.TVHomeSharing",
      "com.apple.TVSearch",
      "com.apple.TVSettings",
    ]);
  });
});

describe("rearranging", () => {
  it("moves an item forwards and backwards", () => {
    expect(moveItem(["a", "b", "c", "d"], 0, 2)).toEqual(["b", "c", "a", "d"]);
    expect(moveItem(["a", "b", "c", "d"], 3, 0)).toEqual(["d", "a", "b", "c"]);
    expect(moveItem(["a", "b"], 1, 9)).toEqual(["a", "b"]);
    expect(moveItem(["a", "b"], 5, 0)).toEqual(["a", "b"]);
  });

  const grid = { originX: 10, originY: 20, cellWidth: 100, cellHeight: 120, columns: 3, count: 8 };

  it("finds the slot under the pointer", () => {
    expect(slotAt(15, 25, grid)).toBe(0);
    expect(slotAt(250, 30, grid)).toBe(2);
    expect(slotAt(150, 150, grid)).toBe(4);
  });

  it("keeps the slot inside the grid", () => {
    expect(slotAt(-50, -50, grid)).toBe(0);
    expect(slotAt(900, 30, grid)).toBe(2); // past the last column
    expect(slotAt(250, 999, grid)).toBe(7); // below the last row
    expect(slotAt(0, 0, { ...grid, count: 0 })).toBe(0);
  });

  it("moves with Ctrl+Arrow by a step or a row", () => {
    expect(keyboardMove("ArrowRight", 0, 3, 8)).toBe(1);
    expect(keyboardMove("ArrowDown", 1, 3, 8)).toBe(4);
    expect(keyboardMove("ArrowDown", 6, 3, 8)).toBe(7);
    expect(keyboardMove("ArrowUp", 1, 3, 8)).toBe(0);
    expect(keyboardMove("ArrowLeft", 0, 3, 8)).toBeNull();
    expect(keyboardMove("Enter", 2, 3, 8)).toBeNull();
  });
});
