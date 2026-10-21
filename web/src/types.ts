// The UI state the Python app sends (tandem.ui.controller.AppController.snapshot) and the
// commands it accepts (AppController.handle). Keep the two in step.

export type DeviceKind = "apple_tv" | "homepod" | "receiver" | "other";
export type LinkState = "disconnected" | "connecting" | "connected" | "waiting" | "failed";
export type ThemeChoice = "system" | "light" | "dark";
export type PairingStep = "closed" | "starting" | "enterPin" | "checking" | "done" | "failed";

export type RemoteKey =
  | "up"
  | "down"
  | "left"
  | "right"
  | "select"
  | "menu"
  | "home"
  | "play_pause"
  | "volume_up"
  | "volume_down";
export type KeyAction = "tap" | "double_tap" | "hold";
export type MediaCommand = "play_pause" | "next" | "previous" | "skip_forward" | "skip_backward";

/** What's playing. Shown on screen only; titles are personal, so never log them. */
export interface NowPlaying {
  state: "idle" | "loading" | "paused" | "playing" | "stopped" | "seeking" | "unknown";
  title: string | null;
  artist: string | null;
  album: string | null;
  series: string | null;
  app: string | null;
  position: number | null;
  totalTime: number | null;
}

/** A connected device's controls, as they are right now. */
export interface Controls {
  remote: boolean;
  media: MediaCommand[];
  volume: "level" | "steps" | "none";
  volumeLevel: number | null;
  power: "on" | "off" | "unknown";
  canPower: boolean;
  nowPlaying: NowPlaying | null;
  /** The device can list its apps and open one. */
  apps: boolean;
  /** The device takes typed text into its focused text field. */
  textEntry: boolean;
  /** The device is showing an on-screen keyboard and waiting for text right now. */
  keyboard: boolean;
}

/** An app the device can open. Names are shown on screen only; never log them. */
export interface AppInfo {
  id: string;
  name: string;
}

/** The launcher's list for one device, once asked for with `loadApps`. */
export interface AppList {
  state: "loading" | "ready" | "failed";
  items: AppInfo[];
  error: Problem | null;
}

export interface Device {
  id: string;
  name: string;
  kind: DeviceKind;
  state: LinkState;
  needsPairing: boolean;
  retryIn: number | null;
  /** Set while the device is connected and its controls are ready. */
  controls: Controls | null;
  /** The device's apps, after the launcher asked for them; cleared on disconnect. */
  apps: AppList | null;
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
  | { type: "setAppearance"; theme?: ThemeChoice; background?: string }
  | { type: "press"; id: string; key: RemoteKey; action?: KeyAction }
  | { type: "media"; id: string; command: MediaCommand }
  | { type: "setVolume"; id: string; level: number }
  | { type: "setPower"; id: string; on: boolean }
  | { type: "loadApps"; id: string }
  | { type: "launchApp"; id: string; appId: string }
  | { type: "setText"; id: string; text: string };
