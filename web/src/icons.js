import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
// HeroUI sizes every svg inside a button with a class (14 px here). An inline size wins over
// that class, so an icon always shows at the size it asks for.
function sized(size, style) {
    return { width: size, height: size, ...style };
}
function Svg({ size = 24, children, style, ...props }) {
    return (_jsx("svg", { width: size, height: size, style: sized(size, style), viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", strokeWidth: 1.6, strokeLinecap: "round", strokeLinejoin: "round", "aria-hidden": "true", focusable: "false", ...props, children: children }));
}
export function TvIcon(props) {
    return (_jsxs(Svg, { ...props, children: [_jsx("rect", { x: "3", y: "4.5", width: "18", height: "12", rx: "2.5" }), _jsx("path", { d: "M8.5 20h7M12 16.5V20" })] }));
}
export function SpeakerIcon(props) {
    return (_jsxs(Svg, { ...props, children: [_jsx("path", { d: "M6 9.5C6 6.5 8.7 4 12 4s6 2.5 6 5.5V17a3 3 0 0 1-3 3H9a3 3 0 0 1-3-3Z" }), _jsx("path", { d: "M8.5 8.5h7" })] }));
}
export function SoundbarIcon(props) {
    return (_jsxs(Svg, { ...props, children: [_jsx("rect", { x: "2.5", y: "9", width: "19", height: "6", rx: "3" }), _jsx("path", { d: "M7 12h.01M12 12h.01M17 12h.01", strokeWidth: 2.4 })] }));
}
export function DeviceIcon({ kind, ...props }) {
    if (kind === "apple_tv")
        return _jsx(TvIcon, { ...props });
    if (kind === "homepod")
        return _jsx(SpeakerIcon, { ...props });
    return _jsx(SoundbarIcon, { ...props });
}
export function GearIcon(props) {
    return (_jsxs(Svg, { ...props, children: [_jsx("circle", { cx: "12", cy: "12", r: "3" }), _jsx("path", { d: "M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1Z" })] }));
}
export function CheckIcon(props) {
    return (_jsx(Svg, { ...props, children: _jsx("path", { d: "m5 12.5 4.5 4.5L19 7.5", strokeWidth: 2 }) }));
}
export function WarningIcon(props) {
    return (_jsxs(Svg, { ...props, children: [_jsx("path", { d: "M10.3 4.3 2.6 18a2 2 0 0 0 1.7 3h15.4a2 2 0 0 0 1.7-3L13.7 4.3a2 2 0 0 0-3.4 0Z" }), _jsx("path", { d: "M12 9.5v4M12 17h.01" })] }));
}
export function LogoMark(props) {
    return (_jsxs("svg", { width: props.size ?? 28, height: props.size ?? 28, viewBox: "0 0 32 32", "aria-hidden": "true", children: [_jsx("circle", { cx: "11.5", cy: "16", r: "9.6", fill: "#0066CC" }), _jsx("circle", { cx: "20.5", cy: "16", r: "9.6", fill: "rgba(90, 200, 250, 0.86)" }), _jsx("ellipse", { cx: "16", cy: "16", rx: "2.6", ry: "5.3", fill: "rgba(255, 255, 255, 0.47)" })] }));
}
function Filled({ size = 24, children, style, ...props }) {
    return (_jsx("svg", { width: size, height: size, style: sized(size, style), viewBox: "0 0 24 24", fill: "currentColor", "aria-hidden": "true", focusable: "false", ...props, children: children }));
}
export function PlayIcon(props) {
    return (_jsx(Filled, { ...props, children: _jsx("path", { d: "M8 5.5v13a1 1 0 0 0 1.5.86l10.4-6.5a1 1 0 0 0 0-1.72L9.5 4.64A1 1 0 0 0 8 5.5Z" }) }));
}
export function PauseIcon(props) {
    return (_jsxs(Filled, { ...props, children: [_jsx("rect", { x: "6.5", y: "5", width: "4", height: "14", rx: "1.2" }), _jsx("rect", { x: "13.5", y: "5", width: "4", height: "14", rx: "1.2" })] }));
}
export function NextIcon(props) {
    return (_jsxs(Filled, { ...props, children: [_jsx("path", { d: "M4 6.6v10.8a.8.8 0 0 0 1.2.7l8.3-5.4a.8.8 0 0 0 0-1.4L5.2 5.9a.8.8 0 0 0-1.2.7Z" }), _jsx("path", { d: "M12 6.6v10.8a.8.8 0 0 0 1.2.7l8.3-5.4a.8.8 0 0 0 0-1.4l-8.3-5.4a.8.8 0 0 0-1.2.7Z" })] }));
}
export function PreviousIcon(props) {
    return _jsx(NextIcon, { ...props, style: { transform: "scaleX(-1)" } });
}
export function SkipForwardIcon(props) {
    return (_jsxs(Svg, { ...props, children: [_jsx("path", { d: "M19 12a7 7 0 1 1-2.05-4.95" }), _jsx("path", { d: "M19 4v4h-4" })] }));
}
export function SkipBackwardIcon(props) {
    return (_jsxs(Svg, { ...props, children: [_jsx("path", { d: "M5 12a7 7 0 1 0 2.05-4.95" }), _jsx("path", { d: "M5 4v4h4" })] }));
}
export function PowerIcon(props) {
    return (_jsxs(Svg, { ...props, children: [_jsx("path", { d: "M12 3.5v8" }), _jsx("path", { d: "M6.7 6.6a7.5 7.5 0 1 0 10.6 0" })] }));
}
export function BackIcon(props) {
    return (_jsx(Svg, { ...props, children: _jsx("path", { d: "m14.5 6-6 6 6 6", strokeWidth: 2 }) }));
}
export function ChevronIcon({ direction, ...props }) {
    const rotate = { up: 0, right: 90, down: 180, left: 270 }[direction];
    return (_jsx(Svg, { ...props, style: { transform: `rotate(${rotate}deg)` }, children: _jsx("path", { d: "m7 14 5-5 5 5", strokeWidth: 2 }) }));
}
export function RemoteIcon(props) {
    return (_jsxs(Svg, { ...props, children: [_jsx("rect", { x: "7", y: "2.5", width: "10", height: "19", rx: "5" }), _jsx("circle", { cx: "12", cy: "8", r: "2.2" }), _jsx("path", { d: "M12 13.5v.01M12 17v.01", strokeWidth: 2.4 })] }));
}
export function VolumeIcon({ level = 2, ...props }) {
    return (_jsxs(Svg, { ...props, children: [_jsx("path", { d: "M4 9.5v5h3.5L12 18.5v-13L7.5 9.5Z" }), level >= 1 && _jsx("path", { d: "M15.5 9.5a3.5 3.5 0 0 1 0 5" }), level >= 2 && _jsx("path", { d: "M18 7a7 7 0 0 1 0 10" })] }));
}
export function AppsIcon(props) {
    return (_jsxs(Svg, { ...props, children: [_jsx("rect", { x: "4", y: "4", width: "6.5", height: "6.5", rx: "2" }), _jsx("rect", { x: "13.5", y: "4", width: "6.5", height: "6.5", rx: "2" }), _jsx("rect", { x: "4", y: "13.5", width: "6.5", height: "6.5", rx: "2" }), _jsx("rect", { x: "13.5", y: "13.5", width: "6.5", height: "6.5", rx: "2" })] }));
}
export function KeyboardIcon(props) {
    return (_jsxs(Svg, { ...props, children: [_jsx("rect", { x: "2.5", y: "6", width: "19", height: "12", rx: "2.5" }), _jsx("path", { d: "M6 9.5h.01M9.3 9.5h.01M12.6 9.5h.01M15.9 9.5h.01M18 9.5h.01M6 12.5h.01M18 12.5h.01", strokeWidth: 2.2 }), _jsx("path", { d: "M8.5 15h7M9 12.5h6" })] }));
}
export function SearchIcon(props) {
    return (_jsxs(Svg, { ...props, children: [_jsx("circle", { cx: "10.5", cy: "10.5", r: "6" }), _jsx("path", { d: "m15 15 5 5" })] }));
}
export function StoreIcon(props) {
    return (_jsxs(Svg, { ...props, children: [_jsx("path", { d: "M5.5 8.5h13l-1 11h-11Z" }), _jsx("path", { d: "M9 10.5V7a3 3 0 0 1 6 0v3.5" })] }));
}
export function GamepadIcon(props) {
    return (_jsxs(Svg, { ...props, children: [_jsx("path", { d: "M7.5 7.5h9a4.5 4.5 0 0 1 4.4 5.5l-.6 3a2.6 2.6 0 0 1-4.6 1.1L14.3 15H9.7l-1.4 2.1a2.6 2.6 0 0 1-4.6-1.1l-.6-3a4.5 4.5 0 0 1 4.4-5.5Z" }), _jsx("path", { d: "M8 10v3M6.5 11.5h3M15.5 11h.01M17.5 12.5h.01" })] }));
}
export function ComputerIcon(props) {
    return (_jsxs(Svg, { ...props, children: [_jsx("rect", { x: "3.5", y: "4.5", width: "17", height: "11", rx: "2" }), _jsx("path", { d: "M9 19.5h6M12 15.5v4" }), _jsx("path", { d: "M15 15l5 5" })] }));
}
export function MusicIcon(props) {
    return (_jsxs(Svg, { ...props, children: [_jsx("path", { d: "M9 17.5V6.5l10-2v11" }), _jsx("circle", { cx: "6.5", cy: "17.5", r: "2.5" }), _jsx("circle", { cx: "16.5", cy: "15.5", r: "2.5" })] }));
}
export function WavesIcon(props) {
    return (_jsx(Svg, { ...props, children: _jsx("path", { d: "M4 10v4M8 7v10M12 4v16M16 7v10M20 10v4" }) }));
}
export function SendIcon(props) {
    return (_jsxs(Svg, { ...props, children: [_jsx("rect", { x: "3", y: "4", width: "18", height: "12", rx: "2" }), _jsx("path", { d: "M9 20h6M12 16v4" }), _jsx("path", { d: "M10.5 8l3 2-3 2Z" })] }));
}
export function HeadphonesIcon(props) {
    return (_jsxs(Svg, { ...props, children: [_jsx("path", { d: "M4 15v-3a8 8 0 0 1 16 0v3" }), _jsx("rect", { x: "3.5", y: "14", width: "4", height: "6", rx: "1.5" }), _jsx("rect", { x: "16.5", y: "14", width: "4", height: "6", rx: "1.5" })] }));
}
export function FolderIcon(props) {
    return (_jsx(Svg, { ...props, children: _jsx("path", { d: "M3.5 7.5a2 2 0 0 1 2-2h4l2 2h7a2 2 0 0 1 2 2v7.5a2 2 0 0 1-2 2h-13a2 2 0 0 1-2-2Z" }) }));
}
export function RadioIcon(props) {
    return (_jsxs(Svg, { ...props, children: [_jsx("rect", { x: "3", y: "8", width: "18", height: "12", rx: "2.5" }), _jsx("path", { d: "M7 8l10-4" }), _jsx("circle", { cx: "15.5", cy: "14", r: "2.5" }), _jsx("path", { d: "M6.5 12.5h4M6.5 15.5h4" })] }));
}
export function QueueIcon(props) {
    return (_jsxs(Svg, { ...props, children: [_jsx("path", { d: "M4 6.5h12M4 11.5h12M4 16.5h7" }), _jsx("path", { d: "M15.5 14.5v5l4-2.5Z" })] }));
}
export function PlusIcon(props) {
    return (_jsx(Svg, { ...props, children: _jsx("path", { d: "M12 5v14M5 12h14" }) }));
}
export function StopIcon(props) {
    return (_jsx(Svg, { ...props, children: _jsx("rect", { x: "6.5", y: "6.5", width: "11", height: "11", rx: "2" }) }));
}
export function PlayNextIcon(props) {
    return (_jsxs(Svg, { ...props, children: [_jsx("path", { d: "M4 7.5h9M4 12h9M4 16.5h5" }), _jsx("path", { d: "M15 7l5 3.5-5 3.5Z" })] }));
}
export function RefreshIcon(props) {
    return (_jsxs(Svg, { ...props, children: [_jsx("path", { d: "M19.5 12a7.5 7.5 0 1 1-2.2-5.3" }), _jsx("path", { d: "M19.5 4.5v4h-4" })] }));
}
export function CloseIcon(props) {
    return (_jsx(Svg, { ...props, children: _jsx("path", { d: "M6.5 6.5l11 11M17.5 6.5l-11 11" }) }));
}
