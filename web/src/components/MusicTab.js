import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { Tabs } from "@heroui/react";
import { useState } from "react";
import { strings } from "../strings";
import { AppleMusicView } from "./AppleMusic";
import { LibraryView, PlayerStrip, QueueView, RadioView } from "./Library";
import { MusicPanel } from "./Music";
import { SpotifyView } from "./Spotify";
const SOURCES = ["now", "pc", "radio", "apple", "spotify", "queue"];
/** The Music tab: Tandem's own player on top, then what to play from. */
export function MusicTab({ state, send, onOpenAudio, onOpenConnections, }) {
    const [source, setSource] = useState("now");
    const words = strings.library;
    const label = {
        now: words.nowPlaying,
        pc: words.thisPc,
        radio: words.radio,
        apple: strings.appleMusic.source,
        spotify: strings.spotify.source,
        queue: `${words.queue}${state.player.queue.length > 0 ? ` (${state.player.queue.length})` : ""}`,
    };
    return (_jsxs("div", { className: "flex flex-col gap-4", children: [_jsx(PlayerStrip, { player: state.player, speakers: state.audio.streaming, send: send, onOpenAudio: onOpenAudio }), _jsxs(Tabs, { variant: "secondary", selectedKey: source, onSelectionChange: (key) => setSource(SOURCES.find((s) => s === key) ?? "now"), className: "music-sources", children: [_jsx(Tabs.List, { "aria-label": words.sources, className: "app-tabs", children: SOURCES.map((id) => (_jsxs(Tabs.Tab, { id: id, children: [label[id], _jsx(Tabs.Indicator, {})] }, id))) }), _jsx(Tabs.Panel, { id: "now", children: _jsx(MusicPanel, { music: state.music, send: send }) }), _jsx(Tabs.Panel, { id: "pc", children: _jsx(LibraryView, { library: state.library, send: send }) }), _jsx(Tabs.Panel, { id: "radio", children: _jsx(RadioView, { radio: state.radio, send: send }) }), _jsx(Tabs.Panel, { id: "apple", children: _jsx(AppleMusicView, { catalog: state.catalog, send: send }) }), _jsx(Tabs.Panel, { id: "spotify", children: _jsx(SpotifyView, { spotify: state.spotify, send: send, onOpenConnections: onOpenConnections }) }), _jsx(Tabs.Panel, { id: "queue", children: _jsx(QueueView, { player: state.player, send: send }) })] })] }));
}
