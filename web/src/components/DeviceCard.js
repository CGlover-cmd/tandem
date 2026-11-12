import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { Button, Card, Spinner } from "@heroui/react";
import { useEffect, useState } from "react";
import { cardButtons, statusFor } from "../devices";
import { DeviceIcon, RemoteIcon, SendIcon, WavesIcon } from "../icons";
import { strings } from "../strings";
const TONE_COLOUR = {
    neutral: "var(--muted)",
    accent: "var(--tandem-accent-text)",
    success: "var(--success)",
    warning: "var(--warning)",
    danger: "var(--danger)",
};
/** Seconds left before a retry, counted down locally from the last `retryIn` we were sent. */
function useCountdown(device) {
    const [left, setLeft] = useState(0);
    useEffect(() => {
        if (device.state !== "waiting" || device.retryIn === null) {
            setLeft(0);
            return;
        }
        const due = Date.now() + device.retryIn * 1000;
        const tick = () => setLeft(Math.max(0, Math.ceil((due - Date.now()) / 1000)));
        tick();
        const timer = window.setInterval(tick, 250);
        return () => window.clearInterval(timer);
    }, [device.state, device.retryIn]);
    return left;
}
export function DeviceCard({ device, onAudio, onVideo, onRemote, onActivate }) {
    const secondsLeft = useCountdown(device);
    const buttons = cardButtons(device);
    const status = statusFor(device, secondsLeft);
    const connected = device.state === "connected" && !device.needsPairing;
    const playing = connected ? device.controls?.nowPlaying : null;
    // While the device plays this PC's sound, what it reports playing is that stream, not news.
    const showPlaying = playing && playing.title && playing.state !== "idle" && device.audio !== "on";
    const audio = buttons.audio;
    return (_jsxs(Card, { className: "glass device-card", "data-connected": connected || undefined, "aria-label": `${device.name}, ${strings.kind[device.kind]}, ${status.text}`, children: [_jsxs(Card.Header, { className: "flex flex-row items-start justify-between gap-3", children: [_jsx("span", { className: "device-icon", "data-connected": connected || undefined, children: _jsx(DeviceIcon, { kind: device.kind, size: 26 }) }), device.state === "connecting" && _jsx(Spinner, { size: "sm", color: "accent" }), buttons.quiet && (_jsx(Button, { size: "sm", variant: "ghost", onPress: onActivate, className: "card-quiet-action", children: buttons.quiet.label }))] }), _jsxs(Card.Content, { className: "gap-1", children: [_jsx(Card.Title, { className: "text-[15px] font-semibold leading-snug truncate", children: device.name }), _jsx(Card.Description, { className: "text-[13px] text-[var(--muted)]", children: strings.kind[device.kind] }), _jsxs("p", { className: "mt-1 flex items-center gap-2 text-[13px] text-[var(--muted)]", "aria-live": "polite", children: [_jsx("span", { className: "status-dot", style: { background: TONE_COLOUR[status.tone] } }), status.text] }), showPlaying && (_jsxs("p", { className: "truncate text-[12px] text-[var(--muted)]", title: playing.title ?? undefined, children: [_jsx("span", { "aria-hidden": "true", children: playing.state === "playing" ? "▶ " : "❚❚ " }), playing.title] }))] }), _jsxs(Card.Footer, { className: "flex flex-row flex-wrap items-center gap-2", children: [audio && (_jsxs(Button, { size: "sm", variant: audio.on ? "primary" : "secondary", isDisabled: !audio.enabled, "aria-pressed": audio.on, "aria-label": audio.on ? strings.action.audioOff(device.name) : strings.action.audioOn(device.name), onPress: onAudio, className: "card-media-button", "data-on": audio.on || undefined, children: [audio.state === "starting" ? _jsx(Spinner, { size: "sm", color: "current" }) : _jsx(WavesIcon, { size: 16 }), strings.action.audio] })), buttons.video && (_jsxs(Button, { size: "sm", variant: "secondary", isDisabled: device.state === "connecting", "aria-label": strings.action.videoOn(device.name), onPress: onVideo, className: "card-media-button", children: [_jsx(SendIcon, { size: 16 }), strings.action.video] })), buttons.fallback && (_jsx(Button, { size: "sm", variant: buttons.fallback.primary ? "primary" : "secondary", isDisabled: !buttons.fallback.enabled, onPress: onActivate, className: "min-w-24", children: buttons.fallback.label })), buttons.remote && (_jsxs(Button, { size: "sm", variant: "tertiary", isIconOnly: buttons.video, onPress: onRemote, "aria-label": `${strings.remote.open}: ${device.name}`, children: [_jsx(RemoteIcon, { size: 16 }), !buttons.video && strings.remote.open] }))] })] }));
}
