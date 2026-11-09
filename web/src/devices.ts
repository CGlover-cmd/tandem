// What each device card says and offers. The Audio button mirrors
// AppController.set_device_audio in Python, Video and Remote AppController.open_device, and the
// fallback action AppController.activate.

import { strings } from "./strings";
import type { Device, DeviceAudio } from "./types";

export type Tone = "neutral" | "accent" | "success" | "warning" | "danger";

export interface CardAction {
  label: string;
  /** False while a connection attempt is running: there is nothing to press yet. */
  enabled: boolean;
  primary: boolean;
}

export function actionFor(device: Device): CardAction {
  if (device.needsPairing) return { label: strings.action.pair, enabled: true, primary: true };
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

/** The buttons on a device card. */
export interface CardButtons {
  /** Play this PC's sound on the device: a toggle. Null when the device can't play audio. */
  audio: { state: DeviceAudio; enabled: boolean; on: boolean } | null;
  /** Send a video or link: Apple TV only. */
  video: boolean;
  remote: boolean;
  /** The old Pair/Connect button, for a device with neither Audio nor Video. */
  fallback: CardAction | null;
  /** A small text button: Disconnect, or Cancel while a retry waits. */
  quiet: CardAction | null;
}

export function cardButtons(device: Device): CardButtons {
  const busy = device.state === "connecting";
  const video = device.kind === "apple_tv";
  const audio =
    device.audio === null
      ? null
      : {
          state: device.audio,
          on: device.audio === "on" || device.audio === "starting",
          enabled: !busy && device.audio !== "starting",
        };
  const connected = device.state === "connected" && !device.needsPairing;
  const plain = audio === null && !video;
  let quiet: CardAction | null = null;
  if (connected) quiet = { label: strings.action.disconnect, enabled: true, primary: false };
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

export function statusFor(device: Device, secondsLeft: number): { text: string; tone: Tone } {
  if (device.needsPairing) return { text: strings.status.needsPairing, tone: "warning" };
  if (device.state !== "waiting" && device.state !== "connecting") {
    if (device.audio === "on") return { text: strings.status.playingAudio, tone: "success" };
    if (device.audio === "starting") return { text: strings.status.startingAudio, tone: "accent" };
    if (device.audio === "failed") return { text: strings.status.audioFailed, tone: "danger" };
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
