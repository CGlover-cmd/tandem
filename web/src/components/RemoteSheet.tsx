import { Button, Modal, ProgressBar, Slider } from "@heroui/react";
import { useEffect, useRef, useState, type ReactNode } from "react";

import { estimatePosition, formatTime, keyFor, mediaButtons, pressAction, subtitle } from "../controls";
import { AppsPanel } from "./AppsPanel";
import { TextEntry } from "./TextEntry";
import {
  AppsIcon,
  BackIcon,
  ChevronIcon,
  DeviceIcon,
  KeyboardIcon,
  NextIcon,
  PauseIcon,
  PlayIcon,
  PowerIcon,
  PreviousIcon,
  SkipBackwardIcon,
  SkipForwardIcon,
  TvIcon,
  VolumeIcon,
} from "../icons";
import { strings } from "../strings";
import type { Command, Controls, Device, MediaCommand, NowPlaying, RemoteKey } from "../types";

interface Props {
  device: Device | null;
  onClose: () => void;
  send: (command: Command) => void;
}

type Send = (command: Command) => void;

/** A remote button: a quick press is a tap, a long one a hold (like the Siri Remote). */
function RemoteButton({
  deviceId,
  remoteKey,
  label,
  send,
  className,
  holdable = true,
  children,
}: {
  deviceId: string;
  remoteKey: RemoteKey;
  label: string;
  send: Send;
  className?: string;
  holdable?: boolean;
  children: ReactNode;
}) {
  const started = useRef(0);
  return (
    <Button
      isIconOnly
      variant="tertiary"
      aria-label={label}
      className={className}
      onPressStart={() => {
        started.current = performance.now();
      }}
      onPress={() => {
        const action = holdable ? pressAction(performance.now() - started.current) : "tap";
        send({ type: "press", id: deviceId, key: remoteKey, action });
      }}
    >
      {children}
    </Button>
  );
}

function useNow(active: boolean): number {
  const [now, setNow] = useState(() => performance.now());
  useEffect(() => {
    if (!active) return;
    const timer = window.setInterval(() => setNow(performance.now()), 500);
    return () => window.clearInterval(timer);
  }, [active]);
  return now;
}

function NowPlayingCard({ deviceId, playing, controls, send }: {
  deviceId: string;
  playing: NowPlaying;
  controls: Controls;
  send: Send;
}) {
  // Count on from the last position the device pushed, while it plays.
  const [since, setSince] = useState(() => performance.now());
  useEffect(() => setSince(performance.now()), [playing.position, playing.state]);
  const now = useNow(playing.state === "playing");
  const position = estimatePosition(playing, Math.max(0, (now - since) / 1000));
  const nothing = playing.state === "idle" || !playing.title;
  const media = (command: MediaCommand) => send({ type: "media", id: deviceId, command });
  const isPlaying = playing.state === "playing";

  const icons: Record<MediaCommand, { icon: ReactNode; label: string }> = {
    previous: { icon: <PreviousIcon size={22} />, label: strings.remote.previous },
    skip_backward: { icon: <SkipBackwardIcon size={22} />, label: strings.remote.skipBackward },
    play_pause: {
      icon: isPlaying ? <PauseIcon size={26} /> : <PlayIcon size={26} />,
      label: isPlaying ? strings.remote.pause : strings.remote.play,
    },
    skip_forward: { icon: <SkipForwardIcon size={22} />, label: strings.remote.skipForward },
    next: { icon: <NextIcon size={22} />, label: strings.remote.next },
  };

  return (
    <section className="now-playing glass" aria-label={nothing ? strings.remote.nothingPlaying : playing.title ?? ""}>
      {playing.app && <p className="now-playing-app">{playing.app}</p>}
      <p className="now-playing-title">{nothing ? strings.remote.nothingPlaying : playing.title}</p>
      {!nothing && subtitle(playing) && <p className="now-playing-subtitle">{subtitle(playing)}</p>}
      {!nothing && position !== null && playing.totalTime !== null && playing.totalTime > 0 && (
        <div className="flex flex-col gap-1">
          <ProgressBar
            aria-label={`${formatTime(position)} of ${formatTime(playing.totalTime)}`}
            value={position}
            maxValue={playing.totalTime}
            size="sm"
          >
            <ProgressBar.Track>
              <ProgressBar.Fill />
            </ProgressBar.Track>
          </ProgressBar>
          <div className="flex justify-between text-[11px] tabular-nums text-[var(--muted)]">
            <span>{formatTime(position)}</span>
            <span>-{formatTime(playing.totalTime - position)}</span>
          </div>
        </div>
      )}
      <div className="flex items-center justify-center gap-2">
        {mediaButtons(controls).map((command) => (
          <Button
            key={command}
            isIconOnly
            variant={command === "play_pause" ? "secondary" : "ghost"}
            size={command === "play_pause" ? "lg" : "md"}
            aria-label={icons[command].label}
            onPress={() => media(command)}
            className={command === "play_pause" ? "media-main" : undefined}
          >
            {icons[command].icon}
          </Button>
        ))}
      </div>
    </section>
  );
}

function TouchPad({ deviceId, send }: { deviceId: string; send: Send }) {
  const arrow = (key: "up" | "down" | "left" | "right", label: string) => (
    <RemoteButton deviceId={deviceId} remoteKey={key} label={label} send={send} className={`pad-arrow pad-${key}`}>
      <ChevronIcon direction={key} size={22} />
    </RemoteButton>
  );
  return (
    <div className="pad" role="group" aria-label={strings.remote.pad}>
      {arrow("up", strings.remote.up)}
      {arrow("left", strings.remote.left)}
      <RemoteButton
        deviceId={deviceId}
        remoteKey="select"
        label={strings.remote.select}
        send={send}
        className="pad-select"
      >
        <span className="pad-select-dot" />
      </RemoteButton>
      {arrow("right", strings.remote.right)}
      {arrow("down", strings.remote.down)}
    </div>
  );
}

function VolumeControl({ deviceId, controls, send }: { deviceId: string; controls: Controls; send: Send }) {
  // Follow the device's level, but don't fight the user while they drag.
  const [dragging, setDragging] = useState<number | null>(null);
  if (controls.volume === "none") {
    return <p className="text-center text-[13px] text-[var(--muted)]">{strings.remote.volumeElsewhere}</p>;
  }
  if (controls.volume === "steps") {
    return (
      <div className="flex items-center justify-center gap-3" role="group" aria-label={strings.remote.volume}>
        <RemoteButton deviceId={deviceId} remoteKey="volume_down" label={strings.remote.volumeDown} send={send} holdable={false} className="round-key">
          <VolumeIcon level={0} size={20} />
        </RemoteButton>
        <span className="text-[13px] text-[var(--muted)]">{strings.remote.volume}</span>
        <RemoteButton deviceId={deviceId} remoteKey="volume_up" label={strings.remote.volumeUp} send={send} holdable={false} className="round-key">
          <VolumeIcon level={2} size={20} />
        </RemoteButton>
      </div>
    );
  }
  const level = dragging ?? controls.volumeLevel ?? 0;
  return (
    <div className="flex items-center gap-3">
      <VolumeIcon level={0} size={18} className="text-[var(--muted)]" />
      <Slider
        aria-label={strings.remote.volume}
        className="flex-1"
        minValue={0}
        maxValue={100}
        value={level}
        onChange={(value) => setDragging(Array.isArray(value) ? (value[0] ?? 0) : value)}
        onChangeEnd={(value) => {
          const next = Array.isArray(value) ? (value[0] ?? 0) : value;
          setDragging(null);
          send({ type: "setVolume", id: deviceId, level: next });
        }}
      >
        <Slider.Track>
          <Slider.Fill />
          <Slider.Thumb />
        </Slider.Track>
      </Slider>
      <VolumeIcon level={2} size={18} className="text-[var(--muted)]" />
    </div>
  );
}

export function RemoteSheet({ device, onClose, send }: Props) {
  const controls = device?.controls ?? null;
  const open = device !== null;
  const [view, setView] = useState<"remote" | "apps">("remote");
  const [typing, setTyping] = useState(false);

  // Each time the sheet opens, or moves to another device, start on the remote.
  useEffect(() => {
    setView("remote");
    setTyping(false);
  }, [device?.id]);

  // Show the keyboard field when the TV asks for text, and hide it when the TV stops asking.
  const asking = controls?.keyboard ?? false;
  const canType = controls?.textEntry ?? false;
  useEffect(() => {
    setTyping(asking);
    if (asking) setView("remote");
  }, [asking]);

  // Keyboard: arrows, Enter and Backspace work the remote, unless a control has focus that
  // uses those keys itself (the volume slider, or a focused button for Enter).
  const deviceId = device?.id;
  const hasRemote = (controls?.remote ?? false) && view === "remote";
  useEffect(() => {
    if (!deviceId || !hasRemote) return;
    const onKeyDown = (event: KeyboardEvent) => {
      const key = keyFor(event.key);
      if (!key || event.altKey || event.ctrlKey || event.metaKey) return;
      const target = event.target instanceof HTMLElement ? event.target : null;
      if (target?.closest('[role="slider"], input, textarea')) return;
      if (key === "select" && target?.closest("button")) return;
      event.preventDefault();
      send({ type: "press", id: deviceId, key, action: "tap" });
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [deviceId, hasRemote, send]);

  return (
    <Modal.Backdrop
      isOpen={open}
      onOpenChange={(isOpen) => {
        if (!isOpen) onClose();
      }}
      variant="blur"
    >
      <Modal.Container placement="center" size="sm">
        <Modal.Dialog className="sheet remote-sheet">
          <Modal.CloseTrigger />
          {device && (
            <>
              <Modal.Header className="flex flex-row items-center gap-3">
                <span className="device-icon" data-connected>
                  <DeviceIcon kind={device.kind} size={22} />
                </span>
                <Modal.Heading className="flex-1 truncate text-[18px] font-semibold">
                  {strings.remote.title(device.name)}
                </Modal.Heading>
                {controls?.canPower && (
                  <Button
                    isIconOnly
                    variant="tertiary"
                    aria-label={controls.power === "off" ? strings.remote.turnOn : strings.remote.turnOff}
                    onPress={() => send({ type: "setPower", id: device.id, on: controls.power === "off" })}
                    className="mr-8"
                    data-power={controls.power}
                  >
                    <PowerIcon size={20} />
                  </Button>
                )}
              </Modal.Header>
              <Modal.Body className="flex flex-col gap-5">
                {controls === null ? (
                  <p className="text-center text-[var(--muted)]">{strings.status.connecting}</p>
                ) : view === "apps" && controls.apps ? (
                  <AppsPanel deviceId={device.id} apps={device.apps} send={send} onDone={() => setView("remote")} />
                ) : (
                  <>
                    {(controls.apps || controls.textEntry) && (
                      <div className="flex items-center justify-center gap-2">
                        {controls.apps && (
                          <Button variant="secondary" size="sm" onPress={() => setView("apps")}>
                            <AppsIcon size={16} />
                            {strings.launcher.open}
                          </Button>
                        )}
                        {controls.textEntry && (
                          <Button
                            variant={typing ? "primary" : "secondary"}
                            size="sm"
                            aria-pressed={typing}
                            aria-label={typing ? strings.typing.close : strings.typing.open}
                            onPress={() => setTyping(!typing)}
                          >
                            <KeyboardIcon size={16} />
                            {strings.typing.open}
                          </Button>
                        )}
                      </div>
                    )}
                    {typing && canType && (
                      <TextEntry
                        key={asking ? "asking" : "manual"}
                        deviceId={device.id}
                        asking={asking}
                        send={send}
                        onClose={() => setTyping(false)}
                      />
                    )}
                    {controls.nowPlaying && (
                      <NowPlayingCard deviceId={device.id} playing={controls.nowPlaying} controls={controls} send={send} />
                    )}
                    {controls.remote && (
                      <>
                        <TouchPad deviceId={device.id} send={send} />
                        <div className="flex items-center justify-center gap-4">
                          <RemoteButton deviceId={device.id} remoteKey="menu" label={strings.remote.back} send={send} className="round-key">
                            <BackIcon size={22} />
                          </RemoteButton>
                          <RemoteButton deviceId={device.id} remoteKey="home" label={strings.remote.home} send={send} className="round-key">
                            <TvIcon size={20} />
                          </RemoteButton>
                          <RemoteButton
                            deviceId={device.id}
                            remoteKey="play_pause"
                            label={strings.remote.playPause}
                            send={send}
                            holdable={false}
                            className="round-key"
                          >
                            <span className="flex items-center">
                              <PlayIcon size={14} />
                              <PauseIcon size={14} />
                            </span>
                          </RemoteButton>
                        </div>
                        <p className="text-center text-[11px] text-[var(--muted)]">{strings.remote.keyboardHint}</p>
                      </>
                    )}
                    <VolumeControl deviceId={device.id} controls={controls} send={send} />
                  </>
                )}
              </Modal.Body>
              <Modal.Footer>
                <Button variant="primary" onPress={onClose}>
                  {strings.remote.done}
                </Button>
              </Modal.Footer>
            </>
          )}
        </Modal.Dialog>
      </Modal.Container>
    </Modal.Backdrop>
  );
}
