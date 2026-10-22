import { Button, SearchField, Spinner } from "@heroui/react";
import { useEffect, useMemo, useState, type ReactNode } from "react";

import { ChevronIcon, ComputerIcon, GamepadIcon, GearIcon, SearchIcon, StoreIcon } from "../icons";
import { DRAWN_APPS, filterApps, monogram, tileColour, type Glyph } from "../launcher";
import { problemText, strings } from "../strings";
import type { AppInfo, AppList, Command } from "../types";

const GLYPHS: Record<Glyph, ReactNode> = {
  settings: <GearIcon size={28} />,
  search: <SearchIcon size={28} />,
  store: <StoreIcon size={28} />,
  arcade: <GamepadIcon size={28} />,
  computers: <ComputerIcon size={28} />,
};

/** The app's real icon when we have it; our own drawing for built-in apps; else its letters. */
function AppIcon({ app }: { app: AppInfo }) {
  const [broken, setBroken] = useState(false);
  useEffect(() => setBroken(false), [app.icon]);
  if (app.icon && !broken) {
    return <img className="app-tile-icon app-tile-img" src={app.icon} alt="" draggable={false} onError={() => setBroken(true)} />;
  }
  const drawn = DRAWN_APPS[app.id];
  return (
    <span
      className="app-tile-icon"
      style={{ backgroundColor: drawn ? drawn.colour : tileColour(app.id) }}
      aria-hidden="true"
    >
      {drawn ? GLYPHS[drawn.glyph] : monogram(app.name)}
    </span>
  );
}

interface Props {
  deviceId: string;
  apps: AppList | null;
  send: (command: Command) => void;
  /** Back to the remote, after opening an app or on the back button. */
  onDone: () => void;
}

/** A grid of the device's apps, with a search box. Opening one goes back to the remote. */
export function AppsPanel({ deviceId, apps, send, onDone }: Props) {
  const [query, setQuery] = useState("");

  // Fetch afresh each time the panel opens: apps get installed and removed.
  useEffect(() => {
    send({ type: "loadApps", id: deviceId });
  }, [deviceId, send]);

  const items = apps?.items ?? [];
  const shown = useMemo(() => filterApps(items, query), [items, query]);
  const loading = apps === null || apps.state === "loading";

  return (
    <section className="flex flex-col gap-3" aria-label={strings.launcher.title}>
      <div className="flex items-center gap-2">
        <Button isIconOnly variant="ghost" size="sm" aria-label={strings.launcher.back} onPress={onDone}>
          <ChevronIcon direction="left" size={18} />
        </Button>
        <SearchField
          aria-label={strings.launcher.search}
          value={query}
          onChange={setQuery}
          className="flex-1"
          autoFocus
        >
          <SearchField.Group>
            <SearchField.SearchIcon />
            <SearchField.Input placeholder={strings.launcher.search} />
            <SearchField.ClearButton />
          </SearchField.Group>
        </SearchField>
      </div>

      {apps?.state === "failed" ? (
        <div className="flex flex-col items-center gap-3 py-6 text-center" role="alert">
          <p className="text-[var(--muted)]">
            {apps.error ? problemText(apps.error) : strings.launcher.failed}
          </p>
          <Button variant="secondary" onPress={() => send({ type: "loadApps", id: deviceId })}>
            {strings.launcher.retry}
          </Button>
        </div>
      ) : loading && items.length === 0 ? (
        <div className="flex items-center justify-center gap-2 py-8 text-[var(--muted)]" aria-live="polite">
          <Spinner size="sm" />
          <span>{strings.launcher.loading}</span>
        </div>
      ) : shown.length === 0 ? (
        <p className="py-8 text-center text-[var(--muted)]" aria-live="polite">
          {query.trim() ? strings.launcher.noMatch(query.trim()) : strings.launcher.empty}
        </p>
      ) : (
        <ul className="app-grid" aria-busy={loading}>
          {shown.map((app) => (
            <li key={app.id}>
              <Button
                variant="ghost"
                className="app-tile"
                aria-label={strings.launcher.openApp(app.name)}
                onPress={() => {
                  send({ type: "launchApp", id: deviceId, appId: app.id });
                  onDone();
                }}
              >
                <AppIcon app={app} />
                <span className="app-tile-name">{app.name}</span>
              </Button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
