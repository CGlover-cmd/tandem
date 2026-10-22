// Every word the window shows, in one place so it can be translated later.

import type { DeviceKind, Problem } from "./types";

type Params = Record<string, string>;
type Words = (p: Params) => string;

export const strings = {
  appName: "Tandem",
  devicesTitle: "Devices",
  devicesSubtitle: "Apple TV, HomePod and AirPlay 2 speakers on your network",
  demoBadge: "Demo devices",
  searching: "Looking for devices…",
  emptyTitle: "No devices yet",
  emptyBody:
    "Make sure your Apple TV or speakers are on and connected to the same network as this PC.",
  settings: "Settings",
  reconnecting: "Reconnecting to Tandem…",
  dismiss: "Dismiss",

  kind: {
    apple_tv: "Apple TV",
    homepod: "HomePod",
    receiver: "AirPlay speaker",
    other: "AirPlay device",
  } satisfies Record<DeviceKind, string>,

  status: {
    needsPairing: "Needs pairing",
    disconnected: "Ready",
    connecting: "Connecting…",
    connected: "Connected",
    waiting: (seconds: number) =>
      seconds > 0 ? `Trying again in ${seconds} s` : "Trying again…",
    failed: "Couldn't connect",
  },

  action: {
    pair: "Pair",
    connect: "Connect",
    disconnect: "Disconnect",
    cancel: "Cancel",
    retry: "Try again",
    connecting: "Connecting",
  },

  pairing: {
    title: (name: string) => `Pair ${name}`,
    starting: (name: string) => `Asking ${name} to show a PIN…`,
    enterPin: "Enter the 4-digit PIN shown on your TV.",
    nextPin: "Your TV is showing a new PIN. Enter it to finish.",
    stepOf: (step: number, steps: number) => `PIN ${step} of ${steps}`,
    pinLabel: "PIN",
    checking: "Checking the PIN…",
    done: (name: string) => `${name} is paired. Tandem will connect to it now.`,
    doneTitle: "Paired",
    failedTitle: "Pairing didn't work",
    pair: "Pair",
    cancel: "Cancel",
    close: "Done",
    tryAgain: "Try again",
  },

  remote: {
    open: "Remote",
    title: (name: string) => name,
    pad: "Remote touch pad",
    up: "Up",
    down: "Down",
    left: "Left",
    right: "Right",
    select: "Select",
    back: "Back",
    home: "Home",
    playPause: "Play or pause",
    play: "Play",
    pause: "Pause",
    next: "Next",
    previous: "Previous",
    skipForward: "Skip forward",
    skipBackward: "Skip back",
    volume: "Volume",
    volumeUp: "Volume up",
    volumeDown: "Volume down",
    volumeElsewhere: "Use your TV's remote to change the volume.",
    power: "Power",
    turnOff: "Turn off",
    turnOn: "Turn on",
    nothingPlaying: "Nothing playing",
    keyboardHint: "Arrow keys move, Enter selects, Backspace goes back. Hold for a long press.",
    done: "Done",
  },

  commands: {
    open: "Commands",
    shortcut: "Ctrl+K",
    title: "Commands",
    label: "Type a command",
    placeholder: "Try “pause” or “volume 30 on the loft”",
    hint: "Enter runs it. Esc closes.",
    running: "Working…",
    didYouMean: "Did you mean",
    tryThese: "Try one of these",
    examples: "Things you can type",
    /** What Enter will do. */
    ready: {
      play: (p) => `Play on ${p.device}`,
      pause: (p) => `Pause ${p.device}`,
      next: (p) => `Next on ${p.device}`,
      previous: (p) => `Previous on ${p.device}`,
      volumeSet: (p) => `Set ${p.device} to ${p.level}%`,
      volumeUp: (p) => `Turn ${p.device} up`,
      volumeDown: (p) => `Turn ${p.device} down`,
      openApp: (p) => `Open ${p.app} on ${p.device}`,
      powerOn: (p) => `Turn on ${p.device}`,
      powerOff: (p) => `Turn off ${p.device}`,
      switchOn: (p) => `Turn on ${p.switch}`,
      switchOff: (p) => `Turn off ${p.switch}`,
    } satisfies Record<string, Words>,
    /** What it did. */
    done: {
      play: (p) => `Playing on ${p.device}`,
      pause: (p) => `Paused ${p.device}`,
      next: (p) => `Skipped ahead on ${p.device}`,
      previous: (p) => `Went back on ${p.device}`,
      volumeSet: (p) => `${p.device} is at ${p.level}%`,
      volumeUp: (p) => `Turned ${p.device} up`,
      volumeDown: (p) => `Turned ${p.device} down`,
      openApp: (p) => `Opened ${p.app} on ${p.device}`,
      powerOn: (p) => `Turned on ${p.device}`,
      powerOff: (p) => `Turned off ${p.device}`,
      switchOn: (p) => `${p.switch} is on`,
      switchOff: (p) => `${p.switch} is off`,
    } satisfies Record<string, Words>,
    /** Why it can't be done, or what's missing. */
    problem: {
      help: () => "Type what you want Tandem to do.",
      notUnderstood: () => "Tandem didn't understand that.",
      tooLong: () => "That's too long for a command.",
      badVolume: () => "Volume goes from 0 to 100.",
      unknownDevice: (p) => `There's no device called “${p.name}”.`,
      ambiguousDevice: (p) => `“${p.name}” could be more than one device.`,
      whichDevice: () => "Which device?",
      noDevice: () => "No connected device can do that. Connect one first.",
      notConnected: (p) => `${p.device} isn't connected. Connect it first.`,
      cantDoThat: (p) => `${p.device} can't do that right now.`,
      noVolumeLevel: (p) => `${p.device} can only step its volume up or down.`,
      noVolume: (p) => `Tandem can't change the volume on ${p.device}. Use its own remote.`,
      unknownApp: (p) => `There's no app called “${p.app}” on ${p.device}.`,
      audioNotYet: () => "Sending the PC's audio isn't in Tandem yet.",
      switchesNotYet: (p) =>
        `There's no device called “${p.name}”. Home switches aren't in Tandem yet.`,
      unknownSwitch: (p) => `There's no switch or device called “${p.name}”.`,
      noResponse: (p) => (p.device ? `${p.device} didn't respond. Try again.` : "No response. Try again."),
      backend: (p) => p.text || "Something went wrong. Try again.",
      noCommands: () => "Commands aren't available here.",
    } satisfies Record<string, Words>,
    runKey: "to run",
    closeKey: "to close",
    somethingWrong: "Something went wrong. Try again.",
  },

  settingsSheet: {
    title: "Settings",
    appearance: "Appearance",
    theme: "Theme",
    themeSystem: "System",
    themeLight: "Light",
    themeDark: "Dark",
    background: "Background",
    neutral: "Neutral",
    gradients: "Gradients",
    done: "Done",
  },
};

export function problemText(problem: Problem): string {
  switch (problem.code) {
    case "pinFormat":
      return "Enter the 4-digit PIN shown on the TV.";
    case "wrongPin":
      return "That PIN didn't match. Check the TV and try again.";
    case "pairingFailed":
      return problem.text || "Pairing didn't work. Try again.";
    case "backend":
      return problem.text || "Something went wrong. Try again.";
    default:
      return "Something went wrong. Try again.";
  }
}
