import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { Button, Input, Label, Spinner, Switch, TextField } from "@heroui/react";
import { useState } from "react";
import { outputLive } from "../audio";
import { strings } from "../strings";
/** Saved speaker groups, each with one switch, and "save the playing speakers as a group". */
export function GroupsSection({ groups, outputs, send, }) {
    const words = strings.groups;
    const playing = outputs.filter((o) => outputLive(o) && o.state !== "direct");
    const [naming, setNaming] = useState(false);
    const [name, setName] = useState("");
    const names = new Map(outputs.map((o) => [o.id, o.name]));
    const playingIds = new Set(playing.map((o) => o.id));
    const alreadySaved = groups.some((g) => g.outputs.length === playingIds.size && g.outputs.every((id) => playingIds.has(id)));
    const save = () => {
        const trimmed = name.trim();
        if (!trimmed)
            return;
        send({ type: "saveGroup", name: trimmed, outputs: playing.map((o) => o.id) });
        setName("");
        setNaming(false);
    };
    if (groups.length === 0 && playing.length < 2)
        return null;
    return (_jsxs("section", { className: "flex flex-col gap-2", "aria-labelledby": "groups-label", children: [_jsx("h3", { id: "groups-label", className: "section-title", children: words.title }), groups.length > 0 && (_jsx("ul", { className: "flex flex-col gap-2", "aria-labelledby": "groups-label", children: groups.map((group) => {
                    const members = group.outputs.map((id) => names.get(id)).filter(Boolean).join(", ");
                    const on = group.state === "on" || group.state === "partly";
                    return (_jsxs("li", { className: "output-row glass flex items-center gap-3", children: [_jsxs("div", { className: "min-w-0 flex-1", children: [_jsx("p", { className: "truncate text-[15px] font-semibold", children: group.name }), _jsx("p", { className: "truncate text-[12px] text-[var(--muted)]", children: group.state === "partly" ? words.partly(members) : members || words.noneAround })] }), group.state === "starting" && _jsx(Spinner, { size: "sm", color: "accent", "aria-hidden": "true" }), _jsx(Button, { size: "sm", variant: "tertiary", "aria-label": words.delete(group.name), onPress: () => send({ type: "deleteGroup", id: group.id }), children: words.remove }), _jsx(Switch, { isSelected: on, isDisabled: group.state === "starting", onChange: (turnOn) => send({ type: "setGroup", id: group.id, on: turnOn }), children: _jsxs(Switch.Content, { children: [_jsx(Switch.Control, { children: _jsx(Switch.Thumb, {}) }), _jsx("span", { className: "sr-only", children: words.turnOn(group.name) })] }) })] }, group.id));
                }) })), playing.length >= 2 &&
                !alreadySaved &&
                (naming ? (_jsxs("form", { className: "flex items-center gap-2", onSubmit: (event) => {
                        event.preventDefault();
                        save();
                    }, children: [_jsxs(TextField, { value: name, onChange: setName, maxLength: 40, autoFocus: true, className: "flex-1", children: [_jsx(Label, { className: "sr-only", children: words.nameLabel }), _jsx(Input, { placeholder: words.namePlaceholder, autoComplete: "off" })] }), _jsx(Button, { size: "sm", variant: "primary", type: "submit", isDisabled: !name.trim(), children: words.save }), _jsx(Button, { size: "sm", variant: "secondary", onPress: () => setNaming(false), children: words.cancel })] })) : (_jsx(Button, { size: "sm", variant: "secondary", className: "self-start", onPress: () => setNaming(true), children: words.saveAs(playing.length) })))] }));
}
