// What each device card says and offers. Mirrors AppController.activate in Python.

import { strings } from "./strings";
import type { Device } from "./types";

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
      return { label: strings.action.connect, enabled: true, primary: true };
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

export function statusFor(device: Device, secondsLeft: number): { text: string; tone: Tone } {
  if (device.needsPairing) return { text: strings.status.needsPairing, tone: "warning" };
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
