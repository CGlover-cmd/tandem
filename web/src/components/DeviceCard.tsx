import { Button, Card, Spinner } from "@heroui/react";
import { useEffect, useState } from "react";

import { cardButtons, statusFor, type DeviceCast, type Tone } from "../devices";
import { CastIcon, DeviceIcon, RemoteIcon, SendIcon, WavesIcon } from "../icons";
import { strings } from "../strings";
import type { Device } from "../types";

const TONE_COLOUR: Record<Tone, string> = {
  neutral: "var(--muted)",
  accent: "var(--tandem-accent-text)",
  success: "var(--success)",
  warning: "var(--warning)",
  danger: "var(--danger)",
};

/** Seconds left before a retry, counted down locally from the last `retryIn` we were sent. */
function useCountdown(device: Device): number {
  const [left, setLeft] = useState(0);
  useEffect(() => {
    if (device.state !== "waiting" || device.retryIn === null) {
      setLeft(0);
      return;
    }
    const due = Date.now() + device.retryIn * 1000;
    const tick = () => setLeft(Math.max(0, Math.ceil((due - Date.now()) / 1000)));
    tick();
    const timer = window.setInterval(tick, 250);
    return () => window.clearInterval(timer);
  }, [device.state, device.retryIn]);
  return left;
}

interface Props {
  device: Device;
  /** Is this PC's screen cast to this device? */
  cast?: DeviceCast;
  /** This PC has a screen to cast. */
  canCast?: boolean;
  onAudio: () => void;
  onCast?: () => void;
  onVideo: () => void;
  onRemote: () => void;
  /** The fallback Pair/Connect button, Disconnect and Cancel. */
  onActivate: () => void;
}

export function DeviceCard({
  device,
  cast = "off",
  canCast = false,
  onAudio,
  onCast,
  onVideo,
  onRemote,
  onActivate,
}: Props) {
  const secondsLeft = useCountdown(device);
  const buttons = cardButtons(device, canCast && onCast !== undefined);
  const status = statusFor(device, secondsLeft, cast);
  const connected = device.state === "connected" && !device.needsPairing;
  const playing = connected ? device.controls?.nowPlaying : null;
  // While the device plays this PC's sound or screen, what it reports playing is that stream.
  const showPlaying =
    playing && playing.title && playing.state !== "idle" && device.audio !== "on" && cast === "off";
  const audio = buttons.audio;

  return (
    <Card
      className="glass device-card"
      data-connected={connected || undefined}
      aria-label={`${device.name}, ${strings.kind[device.kind]}, ${status.text}`}
    >
      <Card.Header className="flex flex-row items-start justify-between gap-3">
        <span className="device-icon" data-connected={connected || undefined}>
          <DeviceIcon kind={device.kind} size={26} />
        </span>
        {device.state === "connecting" && <Spinner size="sm" color="accent" />}
        {buttons.quiet && (
          <Button size="sm" variant="ghost" onPress={onActivate} className="card-quiet-action">
            {buttons.quiet.label}
          </Button>
        )}
      </Card.Header>
      <Card.Content className="gap-1">
        <Card.Title className="text-[15px] font-semibold leading-snug truncate">
          {device.name}
        </Card.Title>
        <Card.Description className="text-[13px] text-[var(--muted)]">
          {strings.kind[device.kind]}
        </Card.Description>
        <p className="mt-1 flex items-center gap-2 text-[13px] text-[var(--muted)]" aria-live="polite">
          <span className="status-dot" style={{ background: TONE_COLOUR[status.tone] }} />
          {status.text}
        </p>
        {showPlaying && (
          <p className="truncate text-[12px] text-[var(--muted)]" title={playing.title ?? undefined}>
            <span aria-hidden="true">{playing.state === "playing" ? "▶ " : "❚❚ "}</span>
            {playing.title}
          </p>
        )}
      </Card.Content>
      <Card.Footer className="flex flex-row flex-wrap items-center gap-2">
        {audio && (
          <Button
            size="sm"
            variant={audio.on ? "primary" : "secondary"}
            isDisabled={!audio.enabled}
            aria-pressed={audio.on}
            aria-label={audio.on ? strings.action.audioOff(device.name) : strings.action.audioOn(device.name)}
            onPress={onAudio}
            className="card-media-button"
            data-on={audio.on || undefined}
          >
            {audio.state === "starting" ? <Spinner size="sm" color="current" /> : <WavesIcon size={16} />}
            {strings.action.audio}
          </Button>
        )}
        {buttons.video && (
          <Button
            size="sm"
            variant="secondary"
            isDisabled={device.state === "connecting"}
            aria-label={strings.action.videoOn(device.name)}
            onPress={onVideo}
            className="card-media-button"
          >
            <SendIcon size={16} />
            {strings.action.video}
          </Button>
        )}
        {buttons.cast && (
          <Button
            size="sm"
            variant={cast === "off" ? "secondary" : "primary"}
            isDisabled={device.state === "connecting"}
            aria-label={strings.action.castOn(device.name)}
            onPress={onCast}
            className="card-media-button"
            data-on={cast !== "off" || undefined}
          >
            {cast === "starting" ? <Spinner size="sm" color="current" /> : <CastIcon size={16} />}
            {strings.action.cast}
          </Button>
        )}
        {buttons.fallback && (
          <Button
            size="sm"
            variant={buttons.fallback.primary ? "primary" : "secondary"}
            isDisabled={!buttons.fallback.enabled}
            onPress={onActivate}
            className="min-w-24"
          >
            {buttons.fallback.label}
          </Button>
        )}
        {buttons.remote && (
          <Button
            size="sm"
            variant="tertiary"
            isIconOnly={buttons.video}
            onPress={onRemote}
            aria-label={`${strings.remote.open}: ${device.name}`}
          >
            <RemoteIcon size={16} />
            {/* Three buttons don't fit a card's width: a TV's remote is shown by its icon. */}
            {!buttons.video && strings.remote.open}
          </Button>
        )}
      </Card.Footer>
    </Card>
  );
}
