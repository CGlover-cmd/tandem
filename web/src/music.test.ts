import { describe, expect, it } from "vitest";

import {
  allows,
  artworkUrl,
  canSkip,
  isPlaying,
  musicPosition,
  musicSubtitle,
  progressKind,
  seekTarget,
} from "./music";
import type { Music } from "./types";

// Invented music (docs/PRIVACY.md).
const song: Music = {
  app: "Demo Player",
  state: "playing",
  title: "Morning Light",
  artist: "The Example Band",
  album: "Daybreak",
  position: 42,
  duration: 214,
  commands: ["play_pause", "next"],
  canSeek: true,
  artwork: 3,
};

describe("artworkUrl", () => {
  it("carries the page's token and the artwork version", () => {
    expect(artworkUrl("?token=a+b/c", 3)).toBe("/artwork?token=a%20b%2Fc&v=3");
    expect(artworkUrl("", 1)).toBe("/artwork?token=&v=1");
  });
});

describe("musicPosition", () => {
  it("counts on while playing, up to the end", () => {
    expect(musicPosition(song, 8)).toBe(50);
    expect(musicPosition(song, 1000)).toBe(214);
    expect(musicPosition(song, -5)).toBe(42);
  });

  it("stands still while paused, and has none for live streams", () => {
    expect(musicPosition({ ...song, state: "paused" }, 8)).toBe(42);
    expect(musicPosition({ ...song, position: null }, 8)).toBeNull();
    expect(musicPosition({ ...song, duration: null }, 8)).toBe(50);
  });
});

describe("musicSubtitle", () => {
  it("joins artist and album when both are there", () => {
    expect(musicSubtitle(song)).toBe("The Example Band · Daybreak");
    expect(musicSubtitle({ ...song, album: null })).toBe("The Example Band");
    expect(musicSubtitle({ ...song, artist: "", album: "Daybreak" })).toBe("Daybreak");
    expect(musicSubtitle({ ...song, artist: null, album: null })).toBeNull();
  });
});

describe("controls", () => {
  it("offers only what the app allows", () => {
    expect(isPlaying(song)).toBe(true);
    expect(isPlaying({ ...song, state: "paused" })).toBe(false);
    expect(allows(song, "next")).toBe(true);
    expect(allows(song, "previous")).toBe(false);
  });

  it("picks a slider, a bar or a live label", () => {
    expect(progressKind(song)).toBe("seek");
    expect(progressKind({ ...song, canSeek: false })).toBe("bar");
    expect(progressKind({ ...song, duration: null })).toBe("live");
    expect(progressKind({ ...song, duration: 0 })).toBe("live");
    expect(progressKind({ ...song, position: null })).toBe("live");
  });
});

describe("speaker remote skips", () => {
  it("move 15 seconds within the track", () => {
    expect(seekTarget(song, 42, 15)).toBe(57);
    expect(seekTarget(song, 5, -15)).toBe(0);
    expect(seekTarget(song, 210, 15)).toBe(214);
    expect(seekTarget({ ...song, duration: null }, 500, 15)).toBe(515);
  });

  it("are offered only when the app can seek", () => {
    expect(canSkip(song)).toBe(true);
    expect(canSkip({ ...song, canSeek: false })).toBe(false);
    expect(canSkip({ ...song, duration: null })).toBe(false);
  });
});
