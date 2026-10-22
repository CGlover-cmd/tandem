# Music spike 2: copy protection in Tandem's window

**Verdict: needs a token test.** The browser side is ready for full-track MusicKit JS playback:
inside a window set up like Tandem's, Widevine (software level) loads and builds a licence
request, the page is a secure context, and PlayReady is there too. This overturns the
feasibility review's assumption that WebView2 has no Widevine. What's left can only be
answered with a real Apple developer token: whether Apple's licence servers accept a WebView2
client, and whether the sign-in flow completes. Sign-in also needs one change in Tandem:
pywebview sends every new window to the system browser, which breaks MusicKit JS's popup.

Script: [spikes/spike_music_webview2_drm.py](../../spikes/spike_music_webview2_drm.py). No Apple
account or token was used, and nothing left the PC.

## Setup

- The same host as Tandem's window (ADR-0010): pywebview 6.2.1 on WebView2, the page served by
  aiohttp from `http://127.0.0.1:<random port>/?token=…`, `private_mode=True` (Tandem's
  setting). Also run with `private_mode=False` for comparison.
- WebView2 runtime **155.0.4283.62, Evergreen** (machine-wide install; pywebview's
  `WEBVIEW2_RUNTIME_PATH` is unset, so no Fixed runtime is used). The runtime's own install
  folder contains a `WidevineCdm` folder, so Widevine comes with the runtime rather than from
  something else on this PC.
- Each key system was asked for an audio-only config: `initDataTypes: ["cenc"]`,
  `audioCapabilities: [{ contentType: 'audio/mp4; codecs="mp4a.40.2"' }]`. When access was
  granted, the page called `createMediaKeys()` and then `generateRequest()` with a dummy key id,
  and waited for the CDM's licence message. Nothing was sent to a licence server.

## Findings

Page: `window.isSecureContext` is **true** (loopback counts as a secure origin), EME is present,
and `MediaSource.isTypeSupported` accepts AAC in MP4.

| Key system | Access (Tandem's window, private) | Media keys | Licence request | Not private |
|---|---|---|---|---|
| `com.widevine.alpha` | **Yes** | Yes | Yes: 2 bytes `08 04`, Widevine's request for a service certificate (its normal first step) | Same |
| `com.microsoft.playready` | Yes | Yes | No message within 8 s (our test header may be at fault) | Same |
| `com.microsoft.playready.recommendation` | Yes | First call timed out after 8 s; later calls in the same page worked | Not reached | Same |
| `com.microsoft.playready.recommendation.3000` | No | | | **Yes**, and a 24 KB licence request |
| `com.microsoft.playready.hardware` | No | | | **Yes**, and a 24 KB licence request |
| `org.w3.clearkey` | Yes | Yes | Yes (54 bytes) | Same |

Robustness levels (audio):

| Key system | Granted | Refused |
|---|---|---|
| Widevine | `SW_SECURE_CRYPTO` (software, often called L3) | `SW_SECURE_DECODE`, `HW_SECURE_CRYPTO`, `HW_SECURE_DECODE`, `HW_SECURE_ALL` |
| PlayReady recommendation | `150`, `2000` | `3000` in private mode (granted when not private) |

Hardware PlayReady (SL3000) works only when the window keeps its data on disk; Tandem's
private mode turns it off. Widevine doesn't care either way.

**Popups (MusicKit JS signs in through one):**

| Window setup | `window.open` | Talks back to the page |
|---|---|---|
| pywebview as Tandem uses it | Returns `null`. pywebview catches the request and opens the URL in the system browser instead | No |
| New-window requests left to WebView2 | Opens a WebView2 popup window | Yes: `window.opener.postMessage` reached the page |

The popup test used a page on the same origin. Apple's sign-in page is on another origin; it
should behave the same (the opener link is kept), but the token test will confirm it.

## What this means for Phase 6

- **Full-track Apple Music in the window is possible in principle.** MusicKit JS on Chromium
  browsers is reported to use Widevine, and the software level is what desktop Chrome and Edge
  normally have too. The open risk is server-side: Widevine licence servers can refuse clients
  they don't trust (for example, ones not signed for Widevine's verified media path), and we
  can't see that without a token.
- **Tandem's host needs a change for sign-in:** handle WebView2's new-window request in
  `tandem.ui.app` so that Apple's sign-in page opens in a WebView2 popup (only for Apple's
  sign-in origin), instead of pywebview's default of the system browser.
- **Private mode stays.** Widevine works in it, and Tandem keeps the Apple Music user token in
  its own vault (ADR-0012), so the web view doesn't need to remember it.
- Results are for this PC and this runtime. The Phase 9 installer's WebView2 bootstrapper
  installs the same Evergreen runtime, so other PCs should match; recheck on Windows 10 22H2.

## Token test (next)

Needs the maintainer's Apple Developer Program membership and a MusicKit key (private key kept
in `local/`, never committed). Steps: generate a short-lived developer token outside the repo;
load MusicKit JS in the same window setup with new-window requests left to WebView2; sign in;
play one full catalog track; record whether it plays past the 30-second preview and whether
the licence request succeeds. The result goes into an ADR as the Phase 6 Apple Music go or
no-go.
