import { Fragment as _Fragment, jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { Button, Modal, ProgressBar, Slider } from "@heroui/react";
import { useEffect, useRef, useState } from "react";
import { estimatePosition, formatTime, keyFor, mediaButtons, pressAction, subtitle } from "../controls";
import { AppsPanel } from "./AppsPanel";
import { LiveSlider } from "./LiveSlider";
import { PcPlaybackCard } from "./Music";
import { TextEntry } from "./TextEntry";
import { AppsIcon, BackIcon, ChevronIcon, DeviceIcon, KeyboardIcon, NextIcon, PauseIcon, PlayIcon, PowerIcon, PreviousIcon, SkipBackwardIcon, SkipForwardIcon, TvIcon, VolumeIcon, } from "../icons";
import { strings } from "../strings";
import { outputVolume } from "../audio";
import { statusFor } from "../devices";
/** A remote button: a quick press is a tap, a long one a hold (like the Siri Remote). */
function RemoteButton({ deviceId, remoteKey, label, send, className, holdable = true, children, }) {
    const started = useRef(0);
    return (_jsx(Button, { isIconOnly: true, variant: "tertiary", "aria-label": label, className: className, onPressStart: () => {
            started.current = performance.now();
        }, onPress: () => {
            const action = holdable ? pressAction(performance.now() - started.current) : "tap";
            send({ type: "press", id: deviceId, key: remoteKey, action });
        }, children: children }));
}
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
/** What's playing, with its media buttons. `compact` (beside the touch pad) puts the buttons on
 * the title's row and keeps only a thin progress line, so the remote fits without scrolling. */
function NowPlayingCard({ deviceId, playing, controls, send, compact = false }) {
    // Count on from the last position the device pushed, while it plays.
    const [since, setSince] = useState(() => performance.now());
    useEffect(() => setSince(performance.now()), [playing.position, playing.state]);
    const now = useNow(playing.state === "playing");
    const position = estimatePosition(playing, Math.max(0, (now - since) / 1000));
    const nothing = playing.state === "idle" || !playing.title;
    const media = (command) => send({ type: "media", id: deviceId, command });
    const isPlaying = playing.state === "playing";
    const icons = {
        previous: { icon: _jsx(PreviousIcon, { size: 22 }), label: strings.remote.previous },
        skip_backward: { icon: _jsx(SkipBackwardIcon, { size: 22 }), label: strings.remote.skipBackward },
        play_pause: {
            icon: isPlaying ? _jsx(PauseIcon, { size: 26 }) : _jsx(PlayIcon, { size: 26 }),
            label: isPlaying ? strings.remote.pause : strings.remote.play,
        },
        skip_forward: { icon: _jsx(SkipForwardIcon, { size: 22 }), label: strings.remote.skipForward },
        next: { icon: _jsx(NextIcon, { size: 22 }), label: strings.remote.next },
    };
    const buttons = (_jsx("div", { className: "flex flex-none items-center justify-center gap-1", children: mediaButtons(controls)
            .filter((command) => !compact || command === "previous" || command === "play_pause" || command === "next")
            .map((command) => (_jsx(Button, { isIconOnly: true, variant: command === "play_pause" ? "secondary" : "ghost", size: command === "play_pause" && !compact ? "lg" : "md", "aria-label": icons[command].label, onPress: () => media(command), className: command === "play_pause" ? (compact ? "media-main media-main-compact" : "media-main") : undefined, children: icons[command].icon }, command))) }));
    const hasProgress = !nothing && position !== null && playing.totalTime !== null && playing.totalTime > 0;
    if (compact) {
        return (_jsxs("section", { className: "now-playing now-playing-compact glass", "aria-label": nothing ? strings.remote.nothingPlaying : playing.title ?? "", children: [_jsxs("div", { className: "flex items-center gap-3", children: [_jsxs("div", { className: "min-w-0 flex-1", children: [playing.app && _jsx("p", { className: "now-playing-app", children: playing.app }), _jsx("p", { className: "now-playing-title", children: nothing ? strings.remote.nothingPlaying : playing.title }), !nothing && subtitle(playing) && _jsx("p", { className: "now-playing-subtitle", children: subtitle(playing) })] }), buttons] }), hasProgress && (_jsx(ProgressBar, { "aria-label": `${formatTime(position)} of ${formatTime(playing.totalTime)}`, value: position, maxValue: playing.totalTime, size: "sm", children: _jsx(ProgressBar.Track, { children: _jsx(ProgressBar.Fill, {}) }) }))] }));
    }
    return (_jsxs("section", { className: "now-playing glass", "aria-label": nothing ? strings.remote.nothingPlaying : playing.title ?? "", children: [playing.app && _jsx("p", { className: "now-playing-app", children: playing.app }), _jsx("p", { className: "now-playing-title", children: nothing ? strings.remote.nothingPlaying : playing.title }), !nothing && subtitle(playing) && _jsx("p", { className: "now-playing-subtitle", children: subtitle(playing) }), hasProgress && position !== null && playing.totalTime !== null && (_jsxs("div", { className: "flex flex-col gap-1", children: [_jsx(ProgressBar, { "aria-label": `${formatTime(position)} of ${formatTime(playing.totalTime)}`, value: position, maxValue: playing.totalTime, size: "sm", children: _jsx(ProgressBar.Track, { children: _jsx(ProgressBar.Fill, {}) }) }), _jsxs("div", { className: "flex justify-between text-[11px] tabular-nums text-[var(--muted)]", children: [_jsx("span", { children: formatTime(position) }), _jsxs("span", { children: ["-", formatTime(playing.totalTime - position)] })] })] })), buttons] }));
}
function TouchPad({ deviceId, send }) {
    const arrow = (key, label) => (_jsx(RemoteButton, { deviceId: deviceId, remoteKey: key, label: label, send: send, className: `pad-arrow pad-${key}`, children: _jsx(ChevronIcon, { direction: key, size: 22 }) }));
    return (_jsxs("div", { className: "pad", role: "group", "aria-label": strings.remote.pad, children: [arrow("up", strings.remote.up), arrow("left", strings.remote.left), _jsx(RemoteButton, { deviceId: deviceId, remoteKey: "select", label: strings.remote.select, send: send, className: "pad-select", children: _jsx("span", { className: "pad-select-dot" }) }), arrow("right", strings.remote.right), arrow("down", strings.remote.down)] }));
}
function VolumeControl({ deviceId, controls, send }) {
    // Follow the device's level, but don't fight the user while they drag.
    const [dragging, setDragging] = useState(null);
    if (controls.volume === "none") {
        return _jsx("p", { className: "text-center text-[13px] text-[var(--muted)]", children: strings.remote.volumeElsewhere });
    }
    if (controls.volume === "steps") {
        return (_jsxs("div", { className: "flex items-center justify-center gap-3", role: "group", "aria-label": strings.remote.volume, children: [_jsx(RemoteButton, { deviceId: deviceId, remoteKey: "volume_down", label: strings.remote.volumeDown, send: send, holdable: false, className: "round-key", children: _jsx(VolumeIcon, { level: 0, size: 20 }) }), _jsx("span", { className: "text-[13px] text-[var(--muted)]", children: strings.remote.volume }), _jsx(RemoteButton, { deviceId: deviceId, remoteKey: "volume_up", label: strings.remote.volumeUp, send: send, holdable: false, className: "round-key", children: _jsx(VolumeIcon, { level: 2, size: 20 }) })] }));
    }
    const level = dragging ?? controls.volumeLevel ?? 0;
    return (_jsxs("div", { className: "flex items-center gap-3", children: [_jsx(VolumeIcon, { level: 0, size: 18, className: "text-[var(--muted)]" }), _jsx(Slider, { "aria-label": strings.remote.volume, className: "flex-1", minValue: 0, maxValue: 100, value: level, onChange: (value) => setDragging(Array.isArray(value) ? (value[0] ?? 0) : value), onChangeEnd: (value) => {
                    const next = Array.isArray(value) ? (value[0] ?? 0) : value;
                    setDragging(null);
                    send({ type: "setVolume", id: deviceId, level: next });
                }, children: _jsxs(Slider.Track, { children: [_jsx(Slider.Fill, {}), _jsx(Slider.Thumb, {})] }) }), _jsx(VolumeIcon, { level: 2, size: 18, className: "text-[var(--muted)]" })] }));
}
/** A speaker's remote: audio only. While it plays this PC's sound, the buttons drive the app on
 *  the PC and the slider is the speaker's volume in the Audio panel; otherwise they drive
 *  whatever the speaker itself is playing. */
function SpeakerRemote({ device, controls, music, output, send }) {
    if (device.audio === "on" && output) {
        return (_jsxs(_Fragment, { children: [_jsx(PcPlaybackCard, { music: music, send: send }), _jsxs("div", { className: "flex items-center gap-3", children: [_jsx(VolumeIcon, { level: 0, size: 18, className: "text-[var(--muted)]" }), _jsx(LiveSlider, { label: strings.speakerRemote.volume, value: outputVolume(output), min: 0, max: 100, step: 1, onCommit: (level) => send({ type: "setOutputVolume", id: output.id, level }) }), _jsx(VolumeIcon, { level: 2, size: 18, className: "text-[var(--muted)]" })] }), _jsx("p", { className: "text-center text-[11px] text-[var(--muted)]", children: strings.speakerRemote.pcNote })] }));
    }
    if (controls === null) {
        return _jsx("p", { className: "text-center text-[var(--muted)]", children: statusFor(device, 0).text });
    }
    return (_jsxs(_Fragment, { children: [_jsx(NowPlayingCard, { deviceId: device.id, playing: controls.nowPlaying ?? IDLE, controls: controls, send: send }), _jsx(VolumeControl, { deviceId: device.id, controls: controls, send: send })] }));
}
const IDLE = {
    state: "idle",
    title: null,
    artist: null,
    album: null,
    series: null,
    app: null,
    position: null,
    totalTime: null,
};
export function RemoteSheet({ device, music, output, onClose, send }) {
    const controls = device?.controls ?? null;
    const speaker = device !== null && device.kind !== "apple_tv";
    const open = device !== null;
    const [view, setView] = useState("remote");
    const [typing, setTyping] = useState(false);
    // Each time the sheet opens, or moves to another device, start on the remote.
    useEffect(() => {
        setView("remote");
        setTyping(false);
    }, [device?.id]);
    // Show the keyboard field when the TV asks for text, and hide it when the TV stops asking.
    const asking = controls?.keyboard ?? false;
    const canType = controls?.textEntry ?? false;
    useEffect(() => {
        setTyping(asking);
        if (asking)
            setView("remote");
    }, [asking]);
    // Keyboard: arrows, Enter and Backspace work the remote, unless a control has focus that
    // uses those keys itself (the volume slider, or a focused button for Enter).
    const deviceId = device?.id;
    const hasRemote = !speaker && (controls?.remote ?? false) && view === "remote";
    useEffect(() => {
        if (!deviceId || !hasRemote)
            return;
        const onKeyDown = (event) => {
            const key = keyFor(event.key);
            if (!key || event.altKey || event.ctrlKey || event.metaKey)
                return;
            const target = event.target instanceof HTMLElement ? event.target : null;
            if (target?.closest('[role="slider"], input, textarea'))
                return;
            if (key === "select" && target?.closest("button"))
                return;
            event.preventDefault();
            send({ type: "press", id: deviceId, key, action: "tap" });
        };
        window.addEventListener("keydown", onKeyDown);
        return () => window.removeEventListener("keydown", onKeyDown);
    }, [deviceId, hasRemote, send]);
    return (_jsx(Modal.Backdrop, { isOpen: open, onOpenChange: (isOpen) => {
            if (!isOpen)
                onClose();
        }, variant: "blur", children: _jsx(Modal.Container, { placement: "center", size: "sm", children: _jsxs(Modal.Dialog, { className: "sheet remote-sheet", children: [_jsx(Modal.CloseTrigger, {}), device && (_jsxs(_Fragment, { children: [_jsxs(Modal.Header, { className: "flex flex-row items-center gap-3", children: [_jsx("span", { className: "device-icon", "data-connected": true, children: _jsx(DeviceIcon, { kind: device.kind, size: 22 }) }), _jsx(Modal.Heading, { className: "flex-1 truncate text-[18px] font-semibold", children: strings.remote.title(device.name) }), controls?.canPower && (_jsx(Button, { isIconOnly: true, variant: "tertiary", "aria-label": controls.power === "off" ? strings.remote.turnOn : strings.remote.turnOff, onPress: () => send({ type: "setPower", id: device.id, on: controls.power === "off" }), className: "mr-8", "data-power": controls.power, children: _jsx(PowerIcon, { size: 20 }) }))] }), _jsx(Modal.Body, { className: "flex flex-col gap-5", children: speaker ? (_jsx(SpeakerRemote, { device: device, controls: controls, music: music, output: output, send: send })) : controls === null ? (_jsx("p", { className: "text-center text-[var(--muted)]", children: statusFor(device, 0).text })) : view === "apps" && controls.apps ? (_jsx(AppsPanel, { deviceId: device.id, apps: device.apps, send: send, onDone: () => setView("remote") })) : (_jsxs(_Fragment, { children: [(controls.apps || controls.textEntry) && (_jsxs("div", { className: "flex items-center justify-center gap-2", children: [controls.apps && (_jsxs(Button, { variant: "secondary", size: "sm", onPress: () => setView("apps"), children: [_jsx(AppsIcon, { size: 16 }), strings.launcher.open] })), controls.textEntry && (_jsxs(Button, { variant: typing ? "primary" : "secondary", size: "sm", "aria-pressed": typing, "aria-label": typing ? strings.typing.close : strings.typing.open, onPress: () => setTyping(!typing), children: [_jsx(KeyboardIcon, { size: 16 }), strings.typing.open] }))] })), typing && canType && (_jsx(TextEntry, { deviceId: device.id, asking: asking, send: send, onClose: () => setTyping(false) }, asking ? "asking" : "manual")), controls.nowPlaying && (_jsx(NowPlayingCard, { deviceId: device.id, playing: controls.nowPlaying, controls: controls, send: send, compact: controls.remote })), controls.remote && (_jsxs(_Fragment, { children: [_jsx(TouchPad, { deviceId: device.id, send: send }), _jsxs("div", { className: "flex items-center justify-center gap-4", children: [_jsx(RemoteButton, { deviceId: device.id, remoteKey: "menu", label: strings.remote.back, send: send, className: "round-key", children: _jsx(BackIcon, { size: 22 }) }), _jsx(RemoteButton, { deviceId: device.id, remoteKey: "home", label: strings.remote.home, send: send, className: "round-key", children: _jsx(TvIcon, { size: 20 }) }), _jsx(RemoteButton, { deviceId: device.id, remoteKey: "play_pause", label: strings.remote.playPause, send: send, holdable: false, className: "round-key", children: _jsxs("span", { className: "flex items-center", children: [_jsx(PlayIcon, { size: 14 }), _jsx(PauseIcon, { size: 14 })] }) })] }), _jsx("p", { className: "text-center text-[11px] text-[var(--muted)]", children: strings.remote.keyboardHint })] })), _jsx(VolumeControl, { deviceId: device.id, controls: controls, send: send })] })) })] }))] }) }) }));
}
