import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { Button } from "@heroui/react";
import { strings } from "../strings";
/** Shown while Windows treats the network as Public: the firewall keeps speakers out until
 * the user marks it Private in Windows (Tandem's per-network trust list; ADR-0017). */
export function NetworkNote({ send, onDismiss }) {
    const words = strings.network;
    return (_jsxs("section", { className: "glass network-note flex flex-col gap-2", role: "status", "aria-labelledby": "network-title", children: [_jsx("h2", { id: "network-title", className: "text-[15px] font-semibold", children: words.title }), _jsx("p", { className: "text-[13px] text-[var(--muted)]", children: words.body }), _jsx("p", { className: "text-[12px] text-[var(--muted)]", children: words.steps }), _jsxs("div", { className: "flex flex-wrap gap-2", children: [_jsx(Button, { size: "sm", variant: "primary", onPress: () => send({ type: "openNetworkSettings" }), children: words.trust }), _jsx(Button, { size: "sm", variant: "secondary", onPress: onDismiss, children: words.later })] })] }));
}
