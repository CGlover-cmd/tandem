import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { Button, Input, Label, Modal, Spinner, TextField } from "@heroui/react";
import { useEffect, useState } from "react";
import { canSend, isLink, sendText } from "../audio";
import { SendIcon } from "../icons";
import { strings } from "../strings";
export function SendSheet({ device, canPickFiles, picking, onClose, send }) {
    const [link, setLink] = useState("");
    useEffect(() => setLink(""), [device?.id]);
    const open = device !== null;
    const ready = device !== null && canSend(device);
    const current = device?.send ?? null;
    const active = current !== null && (current.state === "starting" || current.state === "playing");
    const sendLink = () => {
        if (device && isLink(link)) {
            send({ type: "sendMedia", id: device.id, location: link.trim() });
        }
    };
    return (_jsx(Modal.Backdrop, { isOpen: open, onOpenChange: (isOpen) => {
            if (!isOpen)
                onClose();
        }, variant: "blur", children: _jsx(Modal.Container, { placement: "center", size: "md", children: _jsxs(Modal.Dialog, { className: "sheet", children: [_jsx(Modal.CloseTrigger, {}), _jsxs(Modal.Header, { className: "flex flex-col items-start gap-1", children: [_jsx(Modal.Heading, { className: "text-[20px] font-semibold", children: device ? strings.sendSheet.title(device.name) : "" }), _jsx("p", { className: "text-[13px] text-[var(--muted)]", children: strings.sendSheet.subtitle })] }), _jsxs(Modal.Body, { className: "flex flex-col gap-4", children: [!ready && _jsx("p", { className: "text-[13px] text-[var(--warning)]", children: strings.sendSheet.connectFirst }), current && (_jsxs("div", { className: "glass send-status flex items-center gap-3", role: "status", children: [current.state === "starting" ? (_jsx(Spinner, { size: "sm", color: "accent" })) : (_jsx(SendIcon, { size: 18, className: "text-[var(--muted)]" })), _jsx("span", { className: "min-w-0 flex-1 truncate text-[14px]", children: sendText(current) }), active && device && (_jsx(Button, { size: "sm", variant: "secondary", onPress: () => send({ type: "stopMedia", id: device.id }), children: strings.sendSheet.stop }))] })), canPickFiles && (_jsxs(Button, { variant: "primary", isDisabled: !ready || picking, onPress: () => device && send({ type: "pickMedia", id: device.id }), children: [picking ? _jsx(Spinner, { size: "sm" }) : _jsx(SendIcon, { size: 18 }), picking ? strings.sendSheet.choosing : strings.sendSheet.chooseFile] })), _jsxs(TextField, { value: link, onChange: setLink, onKeyDown: (event) => {
                                    if (event.key === "Enter")
                                        sendLink();
                                }, isDisabled: !ready, fullWidth: true, children: [_jsx(Label, { className: "text-[13px] font-medium", children: strings.sendSheet.link }), _jsxs("div", { className: "flex items-center gap-2", children: [_jsx(Input, { className: "flex-1", type: "url", placeholder: strings.sendSheet.linkPlaceholder, autoComplete: "off", spellCheck: false }), _jsx(Button, { variant: "secondary", isDisabled: !ready || !isLink(link), onPress: sendLink, children: strings.sendSheet.sendLink })] })] }), _jsx("p", { className: "text-[12px] text-[var(--muted)]", children: strings.sendSheet.formats })] })] }) }) }));
}
