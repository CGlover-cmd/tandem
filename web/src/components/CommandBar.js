import { Fragment as _Fragment, jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { Kbd, ListBox, Modal, SearchField, Spinner } from "@heroui/react";
import { useEffect, useId, useRef, useState } from "react";
import { outcomeText, outcomeTone, runsWhenPicked, suggestionsTitle, visibleOutcome } from "../commands";
import { CheckIcon, WarningIcon } from "../icons";
import { strings } from "../strings";
const words = strings.commands;
/** Typed commands (Phase 10a): "pause", "volume 30 on the loft", "open Music on the TV".
 * Enter runs what's typed; the line under the box says what that will do as you type. */
export function CommandBar({ isOpen, onClose, commands, send }) {
    const [text, setText] = useState("");
    const input = useRef(null);
    const list = useRef(null);
    const statusId = useId();
    // Each time the bar opens, start empty; the empty preview brings the examples.
    useEffect(() => {
        if (!isOpen)
            return;
        setText("");
        send({ type: "previewCommand", text: "" });
    }, [isOpen, send]);
    const edit = (value) => {
        setText(value);
        send({ type: "previewCommand", text: value });
    };
    const run = (value) => {
        if (value.trim())
            send({ type: "runCommand", text: value });
    };
    const close = () => {
        send({ type: "clearCommand" });
        onClose();
    };
    const shown = visibleOutcome(commands, text);
    const running = commands.running && commands.text === text;
    const title = shown ? suggestionsTitle(shown) : null;
    const tone = shown ? outcomeTone(shown) : "neutral";
    return (_jsx(Modal.Backdrop, { isOpen: isOpen, onOpenChange: (open) => {
            if (!open)
                close();
        }, variant: "blur", children: _jsx(Modal.Container, { placement: "top", size: "lg", children: _jsxs(Modal.Dialog, { className: "sheet command-bar", "aria-label": words.title, children: [_jsxs(Modal.Body, { className: "flex flex-col gap-3 pt-5", children: [_jsx(SearchField, { "aria-label": words.label, "aria-describedby": statusId, value: text, onChange: edit, onSubmit: run, autoFocus: true, fullWidth: true, children: _jsxs(SearchField.Group, { className: "command-input", children: [_jsx(SearchField.SearchIcon, {}), _jsx(SearchField.Input, { ref: input, placeholder: words.placeholder, autoComplete: "off", spellCheck: false, onKeyDown: (event) => {
                                                // Down arrow moves into the suggestions, like a menu.
                                                if (event.key === "ArrowDown" && list.current) {
                                                    const first = list.current.querySelector("[role='option']");
                                                    if (first) {
                                                        event.preventDefault();
                                                        first.focus();
                                                    }
                                                }
                                            } }), _jsx(SearchField.ClearButton, {})] }) }), _jsx("p", { id: statusId, className: "command-status", "data-tone": tone, role: "status", "aria-live": "polite", children: running ? (_jsxs(_Fragment, { children: [_jsx(Spinner, { size: "sm", color: "accent" }), words.running] })) : shown ? (_jsxs(_Fragment, { children: [shown.status === "done" && _jsx(CheckIcon, { size: 16 }), tone === "warning" || tone === "danger" ? _jsx(WarningIcon, { size: 16 }) : null, _jsx("span", { children: outcomeText(shown) }), shown.status === "ready" && _jsx(Kbd, { className: "ml-auto", children: "↵" })] })) : (_jsx("span", { className: "text-[var(--muted)]", children: words.hint })) }), shown && title && (_jsxs("section", { className: "flex flex-col gap-1", "aria-label": title, children: [_jsx("h3", { className: "section-title px-1", children: title }), _jsx("div", { ref: list, children: _jsx(ListBox, { "aria-label": title, selectionMode: "none", onAction: (key) => {
                                                const picked = String(key);
                                                setText(picked);
                                                if (runsWhenPicked(shown)) {
                                                    send({ type: "previewCommand", text: picked });
                                                    run(picked);
                                                }
                                                else {
                                                    edit(picked);
                                                }
                                                input.current?.focus();
                                            }, className: "command-suggestions", children: shown.suggestions.map((suggestion) => (_jsx(ListBox.Item, { id: suggestion, textValue: suggestion, children: suggestion }, suggestion))) }) })] }))] }), _jsxs(Modal.Footer, { className: "command-footer", children: [_jsxs("span", { children: [_jsx(Kbd, { children: "↵" }), " ", strings.commands.runKey] }), _jsxs("span", { children: [_jsx(Kbd, { children: "Esc" }), " ", strings.commands.closeKey] })] })] }) }) }));
}
