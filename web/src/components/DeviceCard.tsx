import { Button, Card, Spinner } from "@heroui/react";
import { useEffect, useState } from "react";

import { actionFor, statusFor, type Tone } from "../devices";
import { DeviceIcon, RemoteIcon } from "../icons";
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
  onActivate: () => void;
  onOpenControls: () => void;
}

export function DeviceCard({ device, onActivate, onOpenControls }: Props) {
  const secondsLeft = useCountdown(device);
  const action = actionFor(device);
  const status = statusFor(device, secondsLeft);
  const connected = device.state === "connected" && !device.needsPairing;
  const controls = connected ? device.controls : null;
  const playing = controls?.nowPlaying;
  const showPlaying = playing && playing.title && playing.state !== "idle";

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
      <Card.Footer className="flex flex-row items-center gap-2">
        <Button
          size="sm"
          variant={action.primary ? "primary" : "secondary"}
          isDisabled={!action.enabled}
          onPress={onActivate}
          className="min-w-24"
        >
          {action.label}
        </Button>
        {controls && (
          <Button
            size="sm"
            variant="tertiary"
            onPress={onOpenControls}
            aria-label={`${strings.remote.open}: ${device.name}`}
          >
            <RemoteIcon size={16} />
            {strings.remote.open}
          </Button>
        )}
      </Card.Footer>
    </Card>
  );
}
