import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { Button, Modal, Spinner } from "@heroui/react";
import { CheckIcon } from "../icons";
import { allDone, onboardingSteps } from "../onboarding";
import { strings } from "../strings";
function Mark({ step, index }) {
    if (step.state === "done") {
        return (_jsx("span", { className: "step-mark", "data-done": "true", "aria-hidden": "true", children: _jsx(CheckIcon, { size: 16 }) }));
    }
    if (step.state === "waiting") {
        return (_jsx("span", { className: "step-mark", "aria-hidden": "true", children: _jsx(Spinner, { size: "sm", color: "accent" }) }));
    }
    return (_jsx("span", { className: "step-mark", "aria-hidden": "true", children: index + 1 }));
}
export function OnboardingSheet({ isOpen, state, onClose, onOpenAudio, onPair }) {
    const steps = onboardingSteps(state);
    const words = strings.onboarding;
    return (_jsx(Modal.Backdrop, { isOpen: isOpen, onOpenChange: (open) => {
            if (!open)
                onClose();
        }, variant: "blur", children: _jsx(Modal.Container, { placement: "center", size: "md", children: _jsxs(Modal.Dialog, { className: "sheet", children: [_jsxs(Modal.Header, { className: "flex flex-col items-start gap-1", children: [_jsx(Modal.Heading, { className: "text-[20px] font-semibold", children: words.title }), _jsx("p", { className: "text-[13px] text-[var(--muted)]", children: words.subtitle })] }), _jsxs(Modal.Body, { className: "flex flex-col gap-3", children: [_jsx("ol", { className: "flex flex-col gap-2", "aria-label": words.title, children: steps.map((step, index) => (_jsxs("li", { className: "glass onboarding-step flex items-start gap-3", children: [_jsx(Mark, { step: step, index: index }), _jsxs("div", { className: "min-w-0 flex-1", children: [_jsxs("p", { className: "text-[15px] font-semibold", children: [step.title, _jsx("span", { className: "sr-only", children: step.state === "done" ? `, ${words.done}` : "" })] }), _jsx("p", { className: "text-[13px] text-[var(--muted)]", children: step.detail })] }), step.id === "pair" && step.state === "todo" && step.deviceId && (_jsx(Button, { size: "sm", variant: "primary", onPress: () => onPair(step.deviceId), children: words.pair })), step.id === "play" && step.state !== "done" && (_jsx(Button, { size: "sm", variant: "secondary", onPress: onOpenAudio, children: words.openAudio }))] }, step.id))) }), _jsxs("section", { className: "flex flex-col gap-1", "aria-labelledby": "help-label", children: [_jsx("h3", { id: "help-label", className: "section-title", children: words.helpTitle }), _jsx("ul", { className: "flex list-disc flex-col gap-1 pl-5 text-[12px] text-[var(--muted)]", children: words.tips.map((tip) => (_jsx("li", { children: tip }, tip))) })] })] }), _jsx(Modal.Footer, { children: _jsx(Button, { variant: allDone(steps) ? "primary" : "tertiary", onPress: onClose, children: allDone(steps) ? words.finish : words.later }) })] }) }) }));
}
