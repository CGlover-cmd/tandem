import { Kbd, ListBox, Modal, SearchField, Spinner } from "@heroui/react";
import { useEffect, useId, useRef, useState } from "react";

import { outcomeText, outcomeTone, runsWhenPicked, suggestionsTitle, visibleOutcome } from "../commands";
import { CheckIcon, WarningIcon } from "../icons";
import { strings } from "../strings";
import type { CommandBarState, Command } from "../types";

interface Props {
  isOpen: boolean;
  onClose: () => void;
  commands: CommandBarState;
  send: (command: Command) => void;
}

const words = strings.commands;

/** Typed commands (Phase 9a): "pause", "volume 30 on the loft", "open Music on the TV".
 * Enter runs what's typed; the line under the box says what that will do as you type. */
export function CommandBar({ isOpen, onClose, commands, send }: Props) {
  const [text, setText] = useState("");
  const input = useRef<HTMLInputElement>(null);
  const list = useRef<HTMLDivElement>(null);
  const statusId = useId();

  // Each time the bar opens, start empty; the empty preview brings the examples.
  useEffect(() => {
    if (!isOpen) return;
    setText("");
    send({ type: "previewCommand", text: "" });
  }, [isOpen, send]);

  const edit = (value: string) => {
    setText(value);
    send({ type: "previewCommand", text: value });
  };
  const run = (value: string) => {
    if (value.trim()) send({ type: "runCommand", text: value });
  };
  const close = () => {
    send({ type: "clearCommand" });
    onClose();
  };

  const shown = visibleOutcome(commands, text);
  const running = commands.running && commands.text === text;
  const title = shown ? suggestionsTitle(shown) : null;
  const tone = shown ? outcomeTone(shown) : "neutral";

  return (
    <Modal.Backdrop
      isOpen={isOpen}
      onOpenChange={(open) => {
        if (!open) close();
      }}
      variant="blur"
    >
      <Modal.Container placement="top" size="lg">
        <Modal.Dialog className="sheet command-bar" aria-label={words.title}>
          <Modal.Body className="flex flex-col gap-3 pt-5">
            <SearchField
              aria-label={words.label}
              aria-describedby={statusId}
              value={text}
              onChange={edit}
              onSubmit={run}
              autoFocus
              fullWidth
            >
              <SearchField.Group className="command-input">
                <SearchField.SearchIcon />
                <SearchField.Input
                  ref={input}
                  placeholder={words.placeholder}
                  autoComplete="off"
                  spellCheck={false}
                  onKeyDown={(event) => {
                    // Down arrow moves into the suggestions, like a menu.
                    if (event.key === "ArrowDown" && list.current) {
                      const first = list.current.querySelector<HTMLElement>("[role='option']");
                      if (first) {
                        event.preventDefault();
                        first.focus();
                      }
                    }
                  }}
                />
                <SearchField.ClearButton />
              </SearchField.Group>
            </SearchField>

            <p id={statusId} className="command-status" data-tone={tone} role="status" aria-live="polite">
              {running ? (
                <>
                  <Spinner size="sm" color="accent" />
                  {words.running}
                </>
              ) : shown ? (
                <>
                  {shown.status === "done" && <CheckIcon size={16} />}
                  {tone === "warning" || tone === "danger" ? <WarningIcon size={16} /> : null}
                  <span>{outcomeText(shown)}</span>
                  {shown.status === "ready" && <Kbd className="ml-auto">{"↵"}</Kbd>}
                </>
              ) : (
                <span className="text-[var(--muted)]">{words.hint}</span>
              )}
            </p>

            {shown && title && (
              <section className="flex flex-col gap-1" aria-label={title}>
                <h3 className="section-title px-1">{title}</h3>
                <div ref={list}>
                  <ListBox
                    aria-label={title}
                    selectionMode="none"
                    onAction={(key) => {
                      const picked = String(key);
                      setText(picked);
                      if (runsWhenPicked(shown)) {
                        send({ type: "previewCommand", text: picked });
                        run(picked);
                      } else {
                        edit(picked);
                      }
                      input.current?.focus();
                    }}
                    className="command-suggestions"
                  >
                    {shown.suggestions.map((suggestion) => (
                      <ListBox.Item key={suggestion} id={suggestion} textValue={suggestion}>
                        {suggestion}
                      </ListBox.Item>
                    ))}
                  </ListBox>
                </div>
              </section>
            )}
          </Modal.Body>
          <Modal.Footer className="command-footer">
            <span>
              <Kbd>{"↵"}</Kbd> {strings.commands.runKey}
            </span>
            <span>
              <Kbd>Esc</Kbd> {strings.commands.closeKey}
            </span>
          </Modal.Footer>
        </Modal.Dialog>
      </Modal.Container>
    </Modal.Backdrop>
  );
}
