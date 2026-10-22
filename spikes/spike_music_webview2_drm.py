"""Music spike 2: which copy-protection (EME) systems work inside Tandem's window?

Throwaway spike code (Phase 6, Music). Full-track Apple Music playback through MusicKit JS
needs the page to get a DRM key system from the browser engine. This script opens a probe page
in the same kind of window Tandem uses (ADR-0010): pywebview on the WebView2 runtime, page
served by aiohttp from http://127.0.0.1:<random port>, `private_mode=True`. It reports:

- which key systems `navigator.requestMediaKeySystemAccess` grants for an audio-only config
  (`audio/mp4; codecs="mp4a.40.2"`), and whether `createMediaKeys()` then works;
- `window.isSecureContext`, and the WebView2 runtime version and kind (Evergreen or Fixed);
- whether `window.open` gives the page a popup it can talk to (MusicKit JS signs in that way).

Popup modes: `--popups pywebview` keeps pywebview's handling of new windows, except that the
URL is only recorded instead of opened in the system browser. `--popups webview2` takes
pywebview's handler out so WebView2 opens its own popup window, as Tandem could do.

No Apple token or account is used, and nothing leaves the PC.

Usage (from the repo root, with the dev virtualenv's python.exe):
    python spikes/spike_music_webview2_drm.py [--popups pywebview|webview2] [--no-private]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import secrets
import sys
import threading
import winreg
from typing import Any

from aiohttp import web

PAGE = """<!doctype html>
<meta charset="utf-8"><title>DRM probe</title>
<body style="font: 14px Segoe UI; padding: 16px">
<p id="status">Probing…</p>
<script>
const KEY_SYSTEMS = [
  "com.widevine.alpha",
  "com.microsoft.playready",
  "com.microsoft.playready.recommendation",
  "com.microsoft.playready.recommendation.3000",
  "com.microsoft.playready.hardware",
  "org.w3.clearkey",
];
const AUDIO = 'audio/mp4; codecs="mp4a.40.2"';
const CONFIGS = [{
  initDataTypes: ["cenc"],
  audioCapabilities: [{ contentType: AUDIO }],
}];
// A dummy key id: the CDM only has to build a licence request from it, nothing is sent.
const KID = new Uint8Array([1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16]);
function u32(n) { return [(n>>>24)&255, (n>>>16)&255, (n>>>8)&255, n&255]; }
function hex(s) { return s.replace(/-/g, "").match(/../g).map((h) => parseInt(h, 16)); }
function pssh(systemId, data) {
  const body = [0,0,0,0, ...hex(systemId), ...u32(data.length), ...data];
  return new Uint8Array([...u32(8 + body.length), 0x70,0x73,0x73,0x68, ...body]);
}
function widevineInit() {  // WidevinePsshData { key_id: KID }
  return pssh("edef8ba9-79d6-4ace-a3c8-27dcd51d21ed", [0x12, 16, ...KID]);
}
function playreadyInit() {  // PlayReady Object holding a v4.0 WRMHEADER
  const guid = [KID[3],KID[2],KID[1],KID[0],KID[5],KID[4],KID[7],KID[6],...KID.slice(8)];
  const kid = btoa(String.fromCharCode(...guid));
  const xml = '<WRMHEADER xmlns="http://schemas.microsoft.com/DRM/2007/03/PlayReadyHeader" ' +
    'version="4.0.0.0"><DATA><PROTECTINFO><KEYLEN>16</KEYLEN><ALGID>AESCTR</ALGID>' +
    '</PROTECTINFO><KID>' + kid + '</KID></DATA></WRMHEADER>';
  const rec = [];
  for (const ch of xml) { const c = ch.charCodeAt(0); rec.push(c & 255, c >> 8); }
  const le16 = (n) => [n & 255, (n >> 8) & 255];
  const le32 = (n) => [n & 255, (n >> 8) & 255, (n >> 16) & 255, (n >>> 24) & 255];
  const obj = [...le32(10 + rec.length), ...le16(1), ...le16(1), ...le16(rec.length), ...rec];
  return pssh("9a04f079-9840-4286-ab92-e65be0885f95", obj);
}
function initFor(ks) {
  if (ks.startsWith("com.widevine")) return ["cenc", widevineInit()];
  if (ks.startsWith("com.microsoft.playready")) return ["cenc", playreadyInit()];
  const keyids = JSON.stringify({ kids: [btoa(String.fromCharCode(...KID))
    .replace(/\\+/g, "-").replace(/\\//g, "_").replace(/=+$/, "")] });
  return ["keyids", new TextEncoder().encode(keyids)];
}
function log(step) {
  fetch("/log?token=TOKEN", { method: "POST", body: step }).catch(() => {});
}
// Some CDM calls never settle when the CDM can't load, so every one gets a deadline.
function within(promise, ms, label) {
  return Promise.race([promise, new Promise((_, reject) =>
    setTimeout(() => reject(new Error("timeout: " + label)), ms))]);
}
async function licenceRequest(ks, keys) {
  const [type, data] = initFor(ks);
  const session = keys.createSession("temporary");
  const got = new Promise((resolve) => {
    session.addEventListener("message", (ev) =>
      resolve({ message: true, messageType: ev.messageType, bytes: ev.message.byteLength,
        head: [...new Uint8Array(ev.message).slice(0, 4)].map((b) => b.toString(16).padStart(2, "0")).join(" ") }));
    setTimeout(() => resolve({ message: false }), 8000);
  });
  try { await within(session.generateRequest(type, data), 8000, "generateRequest"); }
  catch (e) { return { message: false, error: e.name + ": " + e.message }; }
  const out = await got;
  try { await within(session.close(), 3000, "close"); } catch (e) {}
  return out;
}
async function probe(ks, configs) {
  log("probe " + ks + (configs ? " " + configs[0].audioCapabilities[0].robustness : ""));
  const row = { keySystem: ks, access: false, mediaKeys: false, error: null };
  try {
    const access = await within(
      navigator.requestMediaKeySystemAccess(ks, configs || CONFIGS), 8000, "access");
    row.access = true;
    const cfg = access.getConfiguration();
    row.robustness = cfg.audioCapabilities.map((c) => c.robustness);
    row.persistentState = cfg.persistentState;
    try {
      const keys = await within(access.createMediaKeys(), 8000, "createMediaKeys");
      row.mediaKeys = true;
      if (!configs) row.licenceRequest = await licenceRequest(ks, keys);
    } catch (e) { row.error = "createMediaKeys: " + e.message; }
  } catch (e) { row.error = e.name + (e.message.startsWith("timeout") ? " (" + e.message + ")" : ""); }
  return row;
}
const ROBUSTNESS = {
  "com.widevine.alpha": ["SW_SECURE_CRYPTO", "SW_SECURE_DECODE", "HW_SECURE_CRYPTO",
                         "HW_SECURE_DECODE", "HW_SECURE_ALL"],
  "com.microsoft.playready.recommendation": ["150", "2000", "3000"],
};
function tryPopup() {
  return new Promise((resolve) => {
    let w = null;
    try { w = window.open("/popup?token=TOKEN", "probe", "width=420,height=240"); }
    catch (e) { resolve({ opened: false, error: e.name }); return; }
    if (!w) { resolve({ opened: false, handle: "null" }); return; }
    const timer = setTimeout(() => resolve({ opened: true, handle: "window", message: false }), 5000);
    window.addEventListener("message", (ev) => {
      if (ev.data === "popup-ready") {
        clearTimeout(timer);
        try { w.close(); } catch (e) {}
        resolve({ opened: true, handle: "window", message: true, origin: ev.origin === location.origin });
      }
    });
  });
}
(async () => {
  const out = {
    isSecureContext: window.isSecureContext,
    origin: location.origin,
    hasEME: typeof navigator.requestMediaKeySystemAccess === "function",
    mseAac: window.MediaSource ? MediaSource.isTypeSupported(AUDIO) : false,
    userAgent: navigator.userAgent,
  };
  if (navigator.userAgentData) {
    try {
      const hi = await navigator.userAgentData.getHighEntropyValues(["fullVersionList"]);
      out.brands = hi.fullVersionList;
    } catch (e) {}
  }
  out.keySystems = [];
  for (const ks of KEY_SYSTEMS) out.keySystems.push(await probe(ks));
  out.robustness = [];
  for (const [ks, levels] of Object.entries(ROBUSTNESS)) {
    for (const level of levels) {
      const row = await probe(ks, [{ initDataTypes: ["cenc"],
        audioCapabilities: [{ contentType: AUDIO, robustness: level }] }]);
      out.robustness.push({ keySystem: ks, level, access: row.access, mediaKeys: row.mediaKeys });
    }
  }
  out.popup = await tryPopup();
  document.getElementById("status").textContent = "Done.";
  await fetch("/result?token=TOKEN", { method: "POST", body: JSON.stringify(out) });
})();
</script>
"""

POPUP = """<!doctype html><meta charset="utf-8"><title>popup</title>
<p>Popup</p>
<script>if (window.opener) window.opener.postMessage("popup-ready", location.origin);</script>
"""


def runtime_info() -> dict[str, Any]:
    """WebView2 runtime version as WebView2 reports it, and whether Evergreen is installed."""
    info: dict[str, Any] = {}
    try:
        from Microsoft.Web.WebView2.Core import (  # type: ignore[import-not-found]
            CoreWebView2Environment,
        )

        info["available_runtime"] = str(CoreWebView2Environment.GetAvailableBrowserVersionString())
    except Exception as error:  # pragma: no cover - spike
        info["available_runtime"] = f"unknown ({type(error).__name__})"
    client = r"Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"
    for hive, path, label in (
        (winreg.HKEY_LOCAL_MACHINE, rf"SOFTWARE\WOW6432Node\{client}", "machine"),
        (winreg.HKEY_CURRENT_USER, rf"SOFTWARE\{client}", "user"),
    ):
        try:
            with winreg.OpenKey(hive, path) as key:
                info[f"evergreen_{label}"] = winreg.QueryValueEx(key, "pv")[0]
        except OSError:
            info[f"evergreen_{label}"] = None
    return info


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--popups", choices=["pywebview", "webview2"], default="pywebview")
    parser.add_argument("--no-private", action="store_true")
    args = parser.parse_args()

    import webview  # pyright: ignore[reportMissingTypeStubs]
    from webview.platforms import edgechromium  # pyright: ignore[reportMissingTypeStubs]

    wv: Any = webview
    popup_requests: list[str] = []

    if args.popups == "pywebview":

        def record_only(self: Any, sender: Any, event: Any) -> None:
            # pywebview's own handler, minus opening the URL in the system browser.
            event.set_Handled(True)
            popup_requests.append(str(event.get_Uri()).split("?")[0])

        edgechromium.EdgeChrome.on_new_window_request = record_only
    else:

        def let_webview2_open(self: Any, sender: Any, event: Any) -> None:
            popup_requests.append(str(event.get_Uri()).split("?")[0])  # Handled stays False

        edgechromium.EdgeChrome.on_new_window_request = let_webview2_open

    token = secrets.token_urlsafe(16)
    result: dict[str, Any] = {}
    loop = asyncio.new_event_loop()
    ready = threading.Event()
    done = threading.Event()
    port_box: list[int] = []

    def checked(request: web.Request) -> None:
        if request.query.get("token") != token:
            raise web.HTTPForbidden()

    async def index(request: web.Request) -> web.Response:
        checked(request)
        return web.Response(text=PAGE.replace("TOKEN", token), content_type="text/html")

    async def popup(request: web.Request) -> web.Response:
        checked(request)
        return web.Response(text=POPUP, content_type="text/html")

    async def post_result(request: web.Request) -> web.Response:
        checked(request)
        result.update(json.loads(await request.text()))
        done.set()
        return web.Response(text="ok")

    async def post_log(request: web.Request) -> web.Response:
        checked(request)
        print("page:", await request.text(), file=sys.stderr, flush=True)
        return web.Response(text="ok")

    async def serve() -> None:
        app = web.Application()
        app.router.add_get("/", index)
        app.router.add_get("/popup", popup)
        app.router.add_post("/result", post_result)
        app.router.add_post("/log", post_log)
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "127.0.0.1", 0)
        await site.start()
        server: Any = site._server  # pyright: ignore[reportPrivateUsage]
        port_box.append(server.sockets[0].getsockname()[1])
        ready.set()

    def run_loop() -> None:
        asyncio.set_event_loop(loop)
        loop.run_until_complete(serve())
        loop.run_forever()

    threading.Thread(target=run_loop, daemon=True).start()
    ready.wait()
    url = f"http://127.0.0.1:{port_box[0]}/?token={token}"
    window: Any = wv.create_window("Tandem DRM probe", url, width=520, height=320)

    def watcher() -> None:
        if not done.wait(timeout=180):
            result["error"] = "timed out waiting for the probe page"
        window.destroy()

    threading.Thread(target=watcher, daemon=True).start()
    wv.start(private_mode=not args.no_private)

    report = {
        "mode": {"private_mode": not args.no_private, "popups": args.popups},
        "runtime": runtime_info(),
        "popup_requests_seen_by_host": popup_requests,
        **result,
    }
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
