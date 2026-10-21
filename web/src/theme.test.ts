import { describe, expect, it } from "vitest";

import { contrast, over, parseColour } from "./contrast";
import { backgroundCss, backgrounds, findBackground, palettes, type Mode } from "./theme";

const MODES: Mode[] = ["light", "dark"];
const AA_TEXT = 4.5;
const AA_UI = 3; // dots, rings and other non-text marks

// Python's list in tandem.ui.backend.BACKGROUNDS.
const PYTHON_BACKGROUNDS = ["mist", "sand", "slate", "sky", "dusk", "meadow", "sunrise", "aurora"];

describe("backgrounds", () => {
  it("match the ids the Python side accepts", () => {
    expect(backgrounds.map((b) => b.id)).toEqual(PYTHON_BACKGROUNDS);
  });

  it("offer neutral tones and gradients", () => {
    expect(backgrounds.filter((b) => b.group === "neutral").length).toBeGreaterThanOrEqual(3);
    expect(backgrounds.filter((b) => b.group === "gradient").length).toBeGreaterThanOrEqual(3);
  });

  it("fall back to the first preset for an unknown id", () => {
    expect(findBackground("plaid").id).toBe("mist");
  });

  it("render as CSS that uses every stop", () => {
    for (const background of backgrounds) {
      for (const mode of MODES) {
        const css = backgroundCss(background, mode);
        for (const stop of background.stops[mode]) expect(css).toContain(stop);
      }
    }
  });
});

describe.each(MODES)("%s mode contrast (WCAG AA)", (mode) => {
  const p = palettes[mode];
  const cases = backgrounds.flatMap((b) => b.stops[mode].map((stop) => [b.id, stop] as const));

  it.each(cases)("text on the %s background (%s)", (_id, stop) => {
    const ground = parseColour(stop);
    expect(contrast(parseColour(p.foreground), ground)).toBeGreaterThanOrEqual(AA_TEXT);
    expect(contrast(parseColour(p.muted), ground)).toBeGreaterThanOrEqual(AA_TEXT);
  });

  it.each(cases)("text and marks on glass over %s (%s)", (_id, stop) => {
    const glass = over(parseColour(p.glass), parseColour(stop));
    expect(contrast(parseColour(p.foreground), glass)).toBeGreaterThanOrEqual(AA_TEXT);
    expect(contrast(parseColour(p.muted), glass)).toBeGreaterThanOrEqual(AA_TEXT);
    expect(contrast(parseColour(p.accentText), glass)).toBeGreaterThanOrEqual(AA_TEXT);
    for (const mark of [p.success, p.warning, p.danger]) {
      expect(contrast(parseColour(mark), glass)).toBeGreaterThanOrEqual(AA_UI);
    }
  });

  it("button text on the accent fill", () => {
    expect(contrast(parseColour(p.accentForeground), parseColour(p.accent))).toBeGreaterThanOrEqual(
      AA_TEXT,
    );
  });

  it.each(cases)("text on a sheet over %s (%s)", (_id, stop) => {
    const sheet = over(parseColour(p.sheet), parseColour(stop));
    expect(contrast(parseColour(p.foreground), sheet)).toBeGreaterThanOrEqual(AA_TEXT);
    expect(contrast(parseColour(p.muted), sheet)).toBeGreaterThanOrEqual(AA_TEXT);
    expect(contrast(parseColour(p.danger), sheet)).toBeGreaterThanOrEqual(AA_TEXT);
  });
});

describe("parseColour", () => {
  it("reads hex and rgba", () => {
    expect(parseColour("#0066CC")).toEqual({ r: 0, g: 102, b: 204, a: 1 });
    expect(parseColour("rgba(1, 2, 3, 0.5)")).toEqual({ r: 1, g: 2, b: 3, a: 0.5 });
    expect(parseColour("rgb(1, 2, 3)")).toEqual({ r: 1, g: 2, b: 3, a: 1 });
    expect(() => parseColour("blue")).toThrow();
  });
});
