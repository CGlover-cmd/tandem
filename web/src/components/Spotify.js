import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { Button, SearchField, Spinner } from "@heroui/react";
import { useEffect, useRef, useState } from "react";
import { ComputerIcon, MusicIcon, PlayIcon, RefreshIcon, SpeakerIcon } from "../icons";
import { itemDetail, spotifyArtUrl, targetName } from "../spotify";
import { spotifyErrorText, strings } from "../strings";
const words = strings.spotify;
/** An item's artwork, fetched from Spotify through Tandem; a drawn note if there is none. */
function Art({ item, size }) {
    const [broken, setBroken] = useState(false);
    return (_jsx("span", { className: "library-art", style: { width: size, height: size }, "aria-hidden": "true", children: item.hasArt && !broken ? (_jsx("img", { src: spotifyArtUrl(window.location.search, item.id), alt: "", loading: "lazy", draggable: false, onError: () => setBroken(true) })) : (_jsx(MusicIcon, { size: Math.round(size * 0.42) })) }));
}
/** One playlist, album or song: press it to play; "Open in Spotify" links back to Spotify. */
function ItemRow({ item, send }) {
    return (_jsxs("li", { className: "song-row", children: [_jsxs("button", { type: "button", className: "song-row-main", "aria-label": words.play(item.title), onClick: () => send({ type: "spotifyPlay", id: item.id }), children: [_jsx(Art, { item: item, size: 44 }), _jsxs("span", { className: "flex min-w-0 flex-1 flex-col", children: [_jsx("span", { className: "truncate font-medium", children: item.title }), _jsx("span", { className: "truncate text-[12px] text-[var(--muted)]", children: itemDetail(item) })] }), _jsx(PlayIcon, { size: 16, className: "flex-none text-[var(--muted)]" })] }), _jsx(Button, { size: "sm", variant: "ghost", className: "flex-none", "aria-label": words.openOnSpotify(item.title), onPress: () => send({ type: "openInSpotify", id: item.id }), children: words.openShort })] }));
}
function DeviceRow({ device, target, send }) {
    const Icon = device.kind === "computer" ? ComputerIcon : SpeakerIcon;
    const chosen = device.id === target;
    return (_jsxs("li", { className: "catalog-row", "data-current": chosen || undefined, children: [_jsx(Icon, { size: 20, className: "flex-none text-[var(--muted)]" }), _jsxs("button", { type: "button", className: "flex min-w-0 flex-1 flex-col border-0 bg-transparent p-0 text-left text-inherit disabled:cursor-default", disabled: device.restricted, "aria-pressed": chosen, "aria-label": words.useDevice(device.name), onClick: () => send({ type: "spotifyChooseDevice", id: device.id }), children: [_jsx("span", { className: `truncate ${chosen ? "font-semibold" : "font-medium"}`, children: device.name }), _jsx("span", { className: "text-[12px] text-[var(--muted)]", children: device.restricted ? words.cantControl : device.active ? words.playingHere : "" })] }), !device.restricted && !device.active && (_jsx(Button, { size: "sm", variant: "secondary", onPress: () => send({ type: "spotifyTransfer", id: device.id }), children: words.playHere }))] }));
}
/** "Spotify" in the Music tab: playlists, search and devices. Spotify's own apps play. */
export function SpotifyView({ spotify, send, onOpenConnections }) {
    const [text, setText] = useState(spotify.query);
    const timer = useRef(undefined);
    useEffect(() => () => window.clearTimeout(timer.current), []);
    if (spotify.state !== "signed_in") {
        return (_jsxs("div", { className: "flex flex-col items-start gap-3", children: [_jsx("p", { className: "text-[var(--muted)]", children: spotify.state === "not_set_up" ? words.notConnected : words.signedOut }), spotify.error && _jsx("p", { className: "text-[13px] text-[var(--danger)]", children: spotifyErrorText(spotify.error, spotify.redirectUri) }), _jsx(Button, { variant: "primary", onPress: onOpenConnections, children: words.connect })] }));
    }
    const search = (value) => {
        setText(value);
        window.clearTimeout(timer.current);
        // Wait for a pause in typing: every search is a call to Spotify.
        timer.current = window.setTimeout(() => send({ type: "spotifySearch", text: value }), 500);
    };
    const query = text.trim();
    const asked = query.replace(/\s+/g, " ").slice(0, 100);
    const target = targetName(spotify);
    let results = null;
    if (query) {
        if (spotify.searching || spotify.query !== asked) {
            results = (_jsxs("p", { className: "flex items-center gap-2 text-[var(--muted)]", "aria-live": "polite", children: [_jsx(Spinner, { size: "sm" }), words.searching] }));
        }
        else if (spotify.results.length === 0) {
            results = _jsx("p", { className: "text-[var(--muted)]", children: words.noMatch(query) });
        }
        else {
            results = (_jsx("ul", { className: "song-list glass", "aria-live": "polite", children: spotify.results.map((item) => (_jsx(ItemRow, { item: item, send: send }, item.id))) }));
        }
    }
    return (_jsxs("div", { className: "flex flex-col gap-4", children: [spotify.error && (_jsxs("div", { className: "flex items-start gap-2 rounded-xl bg-[var(--field-background)] p-3", role: "alert", children: [_jsx("p", { className: "flex-1 text-[13px] text-[var(--danger)]", children: spotifyErrorText(spotify.error, spotify.redirectUri) }), _jsx(Button, { size: "sm", variant: "ghost", onPress: () => send({ type: "spotifyDismissError" }), children: strings.dismiss })] })), _jsx(SearchField, { "aria-label": words.search, value: text, onChange: search, children: _jsxs(SearchField.Group, { children: [_jsx(SearchField.SearchIcon, {}), _jsx(SearchField.Input, { placeholder: words.search }), _jsx(SearchField.ClearButton, {})] }) }), results, _jsxs("section", { className: "flex flex-col gap-2", children: [_jsxs("div", { className: "flex items-center justify-between gap-2", children: [_jsx("h2", { className: "section-title", children: words.devices }), _jsxs(Button, { size: "sm", variant: "ghost", isDisabled: spotify.loading, onPress: () => send({ type: "spotifyRefresh" }), children: [spotify.loading ? _jsx(Spinner, { size: "sm" }) : _jsx(RefreshIcon, { size: 16 }), words.refresh] })] }), spotify.devices.length === 0 ? (_jsx("p", { className: "text-[13px] text-[var(--muted)]", children: words.noDevices })) : (_jsx("ul", { className: "song-list glass", children: spotify.devices.map((device) => (_jsx(DeviceRow, { device: device, target: spotify.target, send: send }, device.id))) })), target && _jsx("p", { className: "px-2 text-[12px] text-[var(--muted)]", children: words.playsOn(target) })] }), !query && (_jsxs("section", { className: "flex flex-col gap-2", children: [_jsx("h2", { className: "section-title", children: words.playlists }), spotify.playlists.length === 0 ? (_jsx("p", { className: "text-[13px] text-[var(--muted)]", children: spotify.loading ? words.searching : words.noPlaylists })) : (_jsx("ul", { className: "song-list glass", children: spotify.playlists.map((item) => (_jsx(ItemRow, { item: item, send: send }, item.id))) }))] })), _jsx("p", { className: "px-2 text-[11px] text-[var(--muted)]", children: words.hearIt }), _jsx("p", { className: "px-2 text-[11px] text-[var(--muted)]", children: words.credit })] }));
}
