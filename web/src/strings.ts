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

  tabs: {
    label: "Sections",
    devices: "Devices",
    music: "Music",
  },

  music: {
    title: "Music",
    subtitle: "What's playing on this PC, from any app",
    nothingTitle: "Nothing is playing on this PC",
    nothingBody:
      "Play something in Spotify, Apple Music, a browser or any other app, and it shows up here. Tandem controls the app; the app plays the music.",
    untitled: "Playing now",
    from: (app: string) => `Playing in ${app}`,
    anApp: "an app on this PC",
    play: "Play",
    pause: "Pause",
    next: "Next",
    previous: "Previous",
    position: "Position",
    of: (at: string, length: string) => `${at} of ${length}`,
    live: "Live",
    openMusic: "Open Music",
    bar: (title: string) => `Now playing: ${title}. Open Music`,
    note: "Tandem is a remote for the app that's playing. To hear it on your speakers, send the PC's audio to them.",
  },
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

  audio: {
    open: "Audio",
    title: "Audio",
    subtitle:
      "Turn on a speaker and everything your PC plays goes there right away: Spotify, Apple Music, a browser, games. Turn on as many as you like.",
    source: "Sound from",
    sourceSystem: "This PC",
    sourcePlayer: "Tandem's player",
    sourceSystemDetail: "Everything the PC plays: Spotify, Apple Music, a browser, games.",
    sourcePlayerDetail: "Only what you queue in Tandem's player (music files and radio).",
    airplay: "Speakers and TVs",
    pc: "This PC",
    noOutputs: "No speakers found yet. Make sure they're on and on the same network.",
    noPcOutputs: "No other sound outputs on this PC.",
    echoNote:
      "Windows keeps playing on its default output. To hear only your speakers, or to line the PC up with them, set a virtual audio cable as Windows' default output, then turn your real speakers on here.",
    volume: "Volume",
    volumeOf: (name: string) => `Volume for ${name}`,
    delay: "Delay",
    delayOf: (name: string) => `Delay for ${name}`,
    delayHint: "Speakers out of step? Line them up in Settings, Advanced.",
    seconds: (ms: number) => `${(ms / 1000).toFixed(1)} s`,
    state: {
      off: "Off",
      starting: "Starting…",
      streaming: "Playing",
      waiting: "Reconnecting…",
      failed: "Couldn't play here. Turn it on to try again.",
      direct: "Playing from Windows",
    } as Record<string, string>,
    directNote: "Windows plays here itself, so it's always on.",
    pairFirst: "Pair first",
    turnOn: (name: string) => `Play on ${name}`,
    allOff: "Turn all off",
    done: "Done",
    badge: (count: number) => (count === 1 ? "1 playing" : `${count} playing`),
  },

  home: {
    title: "Home app",
    toggle: "Show Tandem in the Home app",
    detail:
      "Adds three switches to the Home app: Tandem Audio (your last speakers on or off), Tandem Music (play or pause) and Tandem TV (power). Siri on a HomePod and Home automations can then flip them. Choosing speakers, volume and the remote stay in Tandem.",
    addSteps: "In the Home app, choose Add Accessory, then More Options, pick Tandem and type this code:",
    added: "Tandem is in your Home app.",
    starting: "Starting…",
    failed: "Tandem couldn't start its Home bridge. Check that Windows Firewall allows Tandem.",
    switchOn: (name: string) => `${name}: on`,
    switchOff: (name: string) => `${name}: off`,
  },

  onboarding: {
    title: "Getting started",
    subtitle: "Three quick steps. This list ticks itself off as you go.",
    findTitle: "Find your devices",
    findDetail:
      "Make sure your speakers and TV are on and on the same Wi-Fi as this PC.",
    findDone: (count: number) => (count === 1 ? "Tandem found 1 device." : `Tandem found ${count} devices.`),
    pairTitle: "Pair your Apple TV",
    pairDetail: "Choose Pair and type the PIN your TV shows. It asks twice: remote control, then AirPlay.",
    pair: "Pair",
    pairDone: "Your Apple TV is paired.",
    playTitle: "Play the PC's sound on a speaker",
    playDetail: "Open Audio and turn on a speaker. Then play something on the PC.",
    playDone: "Sound is going to a speaker.",
    openAudio: "Open Audio",
    done: "done",
    helpTitle: "If something doesn't work",
    tips: [
      "A HomePod or speaker won't connect: in the Home app, open Home Settings, then Speakers & TV, and set Allow Speaker & TV Access to Everyone on this network.",
      "Speakers play out of step: in Settings, open Advanced settings and delay the faster ones until they play together.",
      "No sound on the speaker: Tandem sends what Windows plays, at Windows' volume. Check the PC isn't muted.",
    ],
    later: "Not now",
    finish: "Done",
    reopen: "Getting started",
  },

  sendSheet: {
    open: "Send",
    title: (name: string) => `Send to ${name}`,
    subtitle: "Play a video file from this PC, or a link to a video, on your TV.",
    link: "Link to a video",
    linkPlaceholder: "https://…",
    sendLink: "Play link",
    chooseFile: "Choose a video…",
    choosing: "Choosing…",
    formats: "MP4 and MOV files work best. Links must point straight at a video file or stream.",
    starting: (title: string) => `Starting ${title}…`,
    playing: (title: string) => `Playing ${title}`,
    ended: (title: string) => `Finished ${title}`,
    failed: (title: string) => `The TV couldn't play ${title}`,
    stop: "Stop",
    done: "Done",
    connectFirst: "Connect the TV first.",
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
      sendAudio: (p) => `Send the PC's audio to ${p.devices}`,
      stopStreaming: () => "Stop sending audio",
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
      sendAudio: (p) => `Sending the PC's audio to ${p.devices}`,
      stopStreaming: () => "Stopped sending audio",
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
      notStreaming: () => "Tandem isn't sending audio anywhere.",
      noSpeaker: () => "There's no speaker to send audio to. Make sure one is on.",
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
    photo: "Your photo",
    choosePhoto: "Choose a photo…",
    changePhoto: "Change photo…",
    photoFailed: "Tandem couldn't use that picture. Try a JPEG or PNG photo.",
    advanced: "Advanced settings",
    advancedTitle: "Advanced",
    advancedSubtitle: "Settings most people never need.",
    delays: "Speaker delay",
    delaysDetail:
      "Speakers play a moment behind the PC, some more than others. Delay the faster ones until they all play together.",
    noDelays: "No speakers to line up yet.",
    back: "Back",
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
