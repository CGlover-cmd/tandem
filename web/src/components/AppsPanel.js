import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { Button, SearchField, Spinner } from "@heroui/react";
import { useEffect, useMemo, useState } from "react";
import { ChevronIcon, ComputerIcon, GamepadIcon, GearIcon, SearchIcon, StoreIcon } from "../icons";
import { DRAWN_APPS, filterApps, monogram, tileColour } from "../launcher";
import { problemText, strings } from "../strings";
const GLYPHS = {
    settings: _jsx(GearIcon, { size: 28 }),
    search: _jsx(SearchIcon, { size: 28 }),
    store: _jsx(StoreIcon, { size: 28 }),
    arcade: _jsx(GamepadIcon, { size: 28 }),
    computers: _jsx(ComputerIcon, { size: 28 }),
};
/** The app's real icon when we have it; our own drawing for built-in apps; else its letters. */
function AppIcon({ app }) {
    const [broken, setBroken] = useState(false);
    useEffect(() => setBroken(false), [app.icon]);
    if (app.icon && !broken) {
        return _jsx("img", { className: "app-tile-icon app-tile-img", src: app.icon, alt: "", draggable: false, onError: () => setBroken(true) });
    }
    const drawn = DRAWN_APPS[app.id];
    return (_jsx("span", { className: "app-tile-icon", style: { backgroundColor: drawn ? drawn.colour : tileColour(app.id) }, "aria-hidden": "true", children: drawn ? GLYPHS[drawn.glyph] : monogram(app.name) }));
}
/** A grid of the device's apps, with a search box. Opening one goes back to the remote. */
export function AppsPanel({ deviceId, apps, send, onDone }) {
    const [query, setQuery] = useState("");
    // Fetch afresh each time the panel opens: apps get installed and removed.
    useEffect(() => {
        send({ type: "loadApps", id: deviceId });
    }, [deviceId, send]);
    const items = apps?.items ?? [];
    const shown = useMemo(() => filterApps(items, query), [items, query]);
    const loading = apps === null || apps.state === "loading";
    return (_jsxs("section", { className: "flex flex-col gap-3", "aria-label": strings.launcher.title, children: [_jsxs("div", { className: "flex items-center gap-2", children: [_jsx(Button, { isIconOnly: true, variant: "ghost", size: "sm", "aria-label": strings.launcher.back, onPress: onDone, children: _jsx(ChevronIcon, { direction: "left", size: 18 }) }), _jsx(SearchField, { "aria-label": strings.launcher.search, value: query, onChange: setQuery, className: "flex-1", autoFocus: true, children: _jsxs(SearchField.Group, { children: [_jsx(SearchField.SearchIcon, {}), _jsx(SearchField.Input, { placeholder: strings.launcher.search }), _jsx(SearchField.ClearButton, {})] }) })] }), apps?.state === "failed" ? (_jsxs("div", { className: "flex flex-col items-center gap-3 py-6 text-center", role: "alert", children: [_jsx("p", { className: "text-[var(--muted)]", children: apps.error ? problemText(apps.error) : strings.launcher.failed }), _jsx(Button, { variant: "secondary", onPress: () => send({ type: "loadApps", id: deviceId }), children: strings.launcher.retry })] })) : loading && items.length === 0 ? (_jsxs("div", { className: "flex items-center justify-center gap-2 py-8 text-[var(--muted)]", "aria-live": "polite", children: [_jsx(Spinner, { size: "sm" }), _jsx("span", { children: strings.launcher.loading })] })) : shown.length === 0 ? (_jsx("p", { className: "py-8 text-center text-[var(--muted)]", "aria-live": "polite", children: query.trim() ? strings.launcher.noMatch(query.trim()) : strings.launcher.empty })) : (_jsx("ul", { className: "app-grid", "aria-busy": loading, children: shown.map((app) => (_jsx("li", { children: _jsxs(Button, { variant: "ghost", className: "app-tile", "aria-label": strings.launcher.openApp(app.name), onPress: () => {
                            send({ type: "launchApp", id: deviceId, appId: app.id });
                            onDone();
                        }, children: [_jsx(AppIcon, { app: app }), _jsx("span", { className: "app-tile-name", children: app.name })] }) }, app.id))) }))] }));
}
