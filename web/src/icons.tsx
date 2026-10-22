// Small line icons, drawn here so the app ships no icon font or image files.

import type { SVGProps } from "react";

import type { DeviceKind } from "./types";

type IconProps = SVGProps<SVGSVGElement> & { size?: number };

function Svg({ size = 24, children, ...props }: IconProps) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.6}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
      {...props}
    >
      {children}
    </svg>
  );
}

export function TvIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <rect x="3" y="4.5" width="18" height="12" rx="2.5" />
      <path d="M8.5 20h7M12 16.5V20" />
    </Svg>
  );
}

export function SpeakerIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M6 9.5C6 6.5 8.7 4 12 4s6 2.5 6 5.5V17a3 3 0 0 1-3 3H9a3 3 0 0 1-3-3Z" />
      <path d="M8.5 8.5h7" />
    </Svg>
  );
}

export function SoundbarIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <rect x="2.5" y="9" width="19" height="6" rx="3" />
      <path d="M7 12h.01M12 12h.01M17 12h.01" strokeWidth={2.4} />
    </Svg>
  );
}

export function DeviceIcon({ kind, ...props }: IconProps & { kind: DeviceKind }) {
  if (kind === "apple_tv") return <TvIcon {...props} />;
  if (kind === "homepod") return <SpeakerIcon {...props} />;
  return <SoundbarIcon {...props} />;
}

export function GearIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <circle cx="12" cy="12" r="3" />
      <path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1Z" />
    </Svg>
  );
}

export function CheckIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="m5 12.5 4.5 4.5L19 7.5" strokeWidth={2} />
    </Svg>
  );
}

export function WarningIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M10.3 4.3 2.6 18a2 2 0 0 0 1.7 3h15.4a2 2 0 0 0 1.7-3L13.7 4.3a2 2 0 0 0-3.4 0Z" />
      <path d="M12 9.5v4M12 17h.01" />
    </Svg>
  );
}

export function LogoMark(props: IconProps) {
  return (
    <svg width={props.size ?? 28} height={props.size ?? 28} viewBox="0 0 32 32" aria-hidden="true">
      <circle cx="11.5" cy="16" r="9.6" fill="#0066CC" />
      <circle cx="20.5" cy="16" r="9.6" fill="rgba(90, 200, 250, 0.86)" />
      <ellipse cx="16" cy="16" rx="2.6" ry="5.3" fill="rgba(255, 255, 255, 0.47)" />
    </svg>
  );
}

function Filled({ size = 24, children, ...props }: IconProps) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="currentColor"
      aria-hidden="true"
      focusable="false"
      {...props}
    >
      {children}
    </svg>
  );
}

export function PlayIcon(props: IconProps) {
  return (
    <Filled {...props}>
      <path d="M8 5.5v13a1 1 0 0 0 1.5.86l10.4-6.5a1 1 0 0 0 0-1.72L9.5 4.64A1 1 0 0 0 8 5.5Z" />
    </Filled>
  );
}

export function PauseIcon(props: IconProps) {
  return (
    <Filled {...props}>
      <rect x="6.5" y="5" width="4" height="14" rx="1.2" />
      <rect x="13.5" y="5" width="4" height="14" rx="1.2" />
    </Filled>
  );
}

export function NextIcon(props: IconProps) {
  return (
    <Filled {...props}>
      <path d="M4 6.6v10.8a.8.8 0 0 0 1.2.7l8.3-5.4a.8.8 0 0 0 0-1.4L5.2 5.9a.8.8 0 0 0-1.2.7Z" />
      <path d="M12 6.6v10.8a.8.8 0 0 0 1.2.7l8.3-5.4a.8.8 0 0 0 0-1.4l-8.3-5.4a.8.8 0 0 0-1.2.7Z" />
    </Filled>
  );
}

export function PreviousIcon(props: IconProps) {
  return <NextIcon {...props} style={{ transform: "scaleX(-1)" }} />;
}

export function SkipForwardIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M19 12a7 7 0 1 1-2.05-4.95" />
      <path d="M19 4v4h-4" />
    </Svg>
  );
}

export function SkipBackwardIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M5 12a7 7 0 1 0 2.05-4.95" />
      <path d="M5 4v4h4" />
    </Svg>
  );
}

export function PowerIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M12 3.5v8" />
      <path d="M6.7 6.6a7.5 7.5 0 1 0 10.6 0" />
    </Svg>
  );
}

export function BackIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="m14.5 6-6 6 6 6" strokeWidth={2} />
    </Svg>
  );
}

export function ChevronIcon({ direction, ...props }: IconProps & { direction: "up" | "down" | "left" | "right" }) {
  const rotate = { up: 0, right: 90, down: 180, left: 270 }[direction];
  return (
    <Svg {...props} style={{ transform: `rotate(${rotate}deg)` }}>
      <path d="m7 14 5-5 5 5" strokeWidth={2} />
    </Svg>
  );
}

export function RemoteIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <rect x="7" y="2.5" width="10" height="19" rx="5" />
      <circle cx="12" cy="8" r="2.2" />
      <path d="M12 13.5v.01M12 17v.01" strokeWidth={2.4} />
    </Svg>
  );
}

export function VolumeIcon({ level = 2, ...props }: IconProps & { level?: 0 | 1 | 2 }) {
  return (
    <Svg {...props}>
      <path d="M4 9.5v5h3.5L12 18.5v-13L7.5 9.5Z" />
      {level >= 1 && <path d="M15.5 9.5a3.5 3.5 0 0 1 0 5" />}
      {level >= 2 && <path d="M18 7a7 7 0 0 1 0 10" />}
    </Svg>
  );
}
