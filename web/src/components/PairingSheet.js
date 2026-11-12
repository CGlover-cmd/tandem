import { Fragment as _Fragment, jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { Button, InputOTP, Label, Modal, REGEXP_ONLY_DIGITS, Spinner } from "@heroui/react";
import { useEffect, useState } from "react";
import { CheckIcon, TvIcon, WarningIcon } from "../icons";
import { problemText, strings } from "../strings";
export function PairingSheet({ pairing, send }) {
    const [pin, setPin] = useState("");
    const { state, deviceName, error, step, steps } = pairing;
    const open = state !== "closed";
    // Start each attempt with an empty PIN, and clear a wrong one so the user can retype.
    useEffect(() => {
        if (state === "starting" || (state === "enterPin" && error?.code === "wrongPin"))
            setPin("");
    }, [state, error]);
    useEffect(() => setPin(""), [step]);
    const submit = (value) => {
        if (value.length === 4)
            send({ type: "submitPin", pin: value });
    };
    const dismiss = () => send({ type: state === "done" || state === "failed" ? "closePairing" : "cancelPairing" });
    return (_jsx(Modal.Backdrop, { isOpen: open, onOpenChange: (isOpen) => {
            if (!isOpen)
                dismiss();
        }, variant: "blur", isDismissable: state !== "checking", children: _jsx(Modal.Container, { placement: "center", size: "sm", children: _jsxs(Modal.Dialog, { className: "sheet", "aria-label": strings.pairing.title(deviceName), children: [_jsxs(Modal.Header, { className: "items-center text-center", children: [_jsx("span", { className: "sheet-icon", "data-tone": state === "failed" ? "danger" : undefined, children: state === "done" ? (_jsx(CheckIcon, { size: 28 })) : state === "failed" ? (_jsx(WarningIcon, { size: 28 })) : (_jsx(TvIcon, { size: 28 })) }), _jsx(Modal.Heading, { className: "text-[20px] font-semibold", children: state === "failed"
                                    ? strings.pairing.failedTitle
                                    : state === "done"
                                        ? strings.pairing.doneTitle
                                        : strings.pairing.title(deviceName) })] }), _jsxs(Modal.Body, { className: "flex flex-col items-center gap-4 text-center", children: [state === "starting" && (_jsxs("p", { className: "flex items-center gap-3 text-[var(--muted)]", children: [_jsx(Spinner, { size: "sm", color: "accent" }), strings.pairing.starting(deviceName)] })), (state === "enterPin" || state === "checking") && (_jsxs(_Fragment, { children: [steps > 1 && (_jsx("p", { className: "text-[12px] font-semibold uppercase tracking-wide text-[var(--tandem-accent-text)]", children: strings.pairing.stepOf(step, steps) })), _jsx("p", { className: "text-[var(--muted)]", children: step > 1 ? strings.pairing.nextPin : strings.pairing.enterPin }), _jsxs("div", { className: "flex flex-col items-center gap-2", children: [_jsx(Label, { className: "sr-only", children: strings.pairing.pinLabel }), _jsx(InputOTP, { "aria-label": strings.pairing.pinLabel, maxLength: 4, pattern: REGEXP_ONLY_DIGITS, value: pin, onChange: setPin, onComplete: submit, isDisabled: state === "checking", autoFocus: true, children: _jsxs(InputOTP.Group, { children: [_jsx(InputOTP.Slot, { index: 0 }), _jsx(InputOTP.Slot, { index: 1 }), _jsx(InputOTP.Slot, { index: 2 }), _jsx(InputOTP.Slot, { index: 3 })] }) })] }), _jsx("p", { className: "min-h-5 text-[13px]", role: "alert", children: state === "checking" ? (_jsxs("span", { className: "flex items-center gap-2 text-[var(--muted)]", children: [_jsx(Spinner, { size: "sm", color: "accent" }), strings.pairing.checking] })) : error ? (_jsx("span", { className: "text-[var(--danger)]", children: problemText(error) })) : null })] })), state === "done" && _jsx("p", { className: "text-[var(--muted)]", children: strings.pairing.done(deviceName) }), state === "failed" && error && (_jsx("p", { className: "text-[var(--muted)]", role: "alert", children: problemText(error) }))] }), _jsx(Modal.Footer, { className: "justify-center", children: state === "done" ? (_jsx(Button, { variant: "primary", onPress: () => send({ type: "closePairing" }), autoFocus: true, children: strings.pairing.close })) : state === "failed" ? (_jsxs(_Fragment, { children: [_jsx(Button, { variant: "secondary", onPress: () => send({ type: "closePairing" }), children: strings.pairing.close }), _jsx(Button, { variant: "primary", onPress: () => {
                                        send({ type: "closePairing" });
                                        send({ type: "pair", id: pairing.deviceId });
                                    }, children: strings.pairing.tryAgain })] })) : (_jsxs(_Fragment, { children: [_jsx(Button, { variant: "secondary", onPress: () => send({ type: "cancelPairing" }), children: strings.pairing.cancel }), _jsx(Button, { variant: "primary", isDisabled: state !== "enterPin" || pin.length !== 4, onPress: () => submit(pin), children: strings.pairing.pair })] })) })] }) }) }));
}
