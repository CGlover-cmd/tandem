import { describe, expect, it } from "vitest";

import {
  canSend,
  delayLabel,
  delayOutputs,
  groupOutputs,
  isLink,
  lineUpText,
  masterChanges,
  masterVolume,
  directSwitch,
  outputDirect,
  outputLive,
  outputVolume,
  problemText,
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
  problem: null,
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
  audio: null,
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

  it("can be switched only while Tandem has it muted or kept on for AirPlay", () => {
    const pc = (state: AudioOutput["state"]) => output({ id: "demo-pc-speakers", kind: "pc", state });
    expect(directSwitch(pc("direct"))).toEqual({ on: true, enabled: false });
    expect(directSwitch(pc("muted"))).toEqual({ on: false, enabled: true });
    expect(directSwitch(pc("ahead"))).toEqual({ on: true, enabled: true });
    expect(outputDirect(pc("muted"))).toBe(true);
    expect(outputLive(pc("ahead"))).toBe(false);
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

describe("the All speakers slider", () => {
  const live = (id: string, volume: number) => output({ id, state: "streaming", volume });

  it("shows only with two or more playing outputs, at their average", () => {
    expect(masterVolume([live("a", 40)])).toBeNull();
    expect(masterVolume([live("a", 40), live("b", 60), output({ id: "c", volume: 99 })])).toBe(50);
  });

  it("moves every playing output by the same amount, within 0 to 100", () => {
    expect(masterChanges([live("a", 40), live("b", 90)], 75)).toEqual([
      { id: "a", level: 50 },
      { id: "b", level: 100 },
    ]);
  });
});

describe("why a speaker couldn't play", () => {
  it("names the fix, and the untrusted network first", () => {
    const failed = output({ state: "failed", problem: "access" });
    expect(problemText(failed, false)).toContain("Allow Speaker & TV Access");
    expect(problemText(failed, true)).toContain("doesn't trust this network");
    expect(problemText(output({ state: "failed", problem: "unreachable" }), false)).toContain("No answer");
    expect(problemText(output(), false)).toBeNull();
  });
});

describe("the line-up's status", () => {
  it("names the speaker and the fix", () => {
    expect(lineUpText({ state: "idle", output: null, problem: null })).toBeNull();
    expect(lineUpText({ state: "listening", output: "Patio Speaker", problem: null })).toContain("Patio Speaker");
    expect(lineUpText({ state: "failed", output: "Patio Speaker", problem: "notHeard" })).toContain(
      "beeps from Patio Speaker",
    );
    expect(lineUpText({ state: "failed", output: null, problem: "noMic" })).toContain("Microphone");
  });
});
