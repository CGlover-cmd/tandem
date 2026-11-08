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
  problem: null,
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
      groups: [],
      lineup: { state: "idle", output: null, problem: null },
      streaming: 0,
      canPickFiles: false,
      picking: false,
    },
    home: { enabled: false, running: false, paired: false, setupCode: null, failed: false, switches: [] },
    message: null,
    appearance: {
      theme: "system",
      background: "sky",
      appIcons: true,
      onboarded: false,
      photo: null,
      updateCheck: true,
      restoreOutputs: false,
      photoBlur: 0,
    },
    network: { untrusted: false },
    update: null,
    reporting: false,
    commandsRequested: 0,
    music: null,
    demo: true,
    reduceMotion: false,
    library: {
      folders: [],
      scanning: false,
      scanned: 0,
      songCount: 0,
      albums: [],
      openAlbum: null,
      search: { text: "", songs: [] },
      canPickFolders: false,
      picking: false,
    },
    radio: { query: "", searching: false, results: [], saved: [], error: null },
    player: { state: "stopped", index: null, position: 0, duration: null, error: false, queue: [] },
    catalog: { query: "", searching: false, error: null, songs: [], albums: [] },
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

  it("names the Apple TV its Pair button pairs, and waits while the PIN sheet is open", () => {
    const pair = onboardingSteps(state({ devices: [speaker, tv] })).find((s) => s.id === "pair");
    expect(pair?.deviceId).toBe(tv.id);
    expect(pair?.state).toBe("todo");
    const open = state({
      devices: [speaker, tv],
      pairing: { state: "enterPin", deviceId: tv.id, deviceName: tv.name, error: null, step: 1, steps: 2 },
    });
    expect(onboardingSteps(open).find((s) => s.id === "pair")?.state).toBe("waiting");
  });
});
