// The UI state the Python app sends (tandem.ui.controller.AppController.snapshot) and the
// commands it accepts (AppController.handle). Keep the two in step.

export type DeviceKind = "apple_tv" | "homepod" | "receiver" | "other";
export type LinkState = "disconnected" | "connecting" | "connected" | "waiting" | "failed";
export type ThemeChoice = "system" | "light" | "dark";
export type PairingStep = "closed" | "starting" | "enterPin" | "checking" | "done" | "failed";

export interface Device {
  id: string;
  name: string;
  kind: DeviceKind;
  state: LinkState;
  needsPairing: boolean;
  retryIn: number | null;
}

/** Something to tell the user. `code` picks the words; `text` is backend text, safe to show. */
export interface Problem {
  code: "pinFormat" | "wrongPin" | "pairingFailed" | "backend" | "taskFailed" | string;
  text?: string;
}

export interface Pairing {
  state: PairingStep;
  deviceId: string;
  deviceName: string;
  error: Problem | null;
  /** Which PIN this is, of how many: an Apple TV shows one for remote control, then AirPlay. */
  step: number;
  steps: number;
}

export interface Appearance {
  theme: ThemeChoice;
  background: string;
}

export interface AppState {
  devices: Device[];
  discovering: boolean;
  pairing: Pairing;
  message: Problem | null;
  appearance: Appearance;
  demo: boolean;
  reduceMotion: boolean;
}

export type Command =
  | { type: "activate" | "connect" | "disconnect" | "pair"; id: string }
  | { type: "submitPin"; pin: string }
  | { type: "cancelPairing" | "closePairing" | "dismissMessage" }
  | { type: "setAppearance"; theme?: ThemeChoice; background?: string };
