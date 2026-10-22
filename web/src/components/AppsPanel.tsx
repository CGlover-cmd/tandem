import { Button, SearchField, Spinner } from "@heroui/react";
import {
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
  type KeyboardEvent as ReactKeyboardEvent,
  type PointerEvent as ReactPointerEvent,
  type ReactNode,
} from "react";
import { createPortal } from "react-dom";

import { ChevronIcon, ComputerIcon, GamepadIcon, GearIcon, SearchIcon, StoreIcon } from "../icons";
import {
  DRAG_SLOP_PX,
  DRAWN_APPS,
  filterApps,
  HOLD_TO_LIFT_MS,
  keyboardMove,
  monogram,
  moveItem,
  slotAt,
  tileColour,
  type Glyph,
  type GridLayout,
} from "../launcher";
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
    return (
      <img
        className="app-tile-icon app-tile-img"
        src={app.icon}
        alt=""
        draggable={false}
        onError={() => setBroken(true)}
      />
    );
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

/** The app being held: where the pointer is and where on the tile it took hold. */
interface Lifted {
  id: string;
  pointerId: number;
  x: number;
  y: number;
  grabX: number;
  grabY: number;
  width: number;
  height: number;
  before: string[];
}

interface Hold {
  id: string;
  pointerId: number;
  startX: number;
  startY: number;
  timer: number;
}

/** A grid of the device's apps, with a search box. Opening one goes back to the remote.
 *  Hold an app to lift it and drag it into place; Ctrl+Arrow moves the focused app. */
export function AppsPanel({ deviceId, apps, send, onDone }: Props) {
  const [query, setQuery] = useState("");
  const [order, setOrder] = useState<string[]>([]);
  const [lifted, setLifted] = useState<Lifted | null>(null);
  const [announcement, setAnnouncement] = useState("");
  const hold = useRef<Hold | null>(null);
  const suppressClick = useRef(false);
  const grid = useRef<HTMLUListElement | null>(null);
  const tiles = useRef(new Map<string, HTMLLIElement>());
  const lastRects = useRef(new Map<string, DOMRect>());
  const focusAfterMove = useRef<string | null>(null);

  // Fetch afresh each time the panel opens: apps get installed and removed.
  useEffect(() => {
    send({ type: "loadApps", id: deviceId });
  }, [deviceId, send]);

  const items = apps?.items;
  const byId = useMemo(() => new Map((items ?? []).map((app) => [app.id, app])), [items]);

  // Follow the list the app sends, except while the user is holding an app.
  useEffect(() => {
    if (!lifted) setOrder((items ?? []).map((app) => app.id));
  }, [items]); // not on `lifted`: dropping keeps the order until the app sends it back

  const ordered = useMemo(
    () => order.map((id) => byId.get(id)).filter((app): app is AppInfo => app !== undefined),
    [order, byId],
  );
  const shown = useMemo(() => filterApps(ordered, query), [ordered, query]);
  const searching = query.trim() !== "";
  const canArrange = !searching && apps?.state === "ready";
  const loading = apps === null || apps.state === "loading";

  // Slide the other tiles into their new places (FLIP: measure, invert, play).
  useLayoutEffect(() => {
    const next = new Map<string, DOMRect>();
    for (const [id, element] of tiles.current) {
      const rect = element.getBoundingClientRect();
      next.set(id, rect);
      const previous = lastRects.current.get(id);
      if (!previous || id === lifted?.id) continue;
      const dx = previous.left - rect.left;
      const dy = previous.top - rect.top;
      if (dx === 0 && dy === 0) continue;
      element.style.transition = "none";
      element.style.transform = `translate(${dx}px, ${dy}px)`;
      requestAnimationFrame(() => {
        element.style.transition = "";
        element.style.transform = "";
      });
    }
    lastRects.current = next;
    if (focusAfterMove.current) {
      tiles.current.get(focusAfterMove.current)?.querySelector("button")?.focus();
      focusAfterMove.current = null;
    }
  }, [shown, lifted?.id]);

  const layout = (): GridLayout | null => {
    const list = grid.current;
    const first = order[0] ? tiles.current.get(order[0]) : undefined;
    if (!list || !first) return null;
    const style = getComputedStyle(list);
    const columns = style.gridTemplateColumns.split(" ").filter(Boolean).length || 1;
    const box = list.getBoundingClientRect();
    return {
      originX: box.left + first.offsetLeft - list.scrollLeft,
      originY: box.top + first.offsetTop - list.scrollTop,
      cellWidth: first.offsetWidth + (Number.parseFloat(style.columnGap) || 0),
      cellHeight: first.offsetHeight + (Number.parseFloat(style.rowGap) || 0),
      columns,
      count: order.length,
    };
  };

  const commit = (next: string[], before: string[]) => {
    if (next.join("\n") !== before.join("\n")) send({ type: "reorderApps", id: deviceId, order: next });
  };

  const cancelHold = () => {
    if (hold.current) window.clearTimeout(hold.current.timer);
    hold.current = null;
  };

  const lift = (id: string, pointerId: number, x: number, y: number, target: HTMLElement) => {
    const rect = target.getBoundingClientRect();
    try {
      target.setPointerCapture(pointerId);
    } catch {
      // The pointer may already be gone; the drag then simply ends on pointerup.
    }
    suppressClick.current = true;
    setLifted({
      id,
      pointerId,
      x,
      y,
      grabX: x - rect.left,
      grabY: y - rect.top,
      width: rect.width,
      height: rect.height,
      before: order,
    });
  };

  const onPointerDown = (id: string) => (event: ReactPointerEvent<HTMLButtonElement>) => {
    suppressClick.current = false;
    if (!canArrange || event.button !== 0) return;
    const target = event.currentTarget;
    const { pointerId, clientX, clientY } = event;
    cancelHold();
    hold.current = {
      id,
      pointerId,
      startX: clientX,
      startY: clientY,
      timer: window.setTimeout(() => {
        hold.current = null;
        lift(id, pointerId, clientX, clientY, target);
      }, HOLD_TO_LIFT_MS),
    };
  };

  const onPointerMove = (event: ReactPointerEvent<HTMLButtonElement>) => {
    const pending = hold.current;
    if (pending && pending.pointerId === event.pointerId) {
      const moved = Math.hypot(event.clientX - pending.startX, event.clientY - pending.startY);
      if (moved > DRAG_SLOP_PX) cancelHold(); // scrolling, not holding
      return;
    }
    if (!lifted || lifted.pointerId !== event.pointerId) return;
    setLifted({ ...lifted, x: event.clientX, y: event.clientY });
    const geometry = layout();
    if (geometry) {
      const from = order.indexOf(lifted.id);
      const to = slotAt(event.clientX, event.clientY, geometry);
      if (from !== -1 && to !== from) setOrder(moveItem(order, from, to));
    }
    // Scroll the grid when the app is held near its top or bottom edge.
    const list = grid.current;
    if (list) {
      const box = list.getBoundingClientRect();
      if (event.clientY < box.top + 36) list.scrollTop -= 10;
      else if (event.clientY > box.bottom - 36) list.scrollTop += 10;
    }
  };

  const drop = (event: ReactPointerEvent<HTMLButtonElement>) => {
    cancelHold();
    if (!lifted || lifted.pointerId !== event.pointerId) return;
    commit(order, lifted.before);
    setLifted(null);
  };

  // Escape puts a held app back where it was.
  useEffect(() => {
    if (!lifted) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      event.preventDefault();
      event.stopPropagation();
      setOrder(lifted.before);
      setLifted(null);
    };
    window.addEventListener("keydown", onKey, true);
    return () => window.removeEventListener("keydown", onKey, true);
  }, [lifted]);

  useEffect(() => cancelHold, []);

  const onTileKeyDown = (app: AppInfo) => (event: ReactKeyboardEvent<HTMLButtonElement>) => {
    if (!(event.ctrlKey || event.altKey) || !canArrange) return;
    const geometry = layout();
    const index = order.indexOf(app.id);
    const target = keyboardMove(event.key, index, geometry?.columns ?? 1, order.length);
    if (target === null || index === -1) return;
    event.preventDefault();
    const next = moveItem(order, index, target);
    setOrder(next);
    commit(next, order);
    focusAfterMove.current = app.id;
    setAnnouncement(strings.launcher.moved(app.name, target + 1, next.length));
  };

  const liftedApp = lifted ? byId.get(lifted.id) : undefined;

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
      ) : loading && ordered.length === 0 ? (
        <div className="flex items-center justify-center gap-2 py-8 text-[var(--muted)]" aria-live="polite">
          <Spinner size="sm" />
          <span>{strings.launcher.loading}</span>
        </div>
      ) : shown.length === 0 ? (
        <p className="py-8 text-center text-[var(--muted)]" aria-live="polite">
          {searching ? strings.launcher.noMatch(query.trim()) : strings.launcher.empty}
        </p>
      ) : (
        <>
          <ul className="app-grid" ref={grid} aria-busy={loading} data-arranging={lifted ? true : undefined}>
            {shown.map((app) => (
              <li
                key={app.id}
                ref={(element) => {
                  if (element) tiles.current.set(app.id, element);
                  else tiles.current.delete(app.id);
                }}
                className="app-slot"
                data-lifted={lifted?.id === app.id || undefined}
              >
                <button
                  type="button"
                  className="app-tile"
                  aria-label={strings.launcher.openApp(app.name)}
                  aria-describedby="app-arrange-hint"
                  onPointerDown={onPointerDown(app.id)}
                  onPointerMove={onPointerMove}
                  onPointerUp={drop}
                  onPointerCancel={drop}
                  onContextMenu={(event) => event.preventDefault()}
                  onKeyDown={onTileKeyDown(app)}
                  onClick={() => {
                    if (suppressClick.current) {
                      suppressClick.current = false;
                      return;
                    }
                    send({ type: "launchApp", id: deviceId, appId: app.id });
                    onDone();
                  }}
                >
                  <AppIcon app={app} />
                  <span className="app-tile-name">{app.name}</span>
                </button>
              </li>
            ))}
          </ul>
          <p id="app-arrange-hint" className="text-center text-[11px] text-[var(--muted)]">
            {searching ? strings.launcher.arrangeAfterSearch : strings.launcher.arrangeHint}
          </p>
        </>
      )}
      <span className="sr-only" aria-live="polite">
        {announcement}
      </span>

      {lifted &&
        liftedApp &&
        createPortal(
          <div
            className="app-tile app-tile-lifted"
            aria-hidden="true"
            style={{
              left: lifted.x - lifted.grabX,
              top: lifted.y - lifted.grabY,
              width: lifted.width,
              height: lifted.height,
            }}
          >
            <AppIcon app={liftedApp} />
            <span className="app-tile-name">{liftedApp.name}</span>
          </div>,
          document.body,
        )}
    </section>
  );
}
