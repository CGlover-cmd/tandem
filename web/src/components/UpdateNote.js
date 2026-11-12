import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { Button } from "@heroui/react";
import { strings } from "../strings";
/** A newer Tandem is on GitHub (the update check in Advanced settings found it). */
export function UpdateNote({ version, send, onDismiss, }) {
    const words = strings.update;
    return (_jsxs("section", { className: "glass network-note flex flex-wrap items-center gap-3", role: "status", children: [_jsxs("div", { className: "min-w-0 flex-1", children: [_jsx("h2", { className: "text-[15px] font-semibold", children: words.title(version) }), _jsx("p", { className: "text-[13px] text-[var(--muted)]", children: words.body })] }), _jsx(Button, { size: "sm", variant: "primary", onPress: () => send({ type: "openUpdate" }), children: words.open }), _jsx(Button, { size: "sm", variant: "secondary", onPress: onDismiss, children: words.later })] }));
}
