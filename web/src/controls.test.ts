import { describe, expect, it } from "vitest";

import {
  estimatePosition,
  formatTime,
  keyFor,
  mediaButtons,
  pressAction,
  subtitle,
} from "./controls";
import type { Controls, NowPlaying } from "./types";

const playing: NowPlaying = {
  state: "playing",
  title: "Morning Light",
  artist: "The Example Band",
  album: "Daybreak",
  series: null,
  app: "Music",
  position: 60,
  totalTime: 214,
};

describe("now playing", () => {
  it("formats times", () => {
    expect(formatTime(0)).toBe("0:00");
    expect(formatTime(65.9)).toBe("1:05");
    expect(formatTime(3723)).toBe("1:02:03");
    expect(formatTime(-5)).toBe("0:00");
  });

  it("counts on while playing, and stops at the end", () => {
    expect(estimatePosition(playing, 10)).toBe(70);
    expect(estimatePosition(playing, 1000)).toBe(214);
    expect(estimatePosition({ ...playing, state: "paused" }, 10)).toBe(60);
    expect(estimatePosition({ ...playing, position: null }, 10)).toBeNull();
    expect(estimatePosition({ ...playing, totalTime: null }, 5)).toBe(65);
  });

  it("picks a subtitle", () => {
    expect(subtitle(playing)).toBe("The Example Band");
    expect(subtitle({ ...playing, artist: null, series: "Nature Hour" })).toBe("Nature Hour");
    expect(subtitle({ ...playing, artist: null })).toBe("Daybreak");
    expect(subtitle({ ...playing, artist: null, album: null })).toBeNull();
  });
});

describe("remote", () => {
  const controls: Controls = {
    remote: true,
    media: ["next", "play_pause", "previous"],
    volume: "steps",
    volumeLevel: null,
    power: "on",
    canPower: true,
    nowPlaying: null,
    apps: false,
    textEntry: false,
    keyboard: false,
  };

  it("lays out only the media buttons the device offers", () => {
    expect(mediaButtons(controls)).toEqual(["previous", "play_pause", "next"]);
  });

  it("tells a tap from a hold", () => {
    expect(pressAction(120)).toBe("tap");
    expect(pressAction(600)).toBe("hold");
  });

  it("maps keyboard keys to remote keys", () => {
    expect(["ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight", "Enter", "Backspace", "a"].map(keyFor)).toEqual(
      ["up", "down", "left", "right", "select", "menu", null],
    );
  });
});
