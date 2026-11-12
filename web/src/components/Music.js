import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { Button, Chip, ProgressBar, Slider } from "@heroui/react";
import { useEffect, useState } from "react";
import { formatTime } from "../controls";
import { MusicIcon, NextIcon, PauseIcon, PlayIcon, PreviousIcon, SkipBackwardIcon, SkipForwardIcon, } from "../icons";
import { allows, artworkUrl, canSkip, isPlaying, musicPosition, musicSubtitle, progressKind, seekTarget, } from "../music";
import { strings } from "../strings";
function useNow(active) {
    const [now, setNow] = useState(() => performance.now());
    useEffect(() => {
        if (!active)
            return;
        const timer = window.setInterval(() => setNow(performance.now()), 500);
        return () => window.clearInterval(timer);
    }, [active]);
    return now;
}
/** Count on from the last position the app reported, while it plays. */
function useMusicPosition(music) {
    const [since, setSince] = useState(() => performance.now());
    useEffect(() => setSince(performance.now()), [music.position, music.state]);
    const now = useNow(isPlaying(music));
    return musicPosition(music, (now - since) / 1000);
}
/** The artwork, or a drawn note when there is none (or it won't load). */
function Artwork({ music, size, className }) {
    const [failed, setFailed] = useState(null);
    const version = music.artwork;
    const src = version !== null && failed !== version ? artworkUrl(window.location.search, version) : null;
    return (_jsx("div", { className: className, style: { width: size, height: size }, "aria-hidden": "true", children: src ? (_jsx("img", { src: src, alt: "", draggable: false, onError: () => setFailed(version) })) : (_jsx(MusicIcon, { size: Math.round(size * 0.42) })) }));
}
function MusicButton({ music, command, send, main = false, children, label, }) {
    return (_jsx(Button, { isIconOnly: true, variant: main ? "secondary" : "ghost", size: main ? "lg" : "md", "aria-label": label, isDisabled: !allows(music, command), onPress: () => send({ type: "music", command }), className: main ? "media-main" : undefined, children: children }));
}
function PlayPauseButton({ music, send, main, size }) {
    const playing = isPlaying(music);
    return (_jsx(MusicButton, { music: music, command: "play_pause", send: send, main: main, label: playing ? strings.music.pause : strings.music.play, children: playing ? _jsx(PauseIcon, { size: size }) : _jsx(PlayIcon, { size: size }) }));
}
function Progress({ music, send }) {
    const position = useMusicPosition(music);
    // Follow the app, but don't fight the user while they drag.
    const [dragging, setDragging] = useState(null);
    const kind = progressKind(music);
    if (kind === "live" || position === null || music.duration === null) {
        return (_jsx("div", { className: "flex", children: _jsx(Chip, { size: "sm", variant: "soft", color: "accent", children: strings.music.live }) }));
    }
    const shown = dragging ?? position;
    const times = (_jsxs("div", { className: "flex justify-between text-[11px] tabular-nums text-[var(--muted)]", children: [_jsx("span", { children: formatTime(shown) }), _jsxs("span", { children: ["-", formatTime(music.duration - shown)] })] }));
    const label = strings.music.of(formatTime(shown), formatTime(music.duration));
    if (kind === "bar") {
        return (_jsxs("div", { className: "flex flex-col gap-1", children: [_jsx(ProgressBar, { "aria-label": label, value: shown, maxValue: music.duration, size: "sm", children: _jsx(ProgressBar.Track, { children: _jsx(ProgressBar.Fill, {}) }) }), times] }));
    }
    return (_jsxs("div", { className: "flex flex-col gap-1", children: [_jsx(Slider, { "aria-label": strings.music.position, minValue: 0, maxValue: music.duration, step: 1, value: shown, onChange: (value) => setDragging(Array.isArray(value) ? (value[0] ?? 0) : value), onChangeEnd: (value) => {
                    const next = Array.isArray(value) ? (value[0] ?? 0) : value;
                    setDragging(null);
                    send({ type: "musicSeek", position: next });
                }, children: _jsxs(Slider.Track, { children: [_jsx(Slider.Fill, {}), _jsx(Slider.Thumb, {})] }) }), times] }));
}
/** The Music tab: what any app on the PC is playing, with its controls. */
export function MusicPanel({ music, send }) {
    if (music === null) {
        return (_jsxs("div", { className: "empty-state glass", children: [_jsx("span", { className: "music-empty-icon", children: _jsx(MusicIcon, { size: 28 }) }), _jsx("h2", { className: "text-[17px] font-semibold", children: strings.music.nothingTitle }), _jsx("p", { className: "max-w-md text-center text-[var(--muted)]", children: strings.music.nothingBody })] }));
    }
    const title = music.title ?? strings.music.untitled;
    const subtitle = musicSubtitle(music);
    return (_jsxs("div", { className: "flex flex-col gap-4", children: [_jsxs("section", { className: "music-card glass", "aria-label": title, children: [_jsx(Artwork, { music: music, size: 220, className: "music-art" }), _jsxs("div", { className: "music-details", children: [_jsx("p", { className: "now-playing-app", children: strings.music.from(music.app ?? strings.music.anApp) }), _jsx("h2", { className: "music-title", children: title }), subtitle && _jsx("p", { className: "music-subtitle", children: subtitle }), _jsx(Progress, { music: music, send: send }), _jsxs("div", { className: "flex items-center gap-2", role: "group", "aria-label": strings.music.title, children: [_jsx(MusicButton, { music: music, command: "previous", send: send, label: strings.music.previous, children: _jsx(PreviousIcon, { size: 22 }) }), _jsx(PlayPauseButton, { music: music, send: send, main: true, size: 26 }), _jsx(MusicButton, { music: music, command: "next", send: send, label: strings.music.next, children: _jsx(NextIcon, { size: 22 }) })] })] })] }), _jsx("p", { className: "px-2 text-[12px] text-[var(--muted)]", children: strings.music.note })] }));
}
/** A compact bar at the bottom of the window, on the other tabs. */
export function NowPlayingBar({ music, send, onOpen }) {
    const title = music.title ?? strings.music.untitled;
    const subtitle = musicSubtitle(music) ?? music.app;
    return (_jsxs("div", { className: "now-playing-bar glass", role: "region", "aria-label": strings.music.bar(title), children: [_jsxs("button", { type: "button", className: "now-playing-bar-open", onClick: onOpen, "aria-label": strings.music.bar(title), children: [_jsx(Artwork, { music: music, size: 40, className: "music-art music-art-small" }), _jsxs("span", { className: "flex min-w-0 flex-col text-left", children: [_jsx("span", { className: "now-playing-bar-title", children: title }), subtitle && _jsx("span", { className: "now-playing-bar-subtitle", children: subtitle })] })] }), _jsx(PlayPauseButton, { music: music, send: send, size: 20 }), _jsx(MusicButton, { music: music, command: "next", send: send, label: strings.music.next, children: _jsx(NextIcon, { size: 18 }) })] }));
}
const SKIP_SECONDS = 15;
/** A speaker's remote while it plays this PC's sound: the PC's app is what plays, so the
 *  buttons drive it (previous, back 15 s, play or pause, forward 15 s, next). */
export function PcPlaybackCard({ music, send }) {
    if (music === null) {
        return (_jsxs("section", { className: "now-playing glass", "aria-label": strings.music.nothingTitle, children: [_jsx("p", { className: "now-playing-title", children: strings.music.nothingTitle }), _jsx("p", { className: "now-playing-subtitle", children: strings.speakerRemote.nothingBody })] }));
    }
    return _jsx(PcPlaybackControls, { music: music, send: send });
}
function PcPlaybackControls({ music, send }) {
    const position = useMusicPosition(music);
    const title = music.title ?? strings.music.untitled;
    const subtitle = musicSubtitle(music);
    const skip = canSkip(music) && position !== null;
    const seek = (by) => {
        if (position !== null)
            send({ type: "musicSeek", position: seekTarget(music, position, by) });
    };
    return (_jsxs("section", { className: "now-playing glass", "aria-label": title, children: [_jsxs("div", { className: "flex items-center gap-3", children: [_jsx(Artwork, { music: music, size: 56, className: "music-art music-art-small" }), _jsxs("div", { className: "min-w-0 flex-1", children: [_jsx("p", { className: "now-playing-app", children: strings.music.from(music.app ?? strings.music.anApp) }), _jsx("p", { className: "now-playing-title", children: title }), subtitle && _jsx("p", { className: "now-playing-subtitle", children: subtitle })] })] }), _jsxs("div", { className: "flex items-center justify-center gap-1", role: "group", "aria-label": strings.speakerRemote.controls, children: [_jsx(MusicButton, { music: music, command: "previous", send: send, label: strings.music.previous, children: _jsx(PreviousIcon, { size: 22 }) }), skip && (_jsx(Button, { isIconOnly: true, variant: "ghost", "aria-label": strings.speakerRemote.back(SKIP_SECONDS), onPress: () => seek(-SKIP_SECONDS), children: _jsx(SkipBackwardIcon, { size: 22 }) })), _jsx(PlayPauseButton, { music: music, send: send, main: true, size: 26 }), skip && (_jsx(Button, { isIconOnly: true, variant: "ghost", "aria-label": strings.speakerRemote.forward(SKIP_SECONDS), onPress: () => seek(SKIP_SECONDS), children: _jsx(SkipForwardIcon, { size: 22 }) })), _jsx(MusicButton, { music: music, command: "next", send: send, label: strings.music.next, children: _jsx(NextIcon, { size: 22 }) })] })] }));
}
