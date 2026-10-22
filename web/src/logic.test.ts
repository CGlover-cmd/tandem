import { describe, expect, it } from "vitest";

import { parseMessage, retryDelay, socketUrl } from "./bridge";
import { actionFor, statusFor } from "./devices";
import { problemText } from "./strings";
import type { Device } from "./types";

const speaker: Device = {
  id: "demo-speaker-1",
  name: "Patio Speaker",
  kind: "homepod",
  state: "disconnected",
  needsPairing: false,
  retryIn: null,
  apps: null,
  controls: null,
};

describe("device cards", () => {
  it("offer pairing first", () => {
    const tv = { ...speaker, kind: "apple_tv" as const, needsPairing: true };
    expect(actionFor(tv)).toEqual({ label: "Pair", enabled: true, primary: true });
    expect(statusFor(tv, 0).tone).toBe("warning");
  });

  it.each([
    ["disconnected", "Connect", true, "Ready"],
    ["failed", "Try again", true, "Couldn't connect"],
    ["connected", "Disconnect", true, "Connected"],
    ["waiting", "Cancel", true, "Trying again in 3 s"],
    ["connecting", "Connecting", false, "Connecting…"],
  ] as const)("in state %s offer %s", (state, label, enabled, status) => {
    const device = { ...speaker, state };
    expect(actionFor(device).label).toBe(label);
    expect(actionFor(device).enabled).toBe(enabled);
    expect(statusFor(device, 3).text).toBe(status);
  });

  it("say when a retry is due now", () => {
    expect(statusFor({ ...speaker, state: "waiting" }, 0).text).toBe("Trying again…");
  });
});

describe("bridge", () => {
  it("builds the socket address from the page address", () => {
    expect(socketUrl({ protocol: "http:", host: "127.0.0.1:8765", search: "?token=a+b/c" })).toBe(
      "ws://127.0.0.1:8765/ws?token=a%20b%2Fc",
    );
    expect(socketUrl({ protocol: "https:", host: "x", search: "" })).toBe("wss://x/ws?token=");
  });

  it("backs off when reconnecting", () => {
    expect([0, 1, 2, 3, 4, 10].map(retryDelay)).toEqual([500, 1000, 2000, 4000, 5000, 5000]);
  });

  it("only accepts state messages", () => {
    expect(parseMessage('{"type":"state","state":{"devices":[]}}')).toEqual({ devices: [] });
    expect(parseMessage('{"type":"other"}')).toBeNull();
    expect(parseMessage("not json")).toBeNull();
  });
});

describe("problems", () => {
  it("have words for every code", () => {
    expect(problemText({ code: "wrongPin" })).toMatch(/didn't match/);
    expect(problemText({ code: "pinFormat" })).toMatch(/4-digit/);
    expect(problemText({ code: "pairingFailed", text: "Busy." })).toBe("Busy.");
    expect(problemText({ code: "pairingFailed" })).toMatch(/Pairing didn't work/);
    expect(problemText({ code: "backend" })).toMatch(/went wrong/);
    expect(problemText({ code: "taskFailed" })).toMatch(/went wrong/);
  });
});
