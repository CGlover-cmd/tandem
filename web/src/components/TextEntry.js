import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { Button, Input, Label, TextField } from "@heroui/react";
import { useEffect, useRef, useState } from "react";
import { MAX_TEXT, TYPING_PAUSE_MS } from "../launcher";
import { strings } from "../strings";
/** Types into the text field on the TV. Each change replaces the TV's text, a moment after
 *  the last keystroke. The text may be a search or a password: it is never logged. */
export function TextEntry({ deviceId, asking, send, onClose }) {
    const [text, setText] = useState("");
    const timer = useRef(null);
    const flush = useRef(null);
    const cancelPending = () => {
        if (timer.current !== null) {
            window.clearTimeout(timer.current);
            timer.current = null;
        }
        flush.current = null;
    };
    const sendNow = (value) => {
        cancelPending();
        send({ type: "setText", id: deviceId, text: value });
    };
    const sendSoon = (value) => {
        cancelPending();
        const deliver = () => {
            timer.current = null;
            flush.current = null;
            send({ type: "setText", id: deviceId, text: value });
        };
        flush.current = deliver;
        timer.current = window.setTimeout(deliver, TYPING_PAUSE_MS);
    };
    // A new keyboard on the TV starts empty.
    useEffect(() => {
        if (asking)
            setText("");
    }, [asking]);
    // Closing right after typing still sends the last keystrokes.
    useEffect(() => () => {
        if (timer.current !== null)
            window.clearTimeout(timer.current);
        flush.current?.();
    }, []);
    return (_jsxs("section", { className: "text-entry glass", "aria-label": strings.typing.label, children: [_jsxs(TextField, { value: text, maxLength: MAX_TEXT, onChange: (value) => {
                    setText(value);
                    sendSoon(value);
                }, onKeyDown: (event) => {
                    if (event.key === "Enter")
                        sendNow(text);
                    if (event.key === "Escape")
                        onClose();
                }, autoFocus: true, fullWidth: true, children: [_jsx(Label, { className: "text-[13px] font-medium", children: asking ? strings.typing.asking : strings.typing.label }), _jsxs("div", { className: "flex items-center gap-2", children: [_jsx(Input, { className: "flex-1", placeholder: strings.typing.placeholder, autoComplete: "off", spellCheck: false }), _jsx(Button, { variant: "ghost", size: "sm", isDisabled: text === "", onPress: () => {
                                    setText("");
                                    sendNow("");
                                }, children: strings.typing.clear })] })] }), _jsx("p", { className: "text-[11px] text-[var(--muted)]", children: asking ? strings.typing.hint : strings.typing.selectFirst })] }));
}
