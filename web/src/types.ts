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
  /** The app's icon on Tandem's own server, once looked up (Settings can turn this off). */
  icon: string | null;
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
  /** What was last sent to this Apple TV (a link or a video file), while it plays. */
  send: SendState | null;
}

/** A video or link sent to an Apple TV. `title` is a file name or link host: never log it. */
export interface SendState {
  state: "starting" | "playing" | "ended" | "failed";
  title: string | null;
}

export type OutputKind = "airplay" | "pc";
/** "direct": the PC's default output. Windows plays there itself, so it's always on. */
export type OutputState = "off" | "starting" | "streaming" | "waiting" | "failed" | "direct";
export type AudioSource = "system" | "player";

/** One place the sound can go: an AirPlay device or one of the PC's own sound outputs. */
export interface AudioOutput {
  id: string;
  name: string;
  kind: OutputKind;
  state: OutputState;
  /** 0 to 100; null until the user sets it (the device keeps its own volume). */
  volume: number | null;
  /** Extra delay for this output, to line it up with the others by ear. */
  delayMs: number;
  deviceKind: DeviceKind | null;
  needsPairing: boolean;
}

export interface AudioPanel {
  source: AudioSource;
  /** The PC's default output is hidden while its own sound is the source (it would echo). */
  pcOutputsHidden: boolean;
  outputs: AudioOutput[];
  /** How many outputs Tandem is sending to (not counting the PC's default output). */
  streaming: number;
  /** The window can open a file picker (it can't in the browser preview). */
  canPickFiles: boolean;
  picking: boolean;
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
  /** Look up real app icons on the App Store for the launcher. */
  appIcons: boolean;
  /** The first-run checklist has been closed. */
  onboarded: boolean;
  /** Changes whenever the user's background photo does; null when there's none. */
  photo: number | null;
}

export type CommandStatus =
  | "ready"
  | "done"
  | "help"
  | "needsInfo"
  | "notUnderstood"
  | "notAvailable"
  | "failed";

/** What a typed command did, or would do. Holds device names: show it, never log it. */
export interface CommandOutcome {
  status: CommandStatus;
  /** What it is about ("pause", "whichDevice", ...); commands.ts holds the words. */
  code: string;
  params: Record<string, string>;
  /** Whole commands to offer instead, or examples. */
  suggestions: string[];
}

/** The command bar. The text box is ours; each preview and result names the text it is for. */
export interface CommandBarState {
  text: string;
  preview: CommandOutcome | null;
  running: boolean;
  result: CommandOutcome | null;
  resultFor: string;
}

export type MusicCommand = "play_pause" | "next" | "previous";

/** What an app on this PC is playing (Phase 6). Shown on screen only; never log it. */
export interface Music {
  app: string | null;
  state: "playing" | "paused" | "stopped" | "other";
  title: string | null;
  artist: string | null;
  album: string | null;
  /** Seconds in, as of when this state was sent; null for live streams. */
  position: number | null;
  duration: number | null;
  /** What the app allows right now. */
  commands: MusicCommand[];
  canSeek: boolean;
  /** Changes whenever the artwork does; null when there is none. */
  artwork: number | null;
}

/** Tandem in the Home app. Switch names are Tandem's own ("Tandem Audio"). */
export interface HomeBridge {
  enabled: boolean;
  running: boolean;
  paired: boolean;
  /** The code to type into the Home app, until it has added Tandem. */
  setupCode: string | null;
  failed: boolean;
  switches: { id: string; name: string; on: boolean }[];
}

export interface AppState {
  devices: Device[];
  discovering: boolean;
  pairing: Pairing;
  commands: CommandBarState;
  audio: AudioPanel;
  home: HomeBridge;
  message: Problem | null;
  appearance: Appearance;
  /** Windows treats every connected network as Public, so the firewall keeps speakers out. */
  network: { untrusted: boolean };
  demo: boolean;
  reduceMotion: boolean;
  /** What the PC is playing; null when nothing is. */
  music: Music | null;
}

export type Command =
  | { type: "activate" | "connect" | "disconnect" | "pair"; id: string }
  | { type: "submitPin"; pin: string }
  | { type: "cancelPairing" | "closePairing" | "dismissMessage" | "openNetworkSettings" }
  | { type: "setAppearance"; theme?: ThemeChoice; background?: string; appIcons?: boolean; onboarded?: boolean }
  | { type: "press"; id: string; key: RemoteKey; action?: KeyAction }
  | { type: "media"; id: string; command: MediaCommand }
  | { type: "setVolume"; id: string; level: number }
  | { type: "setPower"; id: string; on: boolean }
  | { type: "loadApps"; id: string }
  | { type: "launchApp"; id: string; appId: string }
  | { type: "setText"; id: string; text: string }
  | { type: "previewCommand" | "runCommand"; text: string }
  | { type: "clearCommand" }
  | { type: "setOutput"; id: string; on: boolean }
  | { type: "setOutputVolume"; id: string; level: number }
  | { type: "setOutputDelay"; id: string; ms: number }
  | { type: "setAudioSource"; source: AudioSource }
  | { type: "allOutputsOff" }
  | { type: "setHomeBridge"; on: boolean }
  | { type: "sendMedia"; id: string; location: string }
  | { type: "pickMedia" | "stopMedia"; id: string }
  | { type: "music"; command: MusicCommand }
  | { type: "musicSeek"; position: number };
