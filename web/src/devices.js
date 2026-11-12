// What each device card says and offers. The Audio button mirrors
// AppController.set_device_audio in Python, Video and Remote AppController.open_device, and the
// fallback action AppController.activate.
import { strings } from "./strings";
export function actionFor(device) {
    if (device.needsPairing)
        return { label: strings.action.pair, enabled: true, primary: true };
    switch (device.state) {
        case "disconnected":
            return { label: strings.action.connect, enabled: true, primary: false };
        case "failed":
            return { label: strings.action.retry, enabled: true, primary: true };
        case "connected":
            return { label: strings.action.disconnect, enabled: true, primary: false };
        case "waiting":
            return { label: strings.action.cancel, enabled: true, primary: false };
        case "connecting":
            return { label: strings.action.connecting, enabled: false, primary: false };
    }
}
export function cardButtons(device) {
    const busy = device.state === "connecting";
    const video = device.kind === "apple_tv";
    const audio = device.audio === null
        ? null
        : {
            state: device.audio,
            on: device.audio === "on" || device.audio === "starting",
            enabled: !busy && device.audio !== "starting",
        };
    const connected = device.state === "connected" && !device.needsPairing;
    const plain = audio === null && !video;
    let quiet = null;
    if (connected)
        quiet = { label: strings.action.disconnect, enabled: true, primary: false };
    else if (device.state === "waiting" && !device.needsPairing)
        quiet = { label: strings.action.cancel, enabled: true, primary: false };
    return {
        audio,
        video,
        remote: !device.needsPairing && (!plain || connected),
        fallback: plain && !connected ? actionFor(device) : null,
        quiet: plain && device.state === "waiting" ? null : quiet,
    };
}
export function statusFor(device, secondsLeft) {
    if (device.needsPairing)
        return { text: strings.status.needsPairing, tone: "warning" };
    if (device.state !== "waiting" && device.state !== "connecting") {
        if (device.audio === "on")
            return { text: strings.status.playingAudio, tone: "success" };
        if (device.audio === "starting")
            return { text: strings.status.startingAudio, tone: "accent" };
        if (device.audio === "failed")
            return { text: strings.status.audioFailed, tone: "danger" };
    }
    switch (device.state) {
        case "disconnected":
            return { text: strings.status.disconnected, tone: "neutral" };
        case "connecting":
            return { text: strings.status.connecting, tone: "accent" };
        case "connected":
            return { text: strings.status.connected, tone: "success" };
        case "waiting":
            return { text: strings.status.waiting(secondsLeft), tone: "warning" };
        case "failed":
            return { text: strings.status.failed, tone: "danger" };
    }
}
