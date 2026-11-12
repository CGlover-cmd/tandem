import { describe, expect, it } from "vitest";

import { cardButtons, castFor, statusFor } from "./devices";
import { strings } from "./strings";
import type { CastPanel, Device } from "./types";

const tv: Device = {
  id: "demo-tv",
  name: "Living Room TV",
  kind: "apple_tv",
  state: "connected",
  needsPairing: false,
  retryIn: null,
  apps: null,
  controls: null,
  send: null,
  audio: "off",
};
const speaker: Device = { ...tv, id: "demo-speaker-1", name: "Patio Speaker", kind: "homepod" };

function active(state: "starting" | "playing" | "ended" | "failed", deviceId = tv.id): CastPanel["active"] {
  return { deviceId, state, problem: state === "failed" ? { code: "castRefused" } : null };
}

describe("cast screen on the card", () => {
  it("offers Screen on an Apple TV only, when the PC has a screen", () => {
    expect(cardButtons(tv, true).cast).toBe(true);
    expect(cardButtons(tv).cast).toBe(false);
    expect(cardButtons(speaker, true).cast).toBe(false);
    expect(cardButtons({ ...tv, needsPairing: true }, true).cast).toBe(true); // pairs first
  });

  it("follows the cast to this TV only", () => {
    expect(castFor(tv, null)).toBe("off");
    expect(castFor(tv, active("starting"))).toBe("starting");
    expect(castFor(tv, active("playing"))).toBe("on");
    expect(castFor(tv, active("ended"))).toBe("off");
    expect(castFor(tv, active("failed"))).toBe("off");
    expect(castFor(tv, active("playing", "demo-den-tv"))).toBe("off");
  });

  it("says so in the card's status", () => {
    expect(statusFor(tv, 0, "on")).toEqual({ text: strings.status.casting, tone: "success" });
    expect(statusFor(tv, 0, "starting")).toEqual({ text: strings.status.startingCast, tone: "accent" });
    expect(statusFor(tv, 0).text).toBe(strings.status.connected);
    expect(statusFor({ ...tv, needsPairing: true }, 0, "on").text).toBe(strings.status.needsPairing);
  });

  it("names screens by place and size, never by monitor name", () => {
    expect(strings.castSheet.screenName(1, true)).toBe("Screen 1 (main)");
    expect(strings.castSheet.screenName(2, false)).toBe("Screen 2");
    expect(strings.castSheet.size(2560, 1440)).toBe("2560 × 1440");
  });

  it("never calls it AirPlay", () => {
    const words = JSON.stringify(strings.castSheet) + strings.action.cast + strings.status.casting;
    expect(words).not.toMatch(/airplay|mirror/i);
    expect(strings.castSheet.subtitle).toContain("Works with Apple TV");
  });
});
