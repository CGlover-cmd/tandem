// The WebSocket link to the Python app. It sends the whole UI state after every change; we
// send commands back. If the link drops (the app restarting, a sleeping PC), we reconnect.
import { useCallback, useEffect, useRef, useState } from "react";
/** The WebSocket address for this page. The token comes from the page's own address. */
export function socketUrl(location) {
    const token = new URLSearchParams(location.search).get("token") ?? "";
    const scheme = location.protocol === "https:" ? "wss:" : "ws:";
    return `${scheme}//${location.host}/ws?token=${encodeURIComponent(token)}`;
}
/** Wait before reconnecting: 0.5 s, doubling, at most 5 s. */
export function retryDelay(attempt) {
    return Math.min(500 * 2 ** attempt, 5000);
}
export function parseMessage(raw) {
    try {
        const message = JSON.parse(raw);
        return message.type === "state" && message.state ? message.state : null;
    }
    catch {
        return null;
    }
}
export function useBridge(url = socketUrl(window.location)) {
    const [state, setState] = useState(null);
    const [status, setStatus] = useState("connecting");
    const socket = useRef(null);
    useEffect(() => {
        let attempt = 0;
        let timer;
        let stopped = false;
        const open = () => {
            const ws = new WebSocket(url);
            socket.current = ws;
            ws.onopen = () => {
                attempt = 0;
                setStatus("open");
            };
            ws.onmessage = (event) => {
                const next = parseMessage(String(event.data));
                if (next)
                    setState(next);
            };
            ws.onclose = () => {
                socket.current = null;
                if (stopped)
                    return;
                setStatus("lost");
                timer = window.setTimeout(open, retryDelay(attempt++));
            };
        };
        open();
        return () => {
            stopped = true;
            window.clearTimeout(timer);
            socket.current?.close();
        };
    }, [url]);
    const send = useCallback((command) => {
        const ws = socket.current;
        if (ws && ws.readyState === WebSocket.OPEN)
            ws.send(JSON.stringify(command));
    }, []);
    return { state, status, send };
}
