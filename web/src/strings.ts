// Every word the window shows, in one place so it can be translated later.

import type { DeviceKind, Problem } from "./types";

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

  launcher: {
    open: "Apps",
    title: "Apps",
    back: "Back to the remote",
    search: "Search apps",
    loading: "Getting the list of apps…",
    empty: "No apps to show.",
    noMatch: (query: string) => `No apps match “${query}”.`,
    failed: "Couldn't get the list of apps.",
    retry: "Try again",
    refresh: "Refresh",
    openApp: (name: string) => `Open ${name}`,
  },

  typing: {
    open: "Keyboard",
    close: "Hide keyboard",
    label: "Text for your TV",
    asking: "Your TV is asking for text.",
    hint: "What you type appears in the text field on your TV.",
    selectFirst: "Select a search box or text field on your TV first, then type here.",
    placeholder: "Type here",
    clear: "Clear",
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
    appIcons: "App icons",
    appIconsDetail: "Shows each Apple TV app's real icon, looked up on the App Store. Turn off to show letters instead.",
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
