import { describe, expect, it } from "vitest";

import { fitWithin, MAX_SIDE } from "./photo";

describe("fitWithin", () => {
  it("shrinks a big photo so its long side is MAX_SIDE", () => {
    expect(fitWithin(6000, 4000)).toEqual({ width: MAX_SIDE, height: 1707 });
    expect(fitWithin(3000, 6000)).toEqual({ width: 1280, height: MAX_SIDE });
  });

  it("leaves a small one alone", () => {
    expect(fitWithin(800, 600)).toEqual({ width: 800, height: 600 });
  });
});
