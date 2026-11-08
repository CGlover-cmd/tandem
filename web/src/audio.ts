// The Audio panel's and Send sheet's small decisions, kept out of the components for Vitest.

import { strings } from "./strings";
import type { AudioOutput, Device, SendState } from "./types";

/** An output counts as on while it starts, plays or reconnects. */
export function outputLive(output: AudioOutput): boolean {
  return output.state === "starting" || output.state === "streaming" || output.state === "waiting";
}

/** The PC's default output: Windows plays there itself, so its switch stays on. */
export function outputDirect(output: AudioOutput): boolean {
  return output.state === "direct";
}

/** Outputs whose delay can be set (Advanced settings): everything Tandem sends to. */
export function delayOutputs(outputs: AudioOutput[]): AudioOutput[] {
  return outputs.filter((o) => !o.needsPairing && !outputDirect(o));
}

/** What a failed output's row says. On an untrusted network that comes first: it's the fix. */
export function problemText(output: AudioOutput, untrusted: boolean): string | null {
  if (output.state !== "failed") return null;
  if (untrusted && output.kind === "airplay") return strings.audio.problem.network!;
  return strings.audio.problem[output.problem ?? "failed"] ?? strings.audio.problem.failed!;
}

/** The "All speakers" slider: the average volume of the outputs Tandem is playing on. */
export function masterVolume(outputs: AudioOutput[]): number | null {
  const live = outputs.filter(outputLive);
  if (live.length < 2) return null;
  return Math.round(live.reduce((sum, o) => sum + outputVolume(o), 0) / live.length);
}

/** Move every playing output by the same amount, keeping their balance (each stays 0 to 100). */
export function masterChanges(outputs: AudioOutput[], level: number): { id: string; level: number }[] {
  const current = masterVolume(outputs);
  if (current === null) return [];
  const delta = level - current;
  return outputs
    .filter(outputLive)
    .map((o) => ({ id: o.id, level: Math.max(0, Math.min(100, Math.round(outputVolume(o) + delta))) }));
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
