import { describe, expect, it } from "vitest";
import { parseMessage, retryDelay, socketUrl } from "./bridge";
import { actionFor, cardButtons, statusFor } from "./devices";
import { problemText } from "./strings";
const speaker = {
    id: "demo-speaker-1",
    name: "Patio Speaker",
    kind: "homepod",
    state: "disconnected",
    needsPairing: false,
    retryIn: null,
    apps: null,
    send: null,
    audio: "off",
    controls: null,
};
describe("device cards", () => {
    it("offer pairing first", () => {
        const tv = { ...speaker, kind: "apple_tv", needsPairing: true };
        expect(actionFor(tv)).toEqual({ label: "Pair", enabled: true, primary: true });
        expect(statusFor(tv, 0).tone).toBe("warning");
    });
    it.each([
        ["disconnected", "Connect", true, "Ready"],
        ["failed", "Try again", true, "Couldn't connect"],
        ["connected", "Disconnect", true, "Connected"],
        ["waiting", "Cancel", true, "Trying again in 3 s"],
        ["connecting", "Connecting", false, "Connecting…"],
    ])("in state %s offer %s", (state, label, enabled, status) => {
        const device = { ...speaker, state };
        expect(actionFor(device).label).toBe(label);
        expect(actionFor(device).enabled).toBe(enabled);
        expect(statusFor(device, 3).text).toBe(status);
    });
    it("fill only the action that unblocks: pairing or a retry, not every Connect", () => {
        expect(actionFor({ ...speaker, state: "disconnected" }).primary).toBe(false);
        expect(actionFor({ ...speaker, state: "failed" }).primary).toBe(true);
    });
    it("say when a retry is due now", () => {
        expect(statusFor({ ...speaker, state: "waiting" }, 0).text).toBe("Trying again…");
    });
});
describe("card buttons", () => {
    const tv = { ...speaker, id: "demo-tv", kind: "apple_tv", audio: "off" };
    it("give a TV Audio, Video and Remote, and a speaker Audio and Remote", () => {
        expect(cardButtons(tv)).toMatchObject({ video: true, remote: true, fallback: null, quiet: null });
        expect(cardButtons(tv).audio).toEqual({ state: "off", on: false, enabled: true });
        expect(cardButtons(speaker)).toMatchObject({ video: false, remote: true, fallback: null });
    });
    it("keep Audio and Video on an unpaired TV, which pair first, but no Remote yet", () => {
        const unpaired = { ...tv, needsPairing: true };
        expect(cardButtons(unpaired)).toMatchObject({ video: true, remote: false, fallback: null });
        expect(cardButtons(unpaired).audio?.enabled).toBe(true);
    });
    it("show Audio as on while it starts or plays, and hold it while it starts", () => {
        expect(cardButtons({ ...speaker, audio: "starting" }).audio).toEqual({ state: "starting", on: true, enabled: false });
        expect(cardButtons({ ...speaker, audio: "on" }).audio).toEqual({ state: "on", on: true, enabled: true });
        expect(cardButtons({ ...speaker, audio: "failed" }).audio?.on).toBe(false);
        expect(cardButtons({ ...speaker, state: "connecting" }).audio?.enabled).toBe(false);
    });
    it("offer Disconnect once connected, and Cancel while a retry waits", () => {
        expect(cardButtons({ ...speaker, state: "connected" }).quiet?.label).toBe("Disconnect");
        expect(cardButtons({ ...speaker, state: "waiting" }).quiet?.label).toBe("Cancel");
    });
    it("fall back to Pair or Connect for a device that can't play audio or video", () => {
        const plain = { ...speaker, kind: "other", audio: null };
        expect(cardButtons(plain)).toMatchObject({ audio: null, video: false, remote: false });
        expect(cardButtons(plain).fallback?.label).toBe("Connect");
        expect(cardButtons({ ...plain, state: "connected" })).toMatchObject({ fallback: null, remote: true });
        expect(cardButtons({ ...plain, state: "waiting" })).toMatchObject({ quiet: null });
    });
    it("say what the sound is doing", () => {
        expect(statusFor({ ...speaker, state: "connected", audio: "on" }, 0).text).toBe("Playing this PC's audio");
        expect(statusFor({ ...speaker, audio: "starting" }, 0).text).toBe("Starting audio…");
        expect(statusFor({ ...speaker, audio: "failed" }, 0).tone).toBe("danger");
        expect(statusFor({ ...speaker, state: "waiting", audio: "on" }, 0).text).toBe("Trying again…");
    });
});
describe("bridge", () => {
    it("builds the socket address from the page address", () => {
        expect(socketUrl({ protocol: "http:", host: "127.0.0.1:8765", search: "?token=a+b/c" })).toBe("ws://127.0.0.1:8765/ws?token=a%20b%2Fc");
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
        expect(problemText({ code: "pairingFailed" })).toMatch(/Pairing didn't work/);
        expect(problemText({ code: "pinExpired" })).toMatch(/expired/);
        expect(problemText({ code: "noSuchCode" })).toMatch(/went wrong/);
        expect(problemText({ code: "taskFailed" })).toMatch(/went wrong/);
    });
});
