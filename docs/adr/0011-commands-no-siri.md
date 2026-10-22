# ADR-0011: No Siri integration; a command bar plus a Home bridge

- Status: Accepted (maintainer, 2026-10-21)
- Date: 2026-10-21

## Context
The maintainer asked whether Tandem could talk to Siri: ask a HomePod or Apple TV to do
something from the PC, typed or spoken. A feasibility review looked at every route:

| Route | What it would need | Verdict |
|---|---|---|
| Siri on the Apple TV through pyatv | The iPhone remote's voice channel. pyatv doesn't implement it; we'd reverse-engineer it | No: private, fragile, answers show only on the TV |
| Typed Siri to a HomePod | "Type to Siri" exists only on iPhone, iPad and Mac | No network entry point |
| Stream a spoken "Hey Siri" over AirPlay | HomePods filter out their own playback | Expected not to trigger |
| Play "Hey Siri" out loud from the PC | Text-to-speech in the room | A gimmick: loud, unreliable, wakes every HomePod nearby |
| Apple Shortcuts or HomeKit APIs | Apps on Apple platforms only | Not reachable from Windows |
| Siri controlling Tandem | Tandem appears in the Home app as an accessory bridge (HomeKit Accessory Protocol, published by Apple) | Yes |

So there is no supported way for Windows to send a request to Siri. The only way in is to
reverse-engineer a private Apple protocol, which we declined for FairPlay in
[ADR-0006](0006-screen-mirroring-fairplay.md) for the same reasons: legal risk in a public
project, and code that breaks with each tvOS update.

## Decision
- **No Siri integration.** Tandem will not reverse-engineer, imitate or bypass Siri or any
  private Apple voice protocol.
- **Commands instead.** Tandem gets its own command bar (Phase 9a): a fixed set of verbs
  ("play", "pause", "next", "previous", "volume 30 on the loft", "send audio to ...",
  "stop streaming", "open Music on the TV", "turn on/off ...") parsed on the PC, with device
  names matched loosely (case, partial words, small typos). No network, no machine learning.
  The parser (`engine/commands.py`) and dispatcher (`engine/command_dispatch.py`) are engine
  code; the window reaches them only through the UI's backend contract (ADR-0008).
- **Siri reaches Tandem through the Home app** (Phase 9b): Tandem runs a HomeKit bridge with a
  few switches. "Hey Siri, turn on Tandem music" on a HomePod flips one; Home automations on
  those switches let Tandem drive Home scenes and devices that stay in Apple Home.
- **Voice later, on the PC** (Phase 9c): the same command bar with a push-to-talk microphone,
  using Windows' on-device recognizer with a fixed phrase list. Never the browser speech API in
  the WebView2 window, which sends audio to an online service. The microphone is off until the
  user turns it on.
- **Naming:** the feature is "Commands" (and "Voice commands" once 9c lands), never "Siri".
  Docs may say "works with the Home app".
- **Privacy:** typed commands and their results contain device and app names, so they are
  shown in the window and never logged (docs/PRIVACY.md).

## Consequences
- Users can't talk to Siri through Tandem. They can type (later, say) a command in Tandem, and
  they can talk to Siri on a HomePod and have Tandem respond through its Home switches.
- The command bar is useful without voice: a keyboard launcher (Ctrl+K) for every device.
- Commands only reach what the engine offers. Until audio streaming lands (Phase 4), "send
  audio" and "stop streaming" answer "not available yet"; until the Home bridge lands,
  "turn on" works only on devices with power control.
- The Home app shows Tandem as an uncertified accessory. That's normal for open-source bridges
  and can't be removed without Apple certification.
