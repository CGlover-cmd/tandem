import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { SearchField, Spinner } from "@heroui/react";
import { useEffect, useRef, useState } from "react";
import { formatTime } from "../controls";
import { MusicIcon } from "../icons";
import { badgeUrl, catalogArtUrl } from "../catalog";
import { strings } from "../strings";
const words = strings.appleMusic;
/** A result's artwork, fetched from Apple through Tandem; a drawn note if there is none. */
function CatalogArt({ id, hasArt, size }) {
    const [broken, setBroken] = useState(false);
    return (_jsx("span", { className: "library-art", style: { width: size, height: size }, "aria-hidden": "true", children: hasArt && !broken ? (_jsx("img", { src: catalogArtUrl(window.location.search, id), alt: "", loading: "lazy", draggable: false, onError: () => setBroken(true) })) : (_jsx(MusicIcon, { size: Math.round(size * 0.42) })) }));
}
/** Apple's "Listen on Apple Music" badge as the way to open a result (Apple's terms ask for the
 *  badge next to its artwork). Without a connection to Apple, plain words instead. */
function OpenButton({ id, title, send }) {
    const [noBadge, setNoBadge] = useState(false);
    return (_jsx("button", { type: "button", className: "apple-badge-button", "aria-label": words.open(title), onClick: () => send({ type: "openInAppleMusic", id }), children: noBadge ? (_jsx("span", { className: "apple-badge-text", children: words.openShort })) : (_jsx("img", { src: badgeUrl(window.location.search), alt: "", height: 34, draggable: false, onError: () => setNoBadge(true) })) }));
}
function SongResult({ song, send }) {
    return (_jsxs("li", { className: "catalog-row", children: [_jsx(CatalogArt, { id: song.id, hasArt: song.hasArt, size: 48 }), _jsxs("span", { className: "flex min-w-0 flex-1 flex-col", children: [_jsx("span", { className: "truncate font-medium", children: song.title }), _jsx("span", { className: "truncate text-[12px] text-[var(--muted)]", children: [song.artist, song.album, song.duration !== null ? formatTime(song.duration) : null].filter(Boolean).join(" · ") })] }), _jsx(OpenButton, { id: song.id, title: song.title, send: send })] }));
}
function AlbumResult({ album, send }) {
    return (_jsxs("li", { className: "catalog-album", children: [_jsx(CatalogArt, { id: album.id, hasArt: album.hasArt, size: 140 }), _jsx("span", { className: "album-tile-title", children: album.title }), _jsx("span", { className: "album-tile-artist", children: [album.artist, album.year].filter(Boolean).join(" · ") }), _jsx(OpenButton, { id: album.id, title: album.title, send: send })] }));
}
/** "Apple Music": search Apple's catalog and open results in the Apple Music app. */
export function AppleMusicView({ catalog, send }) {
    const [text, setText] = useState(catalog.query);
    const timer = useRef(undefined);
    useEffect(() => () => window.clearTimeout(timer.current), []);
    const search = (value) => {
        setText(value);
        window.clearTimeout(timer.current);
        // Wait for a pause in typing: Apple allows about 20 searches a minute.
        timer.current = window.setTimeout(() => send({ type: "searchCatalog", text: value }), 600);
    };
    const query = text.trim();
    // The words the engine searches for (it folds spaces and keeps 100 characters). Until its
    // results are for these words, the typed search is still on its way.
    const asked = query.replace(/\s+/g, " ").slice(0, 100);
    let results = null;
    if (query) {
        if (catalog.searching || catalog.query !== asked) {
            results = (_jsxs("p", { className: "flex items-center gap-2 text-[var(--muted)]", "aria-live": "polite", children: [_jsx(Spinner, { size: "sm" }), words.searching] }));
        }
        else if (catalog.error) {
            results = (_jsx("p", { className: "text-[var(--muted)]", role: "alert", children: catalog.error === "busy" ? words.busy : words.unavailable }));
        }
        else if (catalog.songs.length === 0) {
            results = _jsx("p", { className: "text-[var(--muted)]", children: words.noMatch(query) });
        }
        else {
            results = (_jsxs("div", { className: "flex flex-col gap-4", "aria-live": "polite", children: [catalog.albums.length > 0 && (_jsxs("section", { className: "flex flex-col gap-2", children: [_jsx("h2", { className: "section-title", children: words.albums }), _jsx("ul", { className: "catalog-albums", children: catalog.albums.map((album) => (_jsx(AlbumResult, { album: album, send: send }, album.id))) })] })), _jsxs("section", { className: "flex flex-col gap-2", children: [_jsx("h2", { className: "section-title", children: words.songs }), _jsx("ul", { className: "song-list glass", children: catalog.songs.map((song) => (_jsx(SongResult, { song: song, send: send }, song.id))) })] })] }));
        }
    }
    return (_jsxs("div", { className: "flex flex-col gap-4", children: [_jsx("p", { className: "text-[13px] text-[var(--muted)]", children: words.about }), _jsx(SearchField, { "aria-label": words.search, value: text, onChange: search, children: _jsxs(SearchField.Group, { children: [_jsx(SearchField.SearchIcon, {}), _jsx(SearchField.Input, { placeholder: words.search }), _jsx(SearchField.ClearButton, {})] }) }), results, _jsx("p", { className: "px-2 text-[11px] text-[var(--muted)]", children: words.noLibrary }), _jsx("p", { className: "px-2 text-[11px] text-[var(--muted)]", children: words.credit })] }));
}
