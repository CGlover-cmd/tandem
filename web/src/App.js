import { Fragment as _Fragment, jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { Button, Chip, Kbd, Spinner, Tabs, Toast, toast } from "@heroui/react";
import { useEffect, useMemo, useRef, useState, useSyncExternalStore } from "react";
import { useBridge } from "./bridge";
import { isCommandShortcut } from "./commands";
import { AdvancedSheet } from "./components/AdvancedSheet";
import { SpotifySheet } from "./components/Connections";
import { AudioSheet } from "./components/AudioSheet";
import { CommandBar } from "./components/CommandBar";
import { DeviceCard } from "./components/DeviceCard";
import { NowPlayingBar } from "./components/Music";
import { MusicTab } from "./components/MusicTab";
import { NetworkNote } from "./components/NetworkNote";
import { UpdateNote } from "./components/UpdateNote";
import { OnboardingSheet } from "./components/OnboardingSheet";
import { PairingSheet } from "./components/PairingSheet";
import { RemoteSheet } from "./components/RemoteSheet";
import { SendSheet } from "./components/SendSheet";
import { SettingsSheet } from "./components/SettingsSheet";
import { GearIcon, LogoMark, SearchIcon, WavesIcon } from "./icons";
import { problemText, strings } from "./strings";
import { applyTheme, DEFAULT_BACKGROUND, PHOTO_BACKGROUND, windowBackground } from "./theme";
const darkQuery = window.matchMedia("(prefers-color-scheme: dark)");
function useSystemMode() {
    const dark = useSyncExternalStore((onChange) => {
        darkQuery.addEventListener("change", onChange);
        return () => darkQuery.removeEventListener("change", onChange);
    }, () => darkQuery.matches);
    return dark ? "dark" : "light";
}
function resolveMode(choice, system) {
    return choice === "system" ? system : choice;
}
export function App() {
    const { state, status, send } = useBridge();
    const [settingsOpen, setSettingsOpen] = useState(false);
    const [advancedOpen, setAdvancedOpen] = useState(false);
    const [spotifyOpen, setSpotifyOpen] = useState(false);
    const [networkDismissed, setNetworkDismissed] = useState(false);
    const showNetworkNote = (state?.network.untrusted ?? false) && !networkDismissed;
    const [updateDismissed, setUpdateDismissed] = useState(false);
    const update = updateDismissed ? null : (state?.update ?? null);
    // Ctrl+Alt+K anywhere: the app brings the window up and bumps this count.
    const commandsRequested = state?.commandsRequested ?? 0;
    const seenRequests = useRef(null);
    useEffect(() => {
        if (seenRequests.current !== null && commandsRequested > seenRequests.current)
            setCommandsOpen(true);
        seenRequests.current = commandsRequested;
    }, [commandsRequested]);
    const [commandsOpen, setCommandsOpen] = useState(false);
    const [remoteId, setRemoteId] = useState(null);
    const [audioOpen, setAudioOpen] = useState(false);
    const [guideOpen, setGuideOpen] = useState(false);
    const onboarded = state?.appearance.onboarded ?? true;
    // The checklist opens by itself until it has been closed once.
    useEffect(() => {
        if (!onboarded)
            setGuideOpen(true);
    }, [onboarded]);
    const closeGuide = () => {
        setGuideOpen(false);
        if (!onboarded)
            send({ type: "setAppearance", onboarded: true });
    };
    const [sendId, setSendId] = useState(null);
    const sendDevice = state?.devices.find((d) => d.id === sendId) ?? null;
    // Video on an unpaired TV: pair first, then open the Send sheet.
    const [videoAfterPairing, setVideoAfterPairing] = useState(null);
    const pairingState = state?.pairing.state ?? "closed";
    const pairingWasOpen = useRef(false);
    useEffect(() => {
        if (videoAfterPairing === null)
            return;
        const device = state?.devices.find((d) => d.id === videoAfterPairing);
        if (pairingState !== "closed")
            pairingWasOpen.current = true;
        if (device && !device.needsPairing) {
            if (pairingState !== "closed")
                return; // wait for the pairing sheet to close
            setVideoAfterPairing(null);
            setSendId(device.id);
        }
        else if (!device || (pairingState === "closed" && pairingWasOpen.current)) {
            setVideoAfterPairing(null); // the device left, or pairing was cancelled
        }
    }, [videoAfterPairing, pairingState, state?.devices]);
    const streaming = state?.audio.streaming ?? 0;
    const [view, setView] = useState("devices");
    const music = state?.music ?? null;
    const showBar = music !== null && view !== "music";
    const remoteDevice = state?.devices.find((d) => d.id === remoteId) ?? null;
    const system = useSystemMode();
    const mode = resolveMode(state?.appearance.theme ?? "system", system);
    const backgroundId = state?.appearance.background ?? DEFAULT_BACKGROUND;
    const photo = state?.appearance.photo ?? null;
    const onPhoto = backgroundId === PHOTO_BACKGROUND && photo !== null;
    useEffect(() => applyTheme(mode), [mode]);
    useEffect(() => {
        document.documentElement.dataset.reduceMotion = state?.reduceMotion ? "true" : "false";
    }, [state?.reduceMotion]);
    // Ctrl+K opens the command bar from anywhere in the window.
    useEffect(() => {
        const onKey = (event) => {
            if (!isCommandShortcut(event))
                return;
            event.preventDefault();
            setCommandsOpen(true);
        };
        window.addEventListener("keydown", onKey);
        return () => window.removeEventListener("keydown", onKey);
    }, []);
    // Show the backend's messages as toasts, then tell it they've been seen.
    const message = state?.message;
    useEffect(() => {
        if (!message)
            return;
        toast.danger(problemText(message), { timeout: 6000 });
        send({ type: "dismissMessage" });
    }, [message, send]);
    const backdrop = useMemo(() => windowBackground(backgroundId, photo, mode), [backgroundId, photo, mode]);
    const blur = state?.appearance.photoBlur ?? 0;
    return (_jsxs("div", { className: "app-backdrop", style: { background: onPhoto ? "transparent" : backdrop }, "data-photo": onPhoto || undefined, children: [onPhoto && (_jsx("div", { className: "photo-layer", "aria-hidden": "true", style: { background: backdrop, filter: blur ? `blur(${blur}px)` : undefined } })), _jsx(Toast.Provider, { placement: "bottom" }), _jsxs(Tabs, { className: "app-shell", "data-bar": showBar ? "" : undefined, selectedKey: view, onSelectionChange: (key) => setView(key === "music" ? "music" : "devices"), children: [_jsxs("header", { className: "app-header", children: [_jsxs("div", { className: "flex items-center gap-3", children: [_jsx(LogoMark, { size: 30 }), _jsxs("div", { children: [_jsx("h1", { className: "text-[28px] font-semibold leading-tight tracking-tight", children: strings.appName }), _jsx("p", { className: "text-[13px] text-[var(--muted)]", children: view === "music" ? strings.music.subtitle : strings.devicesSubtitle })] })] }), _jsxs(Tabs.List, { "aria-label": strings.tabs.label, className: "app-tabs", children: [_jsxs(Tabs.Tab, { id: "devices", children: [strings.tabs.devices, _jsx(Tabs.Indicator, {})] }), _jsxs(Tabs.Tab, { id: "music", children: [strings.tabs.music, _jsx(Tabs.Indicator, {})] })] }), _jsxs("div", { className: "flex items-center gap-3", children: [state?.discovering && (_jsxs("span", { className: "flex items-center gap-2 text-[13px] text-[var(--muted)]", children: [_jsx(Spinner, { size: "sm", color: "accent" }), strings.searching] })), state?.demo && (_jsx(Chip, { size: "sm", variant: "soft", color: "accent", children: strings.demoBadge })), _jsxs(Button, { variant: "tertiary", "aria-label": streaming > 0 ? `${strings.audio.open}, ${strings.audio.badge(streaming)}` : strings.audio.open, onPress: () => setAudioOpen(true), className: "command-button", "data-streaming": streaming > 0 || undefined, children: [_jsx(WavesIcon, { size: 18 }), _jsx("span", { children: strings.audio.open }), streaming > 0 && (_jsx(Chip, { size: "sm", variant: "soft", color: "success", children: strings.audio.badge(streaming) }))] }), _jsxs(Button, { variant: "tertiary", "aria-label": strings.commands.open, "aria-keyshortcuts": "Control+K", onPress: () => setCommandsOpen(true), className: "command-button", children: [_jsx(SearchIcon, { size: 18 }), _jsx("span", { children: strings.commands.open }), _jsx(Kbd, { className: "command-kbd", children: strings.commands.shortcut })] }), _jsx(Button, { isIconOnly: true, variant: "tertiary", "aria-label": strings.settings, onPress: () => setSettingsOpen(true), children: _jsx(GearIcon, { size: 20 }) })] })] }), _jsxs(Tabs.Panel, { id: "devices", children: [showNetworkNote && _jsx(NetworkNote, { send: send, onDismiss: () => setNetworkDismissed(true) }), update && _jsx(UpdateNote, { version: update.version, send: send, onDismiss: () => setUpdateDismissed(true) }), state && state.devices.length > 0 ? (_jsx("ul", { className: "device-grid", "aria-label": strings.devicesTitle, children: state.devices.map((device) => (_jsx("li", { children: _jsx(DeviceCard, { device: device, onActivate: () => send({ type: "activate", id: device.id }), onAudio: () => send({
                                            type: "deviceAudio",
                                            id: device.id,
                                            on: device.audio !== "on" && device.audio !== "starting",
                                        }), onVideo: () => {
                                            send({ type: "openDevice", id: device.id });
                                            if (device.needsPairing) {
                                                pairingWasOpen.current = false;
                                                setVideoAfterPairing(device.id);
                                            }
                                            else {
                                                setSendId(device.id);
                                            }
                                        }, onRemote: () => {
                                            send({ type: "openDevice", id: device.id });
                                            setRemoteId(device.id);
                                        } }) }, device.id))) })) : (_jsx("div", { className: "empty-state glass", children: state === null || state.discovering ? (_jsxs(_Fragment, { children: [_jsx(Spinner, { color: "accent" }), _jsx("p", { className: "text-[var(--muted)]", children: strings.searching })] })) : (_jsxs(_Fragment, { children: [_jsx("h2", { className: "text-[17px] font-semibold", children: strings.emptyTitle }), _jsx("p", { className: "max-w-sm text-center text-[var(--muted)]", children: strings.emptyBody })] })) }))] }), _jsx(Tabs.Panel, { id: "music", children: state === null ? (_jsx("div", { className: "empty-state glass", children: _jsx(Spinner, { color: "accent" }) })) : (_jsx(MusicTab, { state: state, send: send, onOpenAudio: () => setAudioOpen(true), onOpenConnections: () => setSpotifyOpen(true) })) })] }), showBar && _jsx(NowPlayingBar, { music: music, send: send, onOpen: () => setView("music") }), status === "lost" && (_jsxs("div", { className: "link-lost", role: "status", children: [_jsx(Spinner, { size: "sm", color: "accent" }), strings.reconnecting] })), state && _jsx(PairingSheet, { pairing: state.pairing, send: send }), state && (_jsx(CommandBar, { isOpen: commandsOpen, onClose: () => setCommandsOpen(false), commands: state.commands, send: send })), _jsx(RemoteSheet, { device: remoteDevice, music: music, output: state?.audio.outputs.find((o) => o.id === remoteId && o.kind === "airplay") ?? null, onClose: () => setRemoteId(null), send: send }), state && (_jsx(OnboardingSheet, { isOpen: guideOpen && !audioOpen && state.pairing.state === "closed", state: state, onClose: closeGuide, onOpenAudio: () => setAudioOpen(true), onPair: (id) => send({ type: "pair", id }) })), state && (_jsx(AudioSheet, { isOpen: audioOpen, onClose: () => setAudioOpen(false), audio: state.audio, untrusted: state.network.untrusted, send: send })), _jsx(SendSheet, { device: sendDevice, canPickFiles: state?.audio.canPickFiles ?? false, picking: state?.audio.picking ?? false, onClose: () => setSendId(null), send: send }), state && (_jsx(SettingsSheet, { isOpen: settingsOpen, onClose: () => setSettingsOpen(false), onOpenGuide: () => {
                    setSettingsOpen(false);
                    setGuideOpen(true);
                }, onOpenAdvanced: () => {
                    setSettingsOpen(false);
                    setAdvancedOpen(true);
                }, onOpenSpotify: () => {
                    setSettingsOpen(false);
                    setSpotifyOpen(true);
                }, appearance: state.appearance, spotify: state.spotify, mode: mode, send: send })), state && (_jsx(SpotifySheet, { isOpen: spotifyOpen, onClose: () => setSpotifyOpen(false), onBack: () => {
                    setSpotifyOpen(false);
                    setSettingsOpen(true);
                }, spotify: state.spotify, send: send })), state && (_jsx(AdvancedSheet, { isOpen: advancedOpen, onClose: () => setAdvancedOpen(false), onBack: () => {
                    setAdvancedOpen(false);
                    setSettingsOpen(true);
                }, appearance: state.appearance, audio: state.audio, home: state.home, reporting: state.reporting, send: send }))] }));
}
