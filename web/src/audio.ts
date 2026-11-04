// The Audio panel's and Send sheet's small decisions, kept out of the components for Vitest.

import { strings } from "./strings";
import type { AudioOutput, Device, SendState } from "./types";

/** An output counts as on while it starts, plays or reconnects. */
export function outputLive(output: AudioOutput): boolean {
  return output.state === "starting" || output.state === "streaming" || output.state === "waiting";
}

/** The slider's position: the saved volume, or the middle until the user sets one. */
export function outputVolume(output: AudioOutput): number {
  return output.volume ?? 50;
}

export function delayLabel(ms: number): string {
  return strings.audio.seconds(ms);
}

export function groupOutputs(outputs: AudioOutput[]): { airplay: AudioOutput[]; pc: AudioOutput[] } {
  return {
    airplay: outputs.filter((o) => o.kind === "airplay"),
    pc: outputs.filter((o) => o.kind === "pc"),
  };
}

/** Send to TV is offered on a connected Apple TV. */
export function canSend(device: Device): boolean {
  return device.kind === "apple_tv" && device.state === "connected" && !device.needsPairing;
}

export function sendText(send: SendState): string {
  const title = send.title ?? "";
  switch (send.state) {
    case "starting":
      return strings.sendSheet.starting(title);
    case "playing":
      return strings.sendSheet.playing(title);
    case "ended":
      return strings.sendSheet.ended(title);
    default:
      return strings.sendSheet.failed(title);
  }
}

/** A link worth sending: http(s) and a host. */
export function isLink(text: string): boolean {
  try {
    const url = new URL(text.trim());
    return (url.protocol === "http:" || url.protocol === "https:") && url.hostname !== "";
  } catch {
    return false;
  }
}
