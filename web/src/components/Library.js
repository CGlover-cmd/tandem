import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { Button, Chip, ProgressBar, SearchField, Spinner } from "@heroui/react";
import { useEffect, useMemo, useRef, useState } from "react";
import { formatTime } from "../controls";
import { CloseIcon, FolderIcon, MusicIcon, NextIcon, PauseIcon, PlayIcon, PlayNextIcon, PlusIcon, PreviousIcon, RadioIcon, RefreshIcon, SpeakerIcon, StopIcon, } from "../icons";
import { albumArtUrl, currentItem, folderName, groupByArtist, isSaved, playerPosition, stationDetails, upNext, } from "../library";
import { strings } from "../strings";
const words = strings.library;
/** An album's artwork from the library, or a drawn note (or radio) when there is none. */
export function AlbumArt({ albumId, size, radio = false, className = "", }) {
    const [broken, setBroken] = useState(null);
    const src = albumId && broken !== albumId ? albumArtUrl(window.location.search, albumId) : null;
    return (_jsx("span", { className: `library-art ${className}`, style: { width: size, height: size }, "aria-hidden": "true", children: src ? (_jsx("img", { src: src, alt: "", draggable: false, loading: "lazy", onError: () => setBroken(albumId) })) : radio ? (_jsx(RadioIcon, { size: Math.round(size * 0.45) })) : (_jsx(MusicIcon, { size: Math.round(size * 0.42) })) }));
}
function IconButton({ label, onPress, children, disabled = false }) {
    return (_jsx(Button, { isIconOnly: true, variant: "ghost", size: "sm", "aria-label": label, onPress: onPress, isDisabled: disabled, children: children }));
}
function useTicking(active) {
    const [now, setNow] = useState(() => performance.now());
    useEffect(() => {
        if (!active)
            return;
        const timer = window.setInterval(() => setNow(performance.now()), 500);
        return () => window.clearInterval(timer);
    }, [active]);
    return now;
}
/** Tandem's own player: what it plays, its transport, and where the sound goes. */
export function PlayerStrip({ player, speakers, send, onOpenAudio, }) {
    const item = currentItem(player);
    const [since, setSince] = useState(() => performance.now());
    useEffect(() => setSince(performance.now()), [player.position, player.state]);
    const now = useTicking(player.state === "playing");
    if (player.queue.length === 0)
        return null;
    const position = playerPosition(player, (now - since) / 1000);
    const playing = player.state === "playing";
    const control = (command) => send({ type: "player", command });
    const status = player.error ? words.failed : player.state === "loading" ? words.loading : player.state === "stopped" ? words.stopped : null;
    return (_jsxs("section", { className: "player-strip glass", "aria-label": words.nowPlayingLabel, children: [_jsx(AlbumArt, { albumId: item?.art ?? null, radio: item?.kind === "radio", size: 56, className: "library-art-small" }), _jsxs("div", { className: "flex min-w-0 flex-1 flex-col gap-1", children: [_jsx("p", { className: "now-playing-app", children: words.nowPlayingLabel }), _jsx("p", { className: "truncate text-[15px] font-semibold", children: item?.title ?? words.stopped }), _jsx("p", { className: "truncate text-[12px] text-[var(--muted)]", children: status ?? (item?.kind === "radio" ? words.live : [item?.artist, item?.album].filter(Boolean).join(" · ")) }), player.duration !== null && player.duration > 0 && item?.kind !== "radio" && (_jsxs("div", { className: "flex items-center gap-2", children: [_jsx(ProgressBar, { "aria-label": strings.music.of(formatTime(position), formatTime(player.duration)), value: position, maxValue: player.duration, size: "sm", className: "flex-1", children: _jsx(ProgressBar.Track, { children: _jsx(ProgressBar.Fill, {}) }) }), _jsxs("span", { className: "text-[11px] tabular-nums text-[var(--muted)]", children: [formatTime(position), " / ", formatTime(player.duration)] })] }))] }), _jsxs("div", { className: "flex items-center gap-1", role: "group", "aria-label": words.queue, children: [_jsx(IconButton, { label: strings.music.previous, onPress: () => control("previous"), disabled: item === null, children: _jsx(PreviousIcon, { size: 20 }) }), _jsx(Button, { isIconOnly: true, variant: "secondary", "aria-label": playing ? strings.music.pause : strings.music.play, onPress: () => control("play_pause"), className: "media-main", children: playing ? _jsx(PauseIcon, { size: 22 }) : _jsx(PlayIcon, { size: 22 }) }), _jsx(IconButton, { label: strings.music.next, onPress: () => control("next"), disabled: upNext(player).length === 0, children: _jsx(NextIcon, { size: 20 }) }), _jsx(IconButton, { label: words.stop, onPress: () => control("stop"), disabled: player.state === "stopped", children: _jsx(StopIcon, { size: 18 }) })] }), _jsxs(Button, { variant: speakers > 0 ? "tertiary" : "secondary", size: "sm", onPress: onOpenAudio, className: "player-speakers", children: [_jsx(SpeakerIcon, { size: 16 }), _jsx("span", { children: speakers > 0 ? words.toSpeakers(speakers) : words.noSpeakers })] })] }));
}
function SongRow({ song, send, showAlbum }) {
    return (_jsxs("li", { className: "song-row", children: [_jsxs("button", { type: "button", className: "song-row-main", onClick: () => send({ type: "playSong", id: song.id }), "aria-label": words.play(song.title), children: [_jsx("span", { className: "song-number", children: showAlbum ? _jsx(AlbumArt, { albumId: song.albumId, size: 32, className: "library-art-tiny" }) : song.number ?? "" }), _jsxs("span", { className: "flex min-w-0 flex-col", children: [_jsx("span", { className: "truncate", children: song.title }), showAlbum && (_jsx("span", { className: "truncate text-[12px] text-[var(--muted)]", children: [song.artist, song.album].filter(Boolean).join(" · ") }))] }), _jsx("span", { className: "song-duration", children: song.duration !== null ? formatTime(song.duration) : "" })] }), _jsx(IconButton, { label: words.playNext, onPress: () => send({ type: "queueSong", id: song.id, next: true }), children: _jsx(PlayNextIcon, { size: 18 }) }), _jsx(IconButton, { label: words.addToQueue, onPress: () => send({ type: "queueSong", id: song.id, next: false }), children: _jsx(PlusIcon, { size: 18 }) })] }));
}
function AlbumGrid({ albums, send }) {
    return (_jsx("ul", { className: "album-grid", children: albums.map((album) => (_jsx("li", { children: _jsxs("button", { type: "button", className: "album-tile", onClick: () => send({ type: "openAlbum", id: album.id }), children: [_jsx(AlbumArt, { albumId: album.hasArt ? album.id : null, size: 156, className: "album-tile-art" }), _jsx("span", { className: "album-tile-title", children: album.title }), _jsx("span", { className: "album-tile-artist", children: album.artist ?? words.unknownArtist })] }) }, album.id))) }));
}
function AlbumView({ album, songs, send }) {
    return (_jsxs("section", { className: "flex flex-col gap-4", "aria-label": album.title, children: [_jsx("div", { children: _jsx(Button, { variant: "ghost", size: "sm", onPress: () => send({ type: "closeAlbum" }), children: words.back }) }), _jsxs("div", { className: "album-header", children: [_jsx(AlbumArt, { albumId: album.hasArt ? album.id : null, size: 176, className: "album-header-art" }), _jsxs("div", { className: "flex min-w-0 flex-col gap-2", children: [_jsx("h2", { className: "music-title", children: album.title }), _jsx("p", { className: "music-subtitle", children: [album.artist ?? words.unknownArtist, album.year, words.songsCount(album.trackCount)].filter(Boolean).join(" · ") }), _jsxs("div", { className: "flex flex-wrap gap-2", children: [_jsxs(Button, { variant: "primary", onPress: () => send({ type: "playAlbum", id: album.id }), children: [_jsx(PlayIcon, { size: 16 }), words.playAlbum] }), _jsxs(Button, { variant: "secondary", onPress: () => send({ type: "queueAlbum", id: album.id, next: true }), children: [_jsx(PlayNextIcon, { size: 16 }), words.playNext] }), _jsxs(Button, { variant: "secondary", onPress: () => send({ type: "queueAlbum", id: album.id, next: false }), children: [_jsx(PlusIcon, { size: 16 }), words.addToQueue] })] })] })] }), _jsx("ul", { className: "song-list glass", children: songs.map((song) => (_jsx(SongRow, { song: song, send: send, showAlbum: false }, song.id))) })] }));
}
/** "This PC": the music library. */
export function LibraryView({ library, send }) {
    const [text, setText] = useState(library.search.text);
    const [mode, setMode] = useState("albums");
    const [artist, setArtist] = useState(undefined);
    const groups = useMemo(() => groupByArtist(library.albums), [library.albums]);
    const searching = text.trim().length > 0;
    const open = library.openAlbum;
    const openAlbum = open ? library.albums.find((a) => a.id === open.id) : undefined;
    const search = (value) => {
        setText(value);
        send({ type: "searchLibrary", text: value });
    };
    const header = (_jsxs("div", { className: "library-toolbar", children: [_jsx(SearchField, { "aria-label": words.search, value: text, onChange: search, className: "library-search", children: _jsxs(SearchField.Group, { children: [_jsx(SearchField.SearchIcon, {}), _jsx(SearchField.Input, { placeholder: words.search }), _jsx(SearchField.ClearButton, {})] }) }), _jsxs("div", { className: "flex flex-wrap items-center gap-2", "aria-label": words.folders, children: [library.folders.map((folder) => (_jsxs(Chip, { size: "sm", variant: "soft", title: folder, children: [_jsx(FolderIcon, { size: 14 }), _jsx("span", { children: folderName(folder) }), _jsx("button", { type: "button", className: "chip-remove", "aria-label": words.removeFolder(folder), onClick: () => send({ type: "removeMusicFolder", folder }), children: _jsx(CloseIcon, { size: 12 }) })] }, folder))), _jsxs(Button, { size: "sm", variant: "secondary", isDisabled: !library.canPickFolders || library.picking, onPress: () => send({ type: "addMusicFolder" }), children: [_jsx(PlusIcon, { size: 14 }), library.picking ? words.adding : words.addFolder] }), library.folders.length > 0 && (_jsx(IconButton, { label: words.rescan, onPress: () => send({ type: "rescanLibrary" }), disabled: library.scanning, children: _jsx(RefreshIcon, { size: 16 }) }))] })] }));
    let body;
    if (library.folders.length === 0) {
        body = (_jsxs("div", { className: "empty-state glass", children: [_jsx("span", { className: "music-empty-icon", children: _jsx(FolderIcon, { size: 28 }) }), _jsx("h2", { className: "text-[17px] font-semibold", children: words.emptyTitle }), _jsx("p", { className: "max-w-md text-center text-[var(--muted)]", children: library.canPickFolders ? words.emptyBody : words.noFolderPicker })] }));
    }
    else if (searching) {
        body =
            library.search.songs.length === 0 ? (_jsx("p", { className: "py-8 text-center text-[var(--muted)]", "aria-live": "polite", children: words.noMatch(text.trim()) })) : (_jsx("ul", { className: "song-list glass", "aria-live": "polite", children: library.search.songs.map((song) => (_jsx(SongRow, { song: song, send: send, showAlbum: true }, song.id))) }));
    }
    else if (open && openAlbum) {
        body = _jsx(AlbumView, { album: openAlbum, songs: open.songs, send: send });
    }
    else {
        const shown = mode === "artists" && artist !== undefined ? groups.find((g) => g.name === artist)?.albums ?? [] : library.albums;
        body = (_jsxs("div", { className: "flex flex-col gap-3", children: [_jsxs("div", { className: "flex items-center gap-2", role: "group", "aria-label": words.albums, children: [_jsx(Button, { size: "sm", variant: mode === "albums" ? "secondary" : "ghost", onPress: () => { setMode("albums"); setArtist(undefined); }, children: words.albums }), _jsx(Button, { size: "sm", variant: mode === "artists" ? "secondary" : "ghost", onPress: () => setMode("artists"), children: words.artists }), _jsx("span", { className: "ml-auto text-[12px] text-[var(--muted)]", "aria-live": "polite", children: library.scanning ? (_jsxs("span", { className: "flex items-center gap-2", children: [_jsx(Spinner, { size: "sm" }), words.scanning(library.scanned)] })) : (words.summary(library.albums.length, library.songCount)) })] }), mode === "artists" && (_jsxs("div", { className: "flex flex-wrap gap-2", "aria-label": words.artists, children: [_jsx(Button, { size: "sm", variant: artist === undefined ? "secondary" : "ghost", onPress: () => setArtist(undefined), children: words.allArtists }), groups.map((group) => (_jsx(Button, { size: "sm", variant: artist === group.name ? "secondary" : "ghost", onPress: () => setArtist(group.name), children: group.name ?? words.unknownArtist }, group.name ?? "")))] })), _jsx(AlbumGrid, { albums: shown, send: send })] }));
    }
    return (_jsxs("div", { className: "flex flex-col gap-4", children: [header, body] }));
}
function StationRow({ station, saved, send }) {
    return (_jsxs("li", { className: "song-row", children: [_jsxs("button", { type: "button", className: "song-row-main", onClick: () => send({ type: "playStation", id: station.id }), "aria-label": words.listen(station.name), children: [_jsx("span", { className: "song-number", children: _jsx(RadioIcon, { size: 18 }) }), _jsxs("span", { className: "flex min-w-0 flex-col", children: [_jsx("span", { className: "truncate", children: station.name }), _jsx("span", { className: "truncate text-[12px] text-[var(--muted)]", children: stationDetails(station, words.kbps) })] })] }), saved ? (_jsx(Button, { size: "sm", variant: "ghost", onPress: () => send({ type: "removeStation", id: station.id }), children: words.remove })) : (_jsx(Button, { size: "sm", variant: "ghost", onPress: () => send({ type: "saveStation", id: station.id }), children: words.save }))] }));
}
/** "Radio": search the open station directory, and saved stations. */
export function RadioView({ radio, send }) {
    const [text, setText] = useState(radio.query);
    const timer = useRef(undefined);
    useEffect(() => () => window.clearTimeout(timer.current), []);
    const search = (value) => {
        setText(value);
        window.clearTimeout(timer.current);
        // Wait for a pause in typing: each search is a request to the public directory.
        timer.current = window.setTimeout(() => send({ type: "searchRadio", text: value }), 450);
    };
    const query = text.trim();
    return (_jsxs("div", { className: "flex flex-col gap-4", children: [_jsx(SearchField, { "aria-label": words.radioSearch, value: text, onChange: search, children: _jsxs(SearchField.Group, { children: [_jsx(SearchField.SearchIcon, {}), _jsx(SearchField.Input, { placeholder: words.radioSearch }), _jsx(SearchField.ClearButton, {})] }) }), query && (_jsx("section", { className: "flex flex-col gap-2", "aria-live": "polite", children: radio.searching ? (_jsxs("p", { className: "flex items-center gap-2 text-[var(--muted)]", children: [_jsx(Spinner, { size: "sm" }), words.radioSearching] })) : radio.error ? (_jsx("p", { className: "text-[var(--muted)]", role: "alert", children: words.radioUnavailable })) : radio.results.length === 0 && radio.query === query ? (_jsx("p", { className: "text-[var(--muted)]", children: words.radioNoMatch(query) })) : (_jsx("ul", { className: "song-list glass", children: radio.results.map((station) => (_jsx(StationRow, { station: station, saved: isSaved(radio.saved, station.id), send: send }, station.id))) })) })), _jsxs("section", { className: "flex flex-col gap-2", children: [_jsx("h2", { className: "section-title", children: words.radioSaved }), radio.saved.length === 0 ? (_jsx("p", { className: "text-[13px] text-[var(--muted)]", children: words.radioNoSaved })) : (_jsx("ul", { className: "song-list glass", children: radio.saved.map((station) => (_jsx(StationRow, { station: station, saved: true, send: send }, station.id))) }))] }), _jsx("p", { className: "px-2 text-[11px] text-[var(--muted)]", children: words.radioCredit })] }));
}
function QueueRow({ item, current, send }) {
    return (_jsxs("li", { className: "song-row", "data-current": current ? "" : undefined, children: [_jsxs("button", { type: "button", className: "song-row-main", onClick: () => send({ type: "playQueueItem", id: item.id }), "aria-label": words.play(item.title), "aria-current": current ? "true" : undefined, children: [_jsx("span", { className: "song-number", children: _jsx(AlbumArt, { albumId: item.art, radio: item.kind === "radio", size: 32, className: "library-art-tiny" }) }), _jsxs("span", { className: "flex min-w-0 flex-col", children: [_jsx("span", { className: "truncate", children: item.title }), _jsx("span", { className: "truncate text-[12px] text-[var(--muted)]", children: item.kind === "radio" ? words.live : [item.artist, item.album].filter(Boolean).join(" · ") })] })] }), _jsx(IconButton, { label: words.removeFromQueue(item.title), onPress: () => send({ type: "removeQueueItem", id: item.id }), children: _jsx(CloseIcon, { size: 16 }) })] }));
}
/** "Queue": what Tandem's player is playing and what comes next. */
export function QueueView({ player, send }) {
    if (player.queue.length === 0) {
        return (_jsxs("div", { className: "empty-state glass", children: [_jsx("span", { className: "music-empty-icon", children: _jsx(MusicIcon, { size: 28 }) }), _jsx("p", { className: "max-w-md text-center text-[var(--muted)]", children: words.queueEmpty })] }));
    }
    return (_jsxs("section", { className: "flex flex-col gap-2", "aria-label": words.queue, children: [_jsxs("div", { className: "flex items-center justify-between", children: [_jsx("h2", { className: "section-title", children: words.upNext }), _jsx(Button, { size: "sm", variant: "ghost", onPress: () => send({ type: "clearQueue" }), children: words.clearQueue })] }), _jsx("ul", { className: "song-list glass", children: player.queue.map((item, index) => (_jsx(QueueRow, { item: item, current: index === player.index, send: send }, item.id))) })] }));
}
