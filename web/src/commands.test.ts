import { describe, expect, it } from "vitest";

import {
  isCommandShortcut,
  outcomeText,
  outcomeTone,
  runsWhenPicked,
  suggestionsTitle,
  visibleOutcome,
} from "./commands";
import { strings } from "./strings";
import type { CommandBarState, CommandOutcome } from "./types";

// Invented names only (docs/PRIVACY.md).
const outcome = (o: Partial<CommandOutcome>): CommandOutcome => ({
  status: "ready",
  code: "pause",
  params: { device: "Patio Speaker" },
  suggestions: [],
  ...o,
});

const bar = (o: Partial<CommandBarState>): CommandBarState => ({
  text: "",
  preview: null,
  running: false,
  result: null,
  resultFor: "",
  ...o,
});

describe("visibleOutcome", () => {
  const preview = outcome({});
  const result = outcome({ status: "done" });

  it("shows the result for the text in the box", () => {
    expect(visibleOutcome(bar({ text: "pause", preview, result, resultFor: "pause" }), "pause")).toBe(result);
  });

  it("falls back to the preview once the text changes", () => {
    const state = bar({ text: "pause p", preview, result, resultFor: "pause" });
    expect(visibleOutcome(state, "pause p")).toBe(preview);
  });

  it("hides answers for older text", () => {
    expect(visibleOutcome(bar({ text: "paus", preview }), "pause")).toBeNull();
  });
});

describe("outcomeText", () => {
  it("says what Enter will do, then what was done", () => {
    expect(outcomeText(outcome({}))).toBe("Pause Patio Speaker");
    expect(outcomeText(outcome({ status: "done" }))).toBe("Paused Patio Speaker");
    expect(
      outcomeText(outcome({ code: "volumeSet", params: { device: "Patio Speaker", level: "30" } })),
    ).toBe("Set Patio Speaker to 30%");
    expect(
      outcomeText(outcome({ status: "done", code: "openApp", params: { app: "Music", device: "Living Room TV" } })),
    ).toBe("Opened Music on Living Room TV");
  });

  it("explains problems", () => {
    expect(outcomeText(outcome({ status: "needsInfo", code: "whichDevice", params: {} }))).toBe("Which device?");
    expect(outcomeText(outcome({ status: "notAvailable", code: "notConnected" }))).toBe(
      "Patio Speaker isn't connected. Connect it first.",
    );
    expect(outcomeText(outcome({ status: "needsInfo", code: "unknownDevice", params: { name: "garden" } }))).toBe(
      "There's no device called “garden”.",
    );
    expect(outcomeText(outcome({ status: "failed", code: "noResponse", params: {} }))).toBe("No response. Try again.");
    expect(outcomeText(outcome({ status: "failed", code: "backend", params: { text: "Safe text." } }))).toBe(
      "Safe text.",
    );
  });

  it("has words for every code the engine sends", () => {
    const problems = [
      "help", "notUnderstood", "tooLong", "badVolume", "unknownDevice", "ambiguousDevice",
      "whichDevice", "noDevice", "notConnected", "cantDoThat", "noVolumeLevel", "noVolume",
      "unknownApp", "audioNotYet", "switchesNotYet", "unknownSwitch", "noResponse", "noCommands",
    ];
    for (const code of problems) {
      expect(outcomeText(outcome({ status: "notAvailable", code }))).not.toBe(strings.commands.somethingWrong);
    }
    const actions = [
      "play", "pause", "next", "previous", "volumeSet", "volumeUp", "volumeDown", "openApp",
      "powerOn", "powerOff", "switchOn", "switchOff",
    ];
    for (const code of actions) {
      expect(outcomeText(outcome({ status: "ready", code }))).not.toBe(strings.commands.somethingWrong);
      expect(outcomeText(outcome({ status: "done", code }))).not.toBe(strings.commands.somethingWrong);
    }
  });

  it("falls back for unknown codes, including object built-ins", () => {
    expect(outcomeText(outcome({ code: "nope" }))).toBe(strings.commands.somethingWrong);
    expect(outcomeText(outcome({ status: "failed", code: "toString" }))).toBe(strings.commands.somethingWrong);
  });
});

describe("tone, suggestions and picking", () => {
  it("colours outcomes", () => {
    expect(outcomeTone(outcome({ status: "done" }))).toBe("success");
    expect(outcomeTone(outcome({ status: "failed" }))).toBe("danger");
    expect(outcomeTone(outcome({ status: "help" }))).toBe("neutral");
    expect(outcomeTone(outcome({ status: "needsInfo" }))).toBe("neutral");
    expect(outcomeTone(outcome({ status: "notAvailable" }))).toBe("warning");
  });

  it("titles suggestions by what they are", () => {
    expect(suggestionsTitle(outcome({}))).toBeNull();
    const s = ["pause"];
    expect(suggestionsTitle(outcome({ status: "help", suggestions: s }))).toBe(strings.commands.examples);
    expect(suggestionsTitle(outcome({ status: "needsInfo", suggestions: s }))).toBe(strings.commands.didYouMean);
    expect(suggestionsTitle(outcome({ status: "notUnderstood", suggestions: s }))).toBe(strings.commands.tryThese);
  });

  it("runs answers but only fills in examples", () => {
    expect(runsWhenPicked(outcome({ status: "needsInfo" }))).toBe(true);
    expect(runsWhenPicked(outcome({ status: "help" }))).toBe(false);
  });
});

describe("isCommandShortcut", () => {
  const key = (k: string, mods: Partial<KeyboardEvent> = {}) => ({
    key: k,
    ctrlKey: false,
    metaKey: false,
    altKey: false,
    shiftKey: false,
    ...mods,
  });

  it("is Ctrl+K or Cmd+K only", () => {
    expect(isCommandShortcut(key("k", { ctrlKey: true }))).toBe(true);
    expect(isCommandShortcut(key("K", { metaKey: true }))).toBe(true);
    expect(isCommandShortcut(key("k"))).toBe(false);
    expect(isCommandShortcut(key("k", { ctrlKey: true, shiftKey: true }))).toBe(false);
    expect(isCommandShortcut(key("j", { ctrlKey: true }))).toBe(false);
  });
});
