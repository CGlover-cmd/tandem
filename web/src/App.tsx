import { Button, Chip, Spinner, Toast, toast } from "@heroui/react";
import { useEffect, useMemo, useState, useSyncExternalStore } from "react";

import { useBridge } from "./bridge";
import { DeviceCard } from "./components/DeviceCard";
import { PairingSheet } from "./components/PairingSheet";
import { RemoteSheet } from "./components/RemoteSheet";
import { SettingsSheet } from "./components/SettingsSheet";
import { GearIcon, LogoMark } from "./icons";
import { problemText, strings } from "./strings";
import { applyTheme, backgroundCss, findBackground, type Mode } from "./theme";
import type { ThemeChoice } from "./types";

const darkQuery = window.matchMedia("(prefers-color-scheme: dark)");

function useSystemMode(): Mode {
  const dark = useSyncExternalStore(
    (onChange) => {
      darkQuery.addEventListener("change", onChange);
      return () => darkQuery.removeEventListener("change", onChange);
    },
    () => darkQuery.matches,
  );
  return dark ? "dark" : "light";
}

function resolveMode(choice: ThemeChoice, system: Mode): Mode {
  return choice === "system" ? system : choice;
}

export function App() {
  const { state, status, send } = useBridge();
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [remoteId, setRemoteId] = useState<string | null>(null);
  const remoteDevice = state?.devices.find((d) => d.id === remoteId) ?? null;
  const system = useSystemMode();
  const mode = resolveMode(state?.appearance.theme ?? "system", system);
  const background = findBackground(state?.appearance.background ?? "mist");

  useEffect(() => applyTheme(mode), [mode]);
  useEffect(() => {
    document.documentElement.dataset.reduceMotion = state?.reduceMotion ? "true" : "false";
  }, [state?.reduceMotion]);

  // Show the backend's messages as toasts, then tell it they've been seen.
  const message = state?.message;
  useEffect(() => {
    if (!message) return;
    toast.danger(problemText(message), { timeout: 6000 });
    send({ type: "dismissMessage" });
  }, [message, send]);

  const backdrop = useMemo(() => backgroundCss(background, mode), [background, mode]);

  return (
    <div className="app-backdrop" style={{ background: backdrop }}>
      <Toast.Provider placement="bottom" />
      <div className="app-shell">
        <header className="app-header">
          <div className="flex items-center gap-3">
            <LogoMark size={30} />
            <div>
              <h1 className="text-[28px] font-semibold leading-tight tracking-tight">
                {strings.devicesTitle}
              </h1>
              <p className="text-[13px] text-[var(--muted)]">{strings.devicesSubtitle}</p>
            </div>
          </div>
          <div className="flex items-center gap-3">
            {state?.discovering && (
              <span className="flex items-center gap-2 text-[13px] text-[var(--muted)]">
                <Spinner size="sm" color="accent" />
                {strings.searching}
              </span>
            )}
            {state?.demo && (
              <Chip size="sm" variant="soft" color="accent">
                {strings.demoBadge}
              </Chip>
            )}
            <Button
              isIconOnly
              variant="tertiary"
              aria-label={strings.settings}
              onPress={() => setSettingsOpen(true)}
            >
              <GearIcon size={20} />
            </Button>
          </div>
        </header>

        <main>
          {state && state.devices.length > 0 ? (
            <ul className="device-grid" aria-label={strings.devicesTitle}>
              {state.devices.map((device) => (
                <li key={device.id}>
                  <DeviceCard
                    device={device}
                    onActivate={() => send({ type: "activate", id: device.id })}
                    onOpenControls={() => setRemoteId(device.id)}
                  />
                </li>
              ))}
            </ul>
          ) : (
            <div className="empty-state glass">
              {state === null || state.discovering ? (
                <>
                  <Spinner color="accent" />
                  <p className="text-[var(--muted)]">{strings.searching}</p>
                </>
              ) : (
                <>
                  <h2 className="text-[17px] font-semibold">{strings.emptyTitle}</h2>
                  <p className="max-w-sm text-center text-[var(--muted)]">{strings.emptyBody}</p>
                </>
              )}
            </div>
          )}
        </main>
      </div>

      {status === "lost" && (
        <div className="link-lost" role="status">
          <Spinner size="sm" color="accent" />
          {strings.reconnecting}
        </div>
      )}

      {state && <PairingSheet pairing={state.pairing} send={send} />}
      <RemoteSheet device={remoteDevice} onClose={() => setRemoteId(null)} send={send} />
      {state && (
        <SettingsSheet
          isOpen={settingsOpen}
          onClose={() => setSettingsOpen(false)}
          appearance={state.appearance}
          mode={mode}
          send={send}
        />
      )}
    </div>
  );
}
