import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { Button, Modal, Spinner, Switch } from "@heroui/react";
import { directSwitch, groupOutputs, masterChanges, masterVolume, outputDirect, outputLive, outputVolume, problemText, } from "../audio";
import { DeviceIcon, HeadphonesIcon, VolumeIcon } from "../icons";
import { strings } from "../strings";
import { GroupsSection } from "./GroupsSection";
import { LiveSlider } from "./LiveSlider";
function OutputRow({ output, untrusted, send, }) {
    const problem = problemText(output, untrusted);
    const direct = outputDirect(output);
    const live = outputLive(output);
    const pcSwitch = direct ? directSwitch(output) : null;
    const on = live || (pcSwitch?.on ?? false);
    const note = output.state === "muted"
        ? strings.audio.mutedNote
        : output.state === "ahead"
            ? strings.audio.aheadNote
            : direct
                ? strings.audio.directNote
                : null;
    const busy = output.state === "starting" || output.state === "waiting";
    const status = output.needsPairing ? strings.audio.pairFirst : strings.audio.state[output.state];
    return (_jsxs("li", { className: "output-row glass", "data-on": on || undefined, "aria-busy": busy || undefined, children: [_jsxs("div", { className: "flex items-center gap-3", children: [_jsx("span", { className: "device-icon", "data-connected": on || undefined, children: output.kind === "pc" ? (_jsx(HeadphonesIcon, { size: 22 })) : (_jsx(DeviceIcon, { kind: output.deviceKind ?? "other", size: 22 })) }), _jsxs("div", { className: "min-w-0 flex-1", children: [_jsx("p", { className: "truncate text-[15px] font-semibold", children: output.name }), _jsx("p", { className: "flex items-center gap-2 text-[12px] text-[var(--muted)]", "aria-live": "polite", children: status })] }), busy && _jsx(Spinner, { size: "sm", color: "accent", "aria-hidden": "true" }), _jsx(Switch, { isSelected: on, isDisabled: output.needsPairing || (pcSwitch !== null && !pcSwitch.enabled), onChange: (turnOn) => send({ type: "setOutput", id: output.id, on: turnOn }), children: _jsxs(Switch.Content, { children: [_jsx(Switch.Control, { children: _jsx(Switch.Thumb, {}) }), _jsx("span", { className: "sr-only", children: direct ? strings.audio.turnPcOn(output.name) : strings.audio.turnOn(output.name) })] }) })] }), note && _jsx("p", { className: "mt-2 text-[12px] text-[var(--muted)]", children: note }), problem && (_jsxs("div", { className: "mt-2 flex flex-col items-start gap-2", role: "status", children: [_jsx("p", { className: "text-[12px] text-[var(--danger)]", children: problem }), untrusted && output.kind === "airplay" && (_jsx(Button, { size: "sm", variant: "secondary", onPress: () => send({ type: "openNetworkSettings" }), children: strings.audio.trustNetwork }))] })), live && (_jsx("div", { className: "mt-3 flex flex-col gap-2", children: _jsxs("div", { className: "flex items-center gap-3", children: [_jsx(VolumeIcon, { level: 1, size: 16, className: "text-[var(--muted)]" }), _jsx(LiveSlider, { label: strings.audio.volumeOf(output.name), value: outputVolume(output), min: 0, max: 100, step: 1, onCommit: (level) => send({ type: "setOutputVolume", id: output.id, level }) })] }) }))] }));
}
export function AudioSheet({ isOpen, onClose, audio, untrusted, send }) {
    const { airplay, pc } = groupOutputs(audio.outputs);
    const master = masterVolume(audio.outputs);
    return (_jsx(Modal.Backdrop, { isOpen: isOpen, onOpenChange: (open) => {
            if (!open)
                onClose();
        }, variant: "blur", children: _jsx(Modal.Container, { placement: "center", size: "lg", scroll: "inside", children: _jsxs(Modal.Dialog, { className: "sheet", children: [_jsx(Modal.CloseTrigger, {}), _jsxs(Modal.Header, { className: "flex flex-col items-start gap-1", children: [_jsx(Modal.Heading, { className: "text-[20px] font-semibold", children: strings.audio.title }), _jsx("p", { className: "text-[13px] text-[var(--muted)]", children: strings.audio.subtitle })] }), _jsxs(Modal.Body, { className: "flex flex-col gap-5", children: [master !== null && (_jsxs("section", { className: "glass output-row flex items-center gap-3", "aria-label": strings.audio.master, children: [_jsx("span", { className: "w-24 text-[13px] font-semibold", children: strings.audio.master }), _jsx(VolumeIcon, { level: 1, size: 16, className: "text-[var(--muted)]" }), _jsx(LiveSlider, { label: strings.audio.masterOf, value: master, min: 0, max: 100, step: 1, onCommit: (level) => {
                                            for (const change of masterChanges(audio.outputs, level)) {
                                                send({ type: "setOutputVolume", id: change.id, level: change.level });
                                            }
                                        } })] })), _jsx(GroupsSection, { groups: audio.groups, outputs: audio.outputs, send: send }), _jsxs("section", { className: "flex flex-col gap-2", "aria-labelledby": "airplay-label", children: [_jsx("h3", { id: "airplay-label", className: "section-title", children: strings.audio.airplay }), airplay.length === 0 ? (_jsx("p", { className: "text-[13px] text-[var(--muted)]", children: strings.audio.noOutputs })) : (_jsx("ul", { className: "flex flex-col gap-2", "aria-labelledby": "airplay-label", children: airplay.map((output) => (_jsx(OutputRow, { output: output, untrusted: untrusted, send: send }, output.id))) })), _jsx("p", { className: "text-[12px] text-[var(--muted)]", children: strings.audio.delayHint })] }), _jsxs("section", { className: "flex flex-col gap-2", "aria-labelledby": "pc-label", children: [_jsx("h3", { id: "pc-label", className: "section-title", children: strings.audio.pc }), pc.length === 0 ? (_jsx("p", { className: "text-[13px] text-[var(--muted)]", children: strings.audio.noPcOutputs })) : (_jsx("ul", { className: "flex flex-col gap-2", "aria-labelledby": "pc-label", children: pc.map((output) => (_jsx(OutputRow, { output: output, untrusted: untrusted, send: send }, output.id))) })), audio.pcOutputsHidden && (_jsx("p", { className: "text-[12px] text-[var(--muted)]", children: strings.audio.echoNote }))] })] }), _jsx(Modal.Footer, { children: _jsx(Button, { variant: "secondary", isDisabled: audio.streaming === 0, onPress: () => send({ type: "allOutputsOff" }), children: strings.audio.allOff }) })] }) }) }));
}
