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
