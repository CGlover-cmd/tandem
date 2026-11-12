import { Fragment as _Fragment, jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { Button, Modal, Separator, Spinner, ToggleButton, ToggleButtonGroup } from "@heroui/react";
import { useRef, useState } from "react";
import { Label, Radio, RadioGroup } from "react-aria-components";
import { CheckIcon, ChevronIcon } from "../icons";
import { uploadPhoto } from "../photo";
import { strings } from "../strings";
import { backgroundCss, backgrounds, PHOTO_BACKGROUND, windowBackground } from "../theme";
import { ConnectionsSection } from "./Connections";
import { LiveSlider } from "./LiveSlider";
const THEMES = [
    { id: "system", label: strings.settingsSheet.themeSystem },
    { id: "light", label: strings.settingsSheet.themeLight },
    { id: "dark", label: strings.settingsSheet.themeDark },
];
function Swatch({ id, label, css }) {
    return (_jsx(Radio, { value: id, "aria-label": label, className: "swatch group flex flex-col items-center gap-1.5 outline-none", children: ({ isSelected }) => (_jsxs(_Fragment, { children: [_jsx("span", { className: "swatch-chip", "data-selected": isSelected || undefined, style: { background: css }, children: isSelected && _jsx(CheckIcon, { size: 18, className: "swatch-check" }) }), _jsx("span", { className: "text-[12px] text-[var(--muted)]", children: label })] })) }));
}
function PresetSwatch({ background, mode }) {
    return _jsx(Swatch, { id: background.id, label: background.label, css: backgroundCss(background, mode) });
}
/** "Choose a photo…": the picked picture is shrunk and sent to Tandem, which then shows it. */
function PhotoPicker({ hasPhoto }) {
    const input = useRef(null);
    const [busy, setBusy] = useState(false);
    const [failed, setFailed] = useState(false);
    const words = strings.settingsSheet;
    return (_jsxs("div", { className: "flex flex-col gap-1", children: [_jsxs("div", { className: "flex items-center gap-3", children: [_jsx(Button, { size: "sm", variant: "secondary", isDisabled: busy, onPress: () => input.current?.click(), children: hasPhoto ? words.changePhoto : words.choosePhoto }), busy && _jsx(Spinner, { size: "sm", color: "accent" })] }), _jsx("input", { ref: input, type: "file", accept: "image/jpeg,image/png,image/webp", className: "sr-only", tabIndex: -1, "aria-hidden": "true", onChange: (event) => {
                    const file = event.target.files?.[0];
                    event.target.value = "";
                    if (!file)
                        return;
                    setBusy(true);
                    setFailed(false);
                    void uploadPhoto(file).then((ok) => {
                        setBusy(false);
                        setFailed(!ok);
                    });
                } }), failed && (_jsx("p", { className: "text-[12px] text-[var(--danger)]", role: "status", children: words.photoFailed }))] }));
}
export function SettingsSheet({ isOpen, onClose, onOpenGuide, onOpenAdvanced, onOpenSpotify, appearance, spotify, mode, send }) {
    const neutral = backgrounds.filter((b) => b.group === "neutral");
    const gradients = backgrounds.filter((b) => b.group === "gradient");
    const words = strings.settingsSheet;
    return (_jsx(Modal.Backdrop, { isOpen: isOpen, onOpenChange: (open) => {
            if (!open)
                onClose();
        }, variant: "blur", children: _jsx(Modal.Container, { placement: "center", size: "md", scroll: "inside", children: _jsxs(Modal.Dialog, { className: "sheet", children: [_jsx(Modal.CloseTrigger, {}), _jsx(Modal.Header, { children: _jsx(Modal.Heading, { className: "text-[20px] font-semibold", children: words.title }) }), _jsxs(Modal.Body, { className: "flex flex-col gap-5", children: [_jsxs("section", { className: "flex flex-col gap-3", "aria-labelledby": "theme-label", children: [_jsx("h3", { id: "theme-label", className: "section-title", children: words.theme }), _jsx(ToggleButtonGroup, { "aria-labelledby": "theme-label", selectionMode: "single", disallowEmptySelection: true, selectedKeys: new Set([appearance.theme]), onSelectionChange: (keys) => {
                                            const [theme] = [...keys];
                                            if (typeof theme === "string")
                                                send({ type: "setAppearance", theme: theme });
                                        }, fullWidth: true, children: THEMES.map((theme) => (_jsx(ToggleButton, { id: theme.id, children: theme.label }, theme.id))) })] }), _jsx(Separator, {}), _jsxs("section", { className: "flex flex-col gap-3", children: [_jsxs(RadioGroup, { value: appearance.background, onChange: (background) => send({ type: "setAppearance", background }), className: "flex flex-col gap-3", children: [_jsx(Label, { className: "section-title", children: words.background }), _jsx("p", { className: "text-[12px] text-[var(--muted)]", children: words.gradients }), _jsx("div", { className: "flex flex-wrap gap-4", children: gradients.map((b) => (_jsx(PresetSwatch, { background: b, mode: mode }, b.id))) }), _jsx("p", { className: "text-[12px] text-[var(--muted)]", children: words.neutral }), _jsx("div", { className: "flex flex-wrap gap-4", children: neutral.map((b) => (_jsx(PresetSwatch, { background: b, mode: mode }, b.id))) }), _jsx("p", { className: "text-[12px] text-[var(--muted)]", children: words.photo }), appearance.photo !== null && (_jsx("div", { className: "flex flex-wrap gap-4", children: _jsx(Swatch, { id: PHOTO_BACKGROUND, label: words.photo, css: windowBackground(PHOTO_BACKGROUND, appearance.photo, mode) }) }))] }), _jsx(PhotoPicker, { hasPhoto: appearance.photo !== null }), appearance.photo !== null && appearance.background === PHOTO_BACKGROUND && (_jsxs("div", { className: "flex items-center gap-3", children: [_jsx("span", { className: "w-12 text-[12px] text-[var(--muted)]", children: words.photoBlur }), _jsx(LiveSlider, { label: words.photoBlur, value: appearance.photoBlur, min: 0, max: 24, step: 1, onCommit: (photoBlur) => send({ type: "setAppearance", photoBlur }) })] }))] }), _jsx(Separator, {}), _jsx(ConnectionsSection, { spotify: spotify, onOpen: onOpenSpotify }), _jsx(Separator, {}), _jsxs("nav", { className: "flex flex-col gap-1", "aria-label": words.more, children: [_jsxs(Button, { variant: "tertiary", fullWidth: true, className: "settings-link", onPress: onOpenGuide, children: [_jsx("span", { children: strings.onboarding.reopen }), _jsx(ChevronIcon, { direction: "right", size: 16 })] }), _jsxs(Button, { variant: "tertiary", fullWidth: true, className: "settings-link", onPress: onOpenAdvanced, children: [_jsx("span", { children: words.advanced }), _jsx(ChevronIcon, { direction: "right", size: 16 })] })] })] })] }) }) }));
}
