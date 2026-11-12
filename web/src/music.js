// What the Music tab and the now-playing bar show (Phase 6). Kept apart from React so it's
// tested. Titles are personal: they go on screen only, never to a log.
/** The artwork's address on Tandem's own server. It needs this launch's token, taken from
 *  the page's own address; `version` changes with the artwork, so a new one is fetched. */
export function artworkUrl(search, version) {
    const token = new URLSearchParams(search).get("token") ?? "";
    return `/artwork?token=${encodeURIComponent(token)}&v=${version}`;
}
/** Where playback is now: the app reports the position only now and then, so we count on. */
export function musicPosition(music, elapsedSeconds) {
    if (music.position === null)
        return null;
    const moving = music.state === "playing" ? Math.max(0, elapsedSeconds) : 0;
    const position = music.position + moving;
    return music.duration === null ? position : Math.min(position, music.duration);
}
/** The line under the title: "Artist · Album", or whichever of the two there is. */
export function musicSubtitle(music) {
    const parts = [music.artist, music.album].filter((part) => !!part);
    return parts.length > 0 ? parts.join(" · ") : null;
}
export function isPlaying(music) {
    return music.state === "playing";
}
export function allows(music, command) {
    return music.commands.includes(command);
}
/** A slider when the app lets us seek, a bar when it only tells us, nothing for live streams. */
export function progressKind(music) {
    if (music.duration === null || music.duration <= 0 || music.position === null)
        return "live";
    return music.canSeek ? "seek" : "bar";
}
/** Where a skip back or forward lands: `by` seconds from `position`, kept inside the track. */
export function seekTarget(music, position, by) {
    const end = music.duration ?? Number.POSITIVE_INFINITY;
    return Math.max(0, Math.min(end, position + by));
}
/** Skip back and forward are offered when the app lets us seek within a track. */
export function canSkip(music) {
    return progressKind(music) === "seek";
}
