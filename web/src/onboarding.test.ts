import { describe, expect, it } from "vitest";

import { allDone, onboardingSteps } from "./onboarding";
import type { AppState, AudioOutput, Device } from "./types";

const speaker: Device = {
  id: "demo-speaker-1",
  name: "Patio Speaker",
  kind: "homepod",
  state: "disconnected",
  needsPairing: false,
  retryIn: null,
  apps: null,
  controls: null,
  send: null,
};
const tv: Device = { ...speaker, id: "demo-tv", name: "Living Room TV", kind: "apple_tv", needsPairing: true };
const output: AudioOutput = {
  id: speaker.id,
  name: speaker.name,
  kind: "airplay",
  state: "off",
  volume: null,
  delayMs: 0,
  deviceKind: "homepod",
  needsPairing: false,
};

function state(over: Partial<AppState> = {}): AppState {
  return {
    devices: [],
    discovering: false,
    pairing: { state: "closed", deviceId: "", deviceName: "", error: null, step: 1, steps: 1 },
    commands: { text: "", preview: null, running: false, result: null, resultFor: "" },
    audio: {
      source: "system",
      pcOutputsHidden: true,
      outputs: [],
      streaming: 0,
      canPickFiles: false,
      picking: false,
    },
    message: null,
    appearance: { theme: "system", background: "mist", appIcons: true, onboarded: false },
    demo: true,
    reduceMotion: false,
    ...over,
  };
}

describe("getting started", () => {
  it("waits while searching, with no TV step until a TV is found", () => {
    const steps = onboardingSteps(state({ discovering: true }));
    expect(steps.map((s) => [s.id, s.state])).toEqual([
      ["find", "waiting"],
      ["play", "todo"],
    ]);
    expect(onboardingSteps(state())[0]?.state).toBe("todo");
  });

  it("ticks steps off as they happen", () => {
    const before = onboardingSteps(state({ devices: [speaker, tv] }));
    expect(before.map((s) => s.state)).toEqual(["done", "todo", "todo"]);
    expect(allDone(before)).toBe(false);
    const after = onboardingSteps(
      state({
        devices: [speaker, { ...tv, needsPairing: false }],
        audio: { ...state().audio, outputs: [{ ...output, state: "streaming" }], streaming: 1 },
      }),
    );
    expect(after.map((s) => s.state)).toEqual(["done", "done", "done"]);
    expect(allDone(after)).toBe(true);
    expect(after[0]?.detail).toBe("Tandem found 2 devices.");
  });
});
