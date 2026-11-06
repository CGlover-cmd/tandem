import { describe, expect, it } from "vitest";

import {
  canSend,
  delayLabel,
  delayOutputs,
  groupOutputs,
  isLink,
  outputDirect,
  outputLive,
  outputVolume,
  sendText,
} from "./audio";
import type { AudioOutput, Device } from "./types";

const output = (over: Partial<AudioOutput> = {}): AudioOutput => ({
  id: "demo-speaker-1",
  name: "Patio Speaker",
  kind: "airplay",
  state: "off",
  volume: null,
  delayMs: 0,
  deviceKind: "homepod",
  needsPairing: false,
  ...over,
});

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
};

describe("audio outputs", () => {
  it("count as on while starting, playing or reconnecting", () => {
    expect(outputLive(output())).toBe(false);
    expect(outputLive(output({ state: "failed" }))).toBe(false);
    for (const state of ["starting", "streaming", "waiting"] as const) {
      expect(outputLive(output({ state }))).toBe(true);
    }
  });

  it("show the saved volume, or the middle", () => {
    expect(outputVolume(output())).toBe(50);
    expect(outputVolume(output({ volume: 20 }))).toBe(20);
  });

  it("group AirPlay first, then the PC", () => {
    const pc = output({ id: "demo-pc-headphones", kind: "pc", deviceKind: null });
    expect(groupOutputs([pc, output()])).toEqual({ airplay: [output()], pc: [pc] });
    expect(delayLabel(1250)).toBe("1.3 s");
  });
});

describe("send to TV", () => {
  it("is offered on a connected Apple TV only", () => {
    expect(canSend(tv)).toBe(true);
    expect(canSend({ ...tv, state: "disconnected" })).toBe(false);
    expect(canSend({ ...tv, kind: "homepod" })).toBe(false);
    expect(canSend({ ...tv, needsPairing: true })).toBe(false);
  });

  it("describes what's playing", () => {
    expect(sendText({ state: "starting", title: "a.mp4" })).toBe("Starting a.mp4…");
    expect(sendText({ state: "playing", title: "a.mp4" })).toBe("Playing a.mp4");
    expect(sendText({ state: "ended", title: "a.mp4" })).toBe("Finished a.mp4");
    expect(sendText({ state: "failed", title: null })).toBe("The TV couldn't play ");
  });

  it("only takes web links", () => {
    expect(isLink(" https://media.example/clip.mp4 ")).toBe(true);
    expect(isLink("http://192.0.2.5/stream.m3u8")).toBe(true);
    expect(isLink("C:/Videos/clip.mp4")).toBe(false);
    expect(isLink("file:///C:/clip.mp4")).toBe(false);
    expect(isLink("not a link")).toBe(false);
  });
});

describe("the PC's default output", () => {
  it("is on but not something Tandem sends to", () => {
    const direct = output({ id: "demo-pc-speakers", kind: "pc", state: "direct" });
    expect(outputDirect(direct)).toBe(true);
    expect(outputLive(direct)).toBe(false);
  });

  it("has no delay to set, nor does a device that needs pairing", () => {
    const outputs = [
      output(),
      output({ id: "demo-pc-speakers", kind: "pc", state: "direct" }),
      output({ id: "demo-tv", needsPairing: true }),
    ];
    expect(delayOutputs(outputs).map((o) => o.id)).toEqual(["demo-speaker-1"]);
  });
});
