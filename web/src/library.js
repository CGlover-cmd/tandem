// What the Music tab's library, radio and queue show (Phase 6). Kept apart from React so it's
// tested. Titles, folders and searches are personal: on screen only, never logged.
/** An album's artwork on Tandem's own server; it needs this launch's token from the page's
 *  own address. */
export function albumArtUrl(search, albumId) {
    const token = new URLSearchParams(search).get("token") ?? "";
    return `/library-art/${encodeURIComponent(albumId)}?token=${encodeURIComponent(token)}`;
}
/** Albums grouped by artist, artists in name order with unknown last. */
export function groupByArtist(albums) {
    const groups = new Map();
    for (const album of albums) {
        const key = album.artist?.toLocaleLowerCase() ?? "";
        const group = groups.get(key) ?? { name: album.artist, albums: [] };
        group.albums.push(album);
        groups.set(key, group);
    }
    return [...groups.values()].sort((a, b) => {
        if (a.name === null)
            return 1;
        if (b.name === null)
            return -1;
        return a.name.localeCompare(b.name, undefined, { sensitivity: "base" });
    });
}
/** The track playing (or paused, or loading), if any. */
export function currentItem(player) {
    if (player.index === null)
        return null;
    return player.queue[player.index] ?? null;
}
/** What follows the current track. */
export function upNext(player) {
    if (player.index === null)
        return player.queue;
    return player.queue.slice(player.index + 1);
}
/** Where playback is now: the engine reports the position once a second, so we count on. */
export function playerPosition(player, elapsedSeconds) {
    const moving = player.state === "playing" ? Math.max(0, elapsedSeconds) : 0;
    const position = player.position + moving;
    return player.duration === null ? position : Math.min(position, player.duration);
}
/** "MP3 · 128 kbps · US", leaving out what the directory doesn't know. */
export function stationDetails(station, kbps) {
    const parts = [station.codec, station.bitrate > 0 ? kbps(station.bitrate) : "", station.country];
    return parts.filter(Boolean).join(" · ");
}
export function isSaved(saved, id) {
    return saved.some((station) => station.id === id);
}
/** The last part of a folder path, for a compact chip; the whole path goes in its tooltip. */
export function folderName(folder) {
    const parts = folder.split(/[\\/]+/).filter(Boolean);
    return parts[parts.length - 1] ?? folder;
}
