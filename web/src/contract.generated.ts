// Written by tools/write_contract.py from the Python side; don't edit by hand.
// `tsc` checks it against types.ts, so the two sides can't drift apart silently.
import type { AppState, Command } from "./types";

/** The demo's whole UI state, as AppController.snapshot() sends it. */
export const demoSnapshot: AppState = {
  "devices": [
    {
      "id": "demo-soundbar",
      "name": "Den Soundbar",
      "kind": "receiver",
      "state": "disconnected",
      "needsPairing": false,
      "retryIn": null,
      "controls": null,
      "apps": null,
      "send": null,
      "audio": "off"
    },
    {
      "id": "demo-tv",
      "name": "Living Room TV",
      "kind": "apple_tv",
      "state": "connected",
      "needsPairing": false,
      "retryIn": null,
      "controls": {
        "remote": true,
        "media": [
          "next",
          "play_pause",
          "previous",
          "skip_backward",
          "skip_forward"
        ],
        "volume": "steps",
        "volumeLevel": null,
        "power": "on",
        "canPower": true,
        "apps": true,
        "textEntry": true,
        "keyboard": false,
        "nowPlaying": {
          "state": "playing",
          "title": "A Walk in the Woods",
          "artist": null,
          "album": null,
          "series": "Nature Hour",
          "app": "TV",
          "position": 754.0,
          "totalTime": 2640.0
        }
      },
      "apps": {
        "state": "ready",
        "items": [
          {
            "id": "com.example.arcade",
            "name": "Arcade Classics",
            "icon": null
          },
          {
            "id": "com.example.fitness",
            "name": "Fitness",
            "icon": null
          },
          {
            "id": "com.example.music",
            "name": "Music",
            "icon": null
          },
          {
            "id": "com.example.nature",
            "name": "Nature Hour",
            "icon": null
          },
          {
            "id": "com.example.photos",
            "name": "Photos",
            "icon": null
          },
          {
            "id": "com.example.podcasts",
            "name": "Podcasts",
            "icon": null
          },
          {
            "id": "com.apple.TVSearch",
            "name": "Search",
            "icon": null
          },
          {
            "id": "com.apple.TVSettings",
            "name": "Settings",
            "icon": null
          },
          {
            "id": "com.example.tv",
            "name": "TV",
            "icon": null
          },
          {
            "id": "com.example.weather",
            "name": "Weather Now",
            "icon": null
          }
        ],
        "error": null
      },
      "send": null,
      "audio": "off"
    },
    {
      "id": "demo-speaker-2",
      "name": "Office Speaker",
      "kind": "homepod",
      "state": "disconnected",
      "needsPairing": false,
      "retryIn": null,
      "controls": null,
      "apps": null,
      "send": null,
      "audio": "off"
    },
    {
      "id": "demo-speaker-1",
      "name": "Patio Speaker",
      "kind": "homepod",
      "state": "connected",
      "needsPairing": false,
      "retryIn": null,
      "controls": {
        "remote": false,
        "media": [
          "next",
          "play_pause",
          "previous"
        ],
        "volume": "level",
        "volumeLevel": 40.0,
        "power": "on",
        "canPower": false,
        "apps": false,
        "textEntry": false,
        "keyboard": false,
        "nowPlaying": {
          "state": "paused",
          "title": "Morning Light",
          "artist": "The Example Band",
          "album": "Daybreak",
          "series": null,
          "app": "Music",
          "position": 61.0,
          "totalTime": 214.0
        }
      },
      "apps": null,
      "send": null,
      "audio": "on"
    }
  ],
  "audio": {
    "source": "system",
    "pcOutputsHidden": true,
    "outputs": [
      {
        "id": "demo-soundbar",
        "name": "Den Soundbar",
        "kind": "airplay",
        "state": "off",
        "volume": null,
        "delayMs": 0,
        "deviceKind": "receiver",
        "needsPairing": false,
        "problem": null
      },
      {
        "id": "demo-tv",
        "name": "Living Room TV",
        "kind": "airplay",
        "state": "off",
        "volume": null,
        "delayMs": 0,
        "deviceKind": "apple_tv",
        "needsPairing": false,
        "problem": null
      },
      {
        "id": "demo-speaker-2",
        "name": "Office Speaker",
        "kind": "airplay",
        "state": "off",
        "volume": null,
        "delayMs": 0,
        "deviceKind": "homepod",
        "needsPairing": false,
        "problem": null
      },
      {
        "id": "demo-speaker-1",
        "name": "Patio Speaker",
        "kind": "airplay",
        "state": "streaming",
        "volume": null,
        "delayMs": 0,
        "deviceKind": "homepod",
        "needsPairing": false,
        "problem": null
      },
      {
        "id": "local:demo-speakers",
        "name": "Speakers",
        "kind": "pc",
        "state": "muted",
        "volume": null,
        "delayMs": 0,
        "deviceKind": null,
        "needsPairing": false,
        "problem": null
      },
      {
        "id": "local:demo-headphones",
        "name": "Headphones",
        "kind": "pc",
        "state": "off",
        "volume": null,
        "delayMs": 0,
        "deviceKind": null,
        "needsPairing": false,
        "problem": null
      }
    ],
    "lineup": {
      "state": "idle",
      "output": null,
      "problem": null
    },
    "groups": [
      {
        "id": "group:example",
        "name": "Out Back",
        "outputs": [
          "demo-speaker-1",
          "demo-soundbar"
        ],
        "state": "partly"
      }
    ],
    "streaming": 1,
    "canPickFiles": false,
    "picking": false
  },
  "library": {
    "folders": [
      "Demo Library"
    ],
    "scanning": false,
    "scanned": 11,
    "songCount": 11,
    "albums": [
      {
        "id": "abdc6ec10153f7e7",
        "title": "City Hours",
        "artist": "Imaginary Orchestra",
        "year": 2019,
        "trackCount": 3,
        "hasArt": true
      },
      {
        "id": "a4785da517681af1",
        "title": "Quiet Rooms",
        "artist": "Placeholder Trio",
        "year": 2023,
        "trackCount": 4,
        "hasArt": true
      },
      {
        "id": "a431c154aac165c0",
        "title": "Daybreak",
        "artist": "The Example Band",
        "year": 2021,
        "trackCount": 4,
        "hasArt": true
      }
    ],
    "openAlbum": null,
    "search": {
      "text": "",
      "songs": []
    },
    "canPickFolders": false,
    "picking": false
  },
  "radio": {
    "query": "",
    "searching": false,
    "results": [],
    "saved": [],
    "error": null
  },
  "catalog": {
    "query": "",
    "searching": false,
    "error": null,
    "songs": [],
    "albums": []
  },
  "player": {
    "state": "stopped",
    "index": null,
    "position": 0.0,
    "duration": null,
    "error": false,
    "queue": []
  },
  "spotify": {
    "state": "not_set_up",
    "loading": false,
    "redirectUri": "http://127.0.0.1/callback",
    "error": null,
    "playlists": [],
    "devices": [],
    "target": null,
    "query": "",
    "searching": false,
    "results": []
  },
  "home": {
    "enabled": false,
    "running": false,
    "paired": false,
    "setupCode": null,
    "failed": false,
    "switches": [
      {
        "id": "audio",
        "name": "Tandem Audio",
        "on": false
      },
      {
        "id": "music",
        "name": "Tandem Music",
        "on": false
      },
      {
        "id": "tv",
        "name": "Tandem TV",
        "on": false
      }
    ]
  },
  "discovering": false,
  "pairing": {
    "state": "done",
    "deviceId": "demo-tv",
    "deviceName": "Living Room TV",
    "error": null,
    "step": 2,
    "steps": 2
  },
  "commands": {
    "text": "",
    "preview": null,
    "running": false,
    "result": null,
    "resultFor": ""
  },
  "message": {
    "code": "notConnected"
  },
  "appearance": {
    "theme": "system",
    "background": "sky",
    "appIcons": true,
    "onboarded": false,
    "updateCheck": true,
    "restoreOutputs": false,
    "mutePc": true,
    "photoBlur": 0,
    "photo": null
  },
  "network": {
    "untrusted": false
  },
  "update": null,
  "reporting": false,
  "commandsRequested": 0,
  "demo": true,
  "reduceMotion": false,
  "music": {
    "app": "Demo Player",
    "state": "playing",
    "title": "Morning Light",
    "artist": "The Example Band",
    "album": "Daybreak",
    "position": 42.0,
    "duration": 214.0,
    "commands": [
      "next",
      "play_pause",
      "previous"
    ],
    "canSeek": true,
    "artwork": 1
  }
};

/** Every command AppController.handle accepts. */
export const commandTypes = [
  "activate",
  "addMusicFolder",
  "allOutputsOff",
  "cancelPairing",
  "clearCommand",
  "clearQueue",
  "closeAlbum",
  "closePairing",
  "connect",
  "deleteGroup",
  "deviceAudio",
  "disconnect",
  "dismissMessage",
  "launchApp",
  "lineUp",
  "loadApps",
  "media",
  "music",
  "musicSeek",
  "openAlbum",
  "openDevice",
  "openInAppleMusic",
  "openInSpotify",
  "openNetworkSettings",
  "openSpotifyDashboard",
  "openUpdate",
  "pair",
  "pickMedia",
  "playAlbum",
  "playQueueItem",
  "playSong",
  "playStation",
  "player",
  "press",
  "previewCommand",
  "queueAlbum",
  "queueSong",
  "removeMusicFolder",
  "removeQueueItem",
  "removeStation",
  "reportProblem",
  "rescanLibrary",
  "runCommand",
  "saveGroup",
  "saveStation",
  "searchCatalog",
  "searchLibrary",
  "searchRadio",
  "sendMedia",
  "setAppearance",
  "setAudioSource",
  "setGroup",
  "setHomeBridge",
  "setOutput",
  "setOutputDelay",
  "setOutputVolume",
  "setPower",
  "setSpotifyClientId",
  "setText",
  "setVolume",
  "spotifyCancelSignIn",
  "spotifyChooseDevice",
  "spotifyDismissError",
  "spotifyPlay",
  "spotifyRefresh",
  "spotifySearch",
  "spotifySignIn",
  "spotifySignOut",
  "spotifyTransfer",
  "stopMedia",
  "submitPin",
] as const satisfies readonly Command["type"][];

/** Fails to compile if types.ts has a command Python doesn't handle. */
type Unhandled = Exclude<Command["type"], (typeof commandTypes)[number]>;
export const everyCommandIsHandled: [Unhandled] extends [never] ? true : never = true;

/** Every problem code Python sends; strings.ts must have words for each. */
export const problemCodes = [
  "appCant",
  "appDidntRespond",
  "appleMusicDidntOpen",
  "badGroup",
  "cantDoThat",
  "connectFirst",
  "couldNotPair",
  "fileGone",
  "folderNotAdded",
  "groupGone",
  "groupNonePlayed",
  "homeFailed",
  "homeUnavailable",
  "noAudio",
  "noLocation",
  "noPairingNeeded",
  "noResponse",
  "noSend",
  "noTextField",
  "notATv",
  "notAvailable",
  "notConnected",
  "notInLibrary",
  "nothingPlaying",
  "pairFirst",
  "pairingFailed",
  "pinExpired",
  "pinFormat",
  "speakerGone",
  "stationGone",
  "taskFailed",
  "wrongPin",
] as const;
