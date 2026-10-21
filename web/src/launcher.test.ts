import { describe, expect, it } from "vitest";

import { contrast, over, parseColour } from "./contrast";
import { filterApps, monogram, TILE_COLOURS, tileColour } from "./launcher";
import type { AppInfo } from "./types";

// Invented apps (docs/PRIVACY.md).
const apps: AppInfo[] = [
  { id: "com.example.cafe", name: "Café Radio" },
  { id: "com.example.nature", name: "Nature Hour" },
  { id: "com.example.tv", name: "TV" },
  { id: "com.example.weather", name: "Weather Now" },
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
    for (const colour of TILE_COLOURS) {
      const base = parseColour(colour);
      expect(contrast(white, base)).toBeGreaterThanOrEqual(4.5);
      expect(contrast(white, over(highlight, base))).toBeGreaterThanOrEqual(4.5);
    }
  });
});
