import { Button, Chip, Kbd, Spinner, Tabs, Toast, toast } from "@heroui/react";
import { useEffect, useMemo, useRef, useState, useSyncExternalStore } from "react";

import { useBridge } from "./bridge";
import { castFor } from "./devices";
import { isCommandShortcut } from "./commands";
import { AdvancedSheet } from "./components/AdvancedSheet";
import { SpotifySheet } from "./components/Connections";
import { AudioSheet } from "./components/AudioSheet";
import { CastSheet } from "./components/CastSheet";
import { CommandBar } from "./components/CommandBar";
import { DeviceCard } from "./components/DeviceCard";
import { FindSpeakerSheet } from "./components/FindSpeakerSheet";
import { NowPlayingBar } from "./components/Music";
import { MusicTab } from "./components/MusicTab";
import { UpdateNote } from "./components/UpdateNote";
import { OnboardingSheet } from "./components/OnboardingSheet";
import { PairingSheet } from "./components/PairingSheet";
import { RemoteSheet } from "./components/RemoteSheet";
import { SendSheet } from "./components/SendSheet";
import { SettingsSheet } from "./components/SettingsSheet";
import { GearIcon, LogoMark, SearchIcon, WavesIcon } from "./icons";
import { problemText, strings } from "./strings";
import { applyTheme, DEFAULT_BACKGROUND, PHOTO_BACKGROUND, windowBackground, type Mode } from "./theme";
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

type View = "devices" | "music";

export function App() {
  const { state, status, send } = useBridge();
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const [findOpen, setFindOpen] = useState(false);
  const [spotifyOpen, setSpotifyOpen] = useState(false);
  const [updateDismissed, setUpdateDismissed] = useState(false);
  const update = updateDismissed ? null : (state?.update ?? null);
  // Ctrl+Alt+K anywhere: the app brings the window up and bumps this count.
  const commandsRequested = state?.commandsRequested ?? 0;
  const seenRequests = useRef<number | null>(null);
  useEffect(() => {
    if (seenRequests.current !== null && commandsRequested > seenRequests.current) setCommandsOpen(true);
    seenRequests.current = commandsRequested;
  }, [commandsRequested]);
  const [commandsOpen, setCommandsOpen] = useState(false);
  const [remoteId, setRemoteId] = useState<string | null>(null);
  const [audioOpen, setAudioOpen] = useState(false);
  const [guideOpen, setGuideOpen] = useState(false);
  const onboarded = state?.appearance.onboarded ?? true;
  // The checklist opens by itself until it has been closed once.
  useEffect(() => {
    if (!onboarded) setGuideOpen(true);
  }, [onboarded]);
  const closeGuide = () => {
    setGuideOpen(false);
    if (!onboarded) send({ type: "setAppearance", onboarded: true });
  };
  const [sendId, setSendId] = useState<string | null>(null);
  const sendDevice = state?.devices.find((d) => d.id === sendId) ?? null;
  const [castId, setCastId] = useState<string | null>(null);
  const castDevice = state?.devices.find((d) => d.id === castId) ?? null;
  const castActive = state?.cast.active ?? null;
  const castingTo =
    castActive && (castActive.state === "starting" || castActive.state === "playing")
      ? (state?.devices.find((d) => d.id === castActive.deviceId) ?? null)
      : null;
  // Video or Screen on an unpaired TV: pair first, then open its sheet.
  const [afterPairing, setAfterPairing] = useState<{ id: string; sheet: "send" | "cast" } | null>(null);
  const pairingState = state?.pairing.state ?? "closed";
  const pairingWasOpen = useRef(false);
  useEffect(() => {
    if (afterPairing === null) return;
    const device = state?.devices.find((d) => d.id === afterPairing.id);
    if (pairingState !== "closed") pairingWasOpen.current = true;
    if (device && !device.needsPairing) {
      if (pairingState !== "closed") return; // wait for the pairing sheet to close
      setAfterPairing(null);
      if (afterPairing.sheet === "cast") setCastId(device.id);
      else setSendId(device.id);
    } else if (!device || (pairingState === "closed" && pairingWasOpen.current)) {
      setAfterPairing(null); // the device left, or pairing was cancelled
    }
  }, [afterPairing, pairingState, state?.devices]);
  const openSheet = (device: { id: string; needsPairing: boolean }, sheet: "send" | "cast") => {
    send({ type: "openDevice", id: device.id });
    if (device.needsPairing) {
      pairingWasOpen.current = false;
      setAfterPairing({ id: device.id, sheet });
    } else if (sheet === "cast") {
      setCastId(device.id);
    } else {
      setSendId(device.id);
    }
  };
  const streaming = state?.audio.streaming ?? 0;
  const [view, setView] = useState<View>("devices");
  const music = state?.music ?? null;
  const showBar = music !== null && view !== "music";
  const remoteDevice = state?.devices.find((d) => d.id === remoteId) ?? null;
  const system = useSystemMode();
  const mode = resolveMode(state?.appearance.theme ?? "system", system);
  const backgroundId = state?.appearance.background ?? DEFAULT_BACKGROUND;
  const photo = state?.appearance.photo ?? null;
  const onPhoto = backgroundId === PHOTO_BACKGROUND && photo !== null;

  useEffect(() => applyTheme(mode), [mode]);
  useEffect(() => {
    document.documentElement.dataset.reduceMotion = state?.reduceMotion ? "true" : "false";
  }, [state?.reduceMotion]);

  // Ctrl+K opens the command bar from anywhere in the window.
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (!isCommandShortcut(event)) return;
      event.preventDefault();
      setCommandsOpen(true);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  // Show the backend's messages as toasts, then tell it they've been seen.
  const message = state?.message;
  useEffect(() => {
    if (!message) return;
    toast.danger(problemText(message), { timeout: 6000 });
    send({ type: "dismissMessage" });
  }, [message, send]);

  const backdrop = useMemo(() => windowBackground(backgroundId, photo, mode), [backgroundId, photo, mode]);
  const blur = state?.appearance.photoBlur ?? 0;

  return (
    <div
      className="app-backdrop"
      style={{ background: onPhoto ? "transparent" : backdrop }}
      data-photo={onPhoto || undefined}
    >
      {onPhoto && (
        <div className="photo-layer" aria-hidden="true" style={{ background: backdrop, filter: blur ? `blur(${blur}px)` : undefined }} />
      )}
      <Toast.Provider placement="bottom" />
      <Tabs
        className="app-shell"
        data-bar={showBar ? "" : undefined}
        selectedKey={view}
        onSelectionChange={(key) => setView(key === "music" ? "music" : "devices")}
      >
        <header className="app-header">
          <div className="flex items-center gap-3">
            <LogoMark size={30} />
            <div>
              <h1 className="text-[28px] font-semibold leading-tight tracking-tight">
                {strings.appName}
              </h1>
              <p className="text-[13px] text-[var(--muted)]">
                {view === "music" ? strings.music.subtitle : strings.devicesSubtitle}
              </p>
            </div>
          </div>
          <Tabs.List aria-label={strings.tabs.label} className="app-tabs">
            <Tabs.Tab id="devices">
              {strings.tabs.devices}
              <Tabs.Indicator />
            </Tabs.Tab>
            <Tabs.Tab id="music">
              {strings.tabs.music}
              <Tabs.Indicator />
            </Tabs.Tab>
          </Tabs.List>
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
              variant="tertiary"
              aria-label={streaming > 0 ? `${strings.audio.open}, ${strings.audio.badge(streaming)}` : strings.audio.open}
              onPress={() => setAudioOpen(true)}
              className="command-button"
              data-streaming={streaming > 0 || undefined}
            >
              <WavesIcon size={18} />
              <span>{strings.audio.open}</span>
              {streaming > 0 && (
                <Chip size="sm" variant="soft" color="success">
                  {strings.audio.badge(streaming)}
                </Chip>
              )}
            </Button>
            <Button
              variant="tertiary"
              aria-label={strings.commands.open}
              aria-keyshortcuts="Control+K"
              onPress={() => setCommandsOpen(true)}
              className="command-button"
            >
              <SearchIcon size={18} />
              <span>{strings.commands.open}</span>
              <Kbd className="command-kbd">{strings.commands.shortcut}</Kbd>
            </Button>
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

        <Tabs.Panel id="devices">
          {update && <UpdateNote version={update.version} send={send} onDismiss={() => setUpdateDismissed(true)} />}
          {state && state.devices.length > 0 ? (
            <ul className="device-grid" aria-label={strings.devicesTitle}>
              {state.devices.map((device) => (
                <li key={device.id}>
                  <DeviceCard
                    device={device}
                    cast={castFor(device, castActive)}
                    canCast={state.cast.screens.length > 0}
                    onCast={() => openSheet(device, "cast")}
                    onActivate={() => send({ type: "activate", id: device.id })}
                    onAudio={() =>
                      send({
                        type: "deviceAudio",
                        id: device.id,
                        on: device.audio !== "on" && device.audio !== "starting",
                      })
                    }
                    onVideo={() => openSheet(device, "send")}
                    onRemote={() => {
                      send({ type: "openDevice", id: device.id });
                      setRemoteId(device.id);
                    }}
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
                  <Button size="sm" variant="secondary" onPress={() => setFindOpen(true)}>
                    {strings.findSpeaker.open}
                  </Button>
                </>
              )}
            </div>
          )}
        </Tabs.Panel>
        <Tabs.Panel id="music">
          {state === null ? (
            <div className="empty-state glass">
              <Spinner color="accent" />
            </div>
          ) : (
            <MusicTab state={state} send={send} onOpenAudio={() => setAudioOpen(true)} onOpenConnections={() => setSpotifyOpen(true)} />
          )}
        </Tabs.Panel>
      </Tabs>

      {showBar && <NowPlayingBar music={music} send={send} onOpen={() => setView("music")} />}

      {status === "lost" && (
        <div className="link-lost" role="status">
          <Spinner size="sm" color="accent" />
          {strings.reconnecting}
        </div>
      )}

      {state && <PairingSheet pairing={state.pairing} send={send} />}
      {state && (
        <CommandBar
          isOpen={commandsOpen}
          onClose={() => setCommandsOpen(false)}
          commands={state.commands}
          send={send}
        />
      )}
      <RemoteSheet
        device={remoteDevice}
        music={music}
        output={state?.audio.outputs.find((o) => o.id === remoteId && o.kind === "airplay") ?? null}
        onClose={() => setRemoteId(null)}
        send={send}
      />
      {state && (
        <OnboardingSheet
          isOpen={guideOpen && !audioOpen && state.pairing.state === "closed"}
          state={state}
          onClose={closeGuide}
          onOpenAudio={() => setAudioOpen(true)}
          onPair={(id) => send({ type: "pair", id })}
        />
      )}
      {state && (
        <AudioSheet
          isOpen={audioOpen}
          onClose={() => setAudioOpen(false)}
          audio={state.audio}
          onFindSpeaker={() => {
            setAudioOpen(false);
            setFindOpen(true);
          }}
          send={send}
        />
      )}
      {state && (
        <FindSpeakerSheet
          isOpen={findOpen}
          onClose={() => setFindOpen(false)}
          network={state.network}
          send={send}
        />
      )}
      <SendSheet
        device={sendDevice}
        canPickFiles={state?.audio.canPickFiles ?? false}
        picking={state?.audio.picking ?? false}
        onClose={() => setSendId(null)}
        send={send}
      />
      {state && (
        <CastSheet
          device={castDevice}
          cast={state.cast}
          elsewhere={castingTo && castingTo.id !== castId ? castingTo.name : null}
          source={state.audio.source}
          onClose={() => setCastId(null)}
          send={send}
        />
      )}
      {state && (
        <SettingsSheet
          isOpen={settingsOpen}
          onClose={() => setSettingsOpen(false)}
          onOpenGuide={() => {
            setSettingsOpen(false);
            setGuideOpen(true);
          }}
          onOpenAdvanced={() => {
            setSettingsOpen(false);
            setAdvancedOpen(true);
          }}
          onFindSpeaker={() => {
            setSettingsOpen(false);
            setFindOpen(true);
          }}
          onOpenSpotify={() => {
            setSettingsOpen(false);
            setSpotifyOpen(true);
          }}
          appearance={state.appearance}
          spotify={state.spotify}
          mode={mode}
          send={send}
        />
      )}
      {state && (
        <SpotifySheet
          isOpen={spotifyOpen}
          onClose={() => setSpotifyOpen(false)}
          onBack={() => {
            setSpotifyOpen(false);
            setSettingsOpen(true);
          }}
          spotify={state.spotify}
          send={send}
        />
      )}
      {state && (
        <AdvancedSheet
          isOpen={advancedOpen}
          onClose={() => setAdvancedOpen(false)}
          onBack={() => {
            setAdvancedOpen(false);
            setSettingsOpen(true);
          }}
          appearance={state.appearance}
          audio={state.audio}
          home={state.home}
          reporting={state.reporting}
          send={send}
        />
      )}
    </div>
  );
}
