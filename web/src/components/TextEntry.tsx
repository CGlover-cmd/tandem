import { Button, Input, Label, TextField } from "@heroui/react";
import { useEffect, useRef, useState } from "react";

import { MAX_TEXT, TYPING_PAUSE_MS } from "../launcher";
import { strings } from "../strings";
import type { Command } from "../types";

interface Props {
  deviceId: string;
  /** The TV is showing its keyboard now. */
  asking: boolean;
  send: (command: Command) => void;
  onClose: () => void;
}

/** Types into the text field on the TV. Each change replaces the TV's text, a moment after
 *  the last keystroke. The text may be a search or a password: it is never logged. */
export function TextEntry({ deviceId, asking, send, onClose }: Props) {
  const [text, setText] = useState("");
  const timer = useRef<number | null>(null);
  const flush = useRef<(() => void) | null>(null);

  const cancelPending = () => {
    if (timer.current !== null) {
      window.clearTimeout(timer.current);
      timer.current = null;
    }
    flush.current = null;
  };
  const sendNow = (value: string) => {
    cancelPending();
    send({ type: "setText", id: deviceId, text: value });
  };
  const sendSoon = (value: string) => {
    cancelPending();
    const deliver = () => {
      timer.current = null;
      flush.current = null;
      send({ type: "setText", id: deviceId, text: value });
    };
    flush.current = deliver;
    timer.current = window.setTimeout(deliver, TYPING_PAUSE_MS);
  };

  // A new keyboard on the TV starts empty.
  useEffect(() => {
    if (asking) setText("");
  }, [asking]);
  // Closing right after typing still sends the last keystrokes.
  useEffect(
    () => () => {
      if (timer.current !== null) window.clearTimeout(timer.current);
      flush.current?.();
    },
    [],
  );

  return (
    <section className="text-entry glass" aria-label={strings.typing.label}>
      <TextField
        value={text}
        maxLength={MAX_TEXT}
        onChange={(value) => {
          setText(value);
          sendSoon(value);
        }}
        onKeyDown={(event) => {
          if (event.key === "Enter") sendNow(text);
          if (event.key === "Escape") onClose();
        }}
        autoFocus
        fullWidth
      >
        <Label className="text-[13px] font-medium">
          {asking ? strings.typing.asking : strings.typing.label}
        </Label>
        <div className="flex items-center gap-2">
          <Input
            className="flex-1"
            placeholder={strings.typing.placeholder}
            autoComplete="off"
            spellCheck={false}
          />
          <Button
            variant="ghost"
            size="sm"
            isDisabled={text === ""}
            onPress={() => {
              setText("");
              sendNow("");
            }}
          >
            {strings.typing.clear}
          </Button>
        </div>
      </TextField>
      <p className="text-[11px] text-[var(--muted)]">
        {asking ? strings.typing.hint : strings.typing.selectFirst}
      </p>
    </section>
  );
}
