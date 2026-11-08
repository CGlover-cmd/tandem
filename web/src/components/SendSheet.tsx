import { Button, Input, Label, Modal, Spinner, TextField } from "@heroui/react";
import { useEffect, useState } from "react";

import { canSend, isLink, sendText } from "../audio";
import { SendIcon } from "../icons";
import { strings } from "../strings";
import type { Command, Device } from "../types";

interface Props {
  device: Device | null;
  canPickFiles: boolean;
  picking: boolean;
  onClose: () => void;
  send: (command: Command) => void;
}

export function SendSheet({ device, canPickFiles, picking, onClose, send }: Props) {
  const [link, setLink] = useState("");
  useEffect(() => setLink(""), [device?.id]);
  const open = device !== null;
  const ready = device !== null && canSend(device);
  const current = device?.send ?? null;
  const active = current !== null && (current.state === "starting" || current.state === "playing");

  const sendLink = () => {
    if (device && isLink(link)) {
      send({ type: "sendMedia", id: device.id, location: link.trim() });
    }
  };

  return (
    <Modal.Backdrop
      isOpen={open}
      onOpenChange={(isOpen) => {
        if (!isOpen) onClose();
      }}
      variant="blur"
    >
      <Modal.Container placement="center" size="md">
        <Modal.Dialog className="sheet">
          <Modal.CloseTrigger />
          <Modal.Header className="flex flex-col items-start gap-1">
            <Modal.Heading className="text-[20px] font-semibold">
              {device ? strings.sendSheet.title(device.name) : ""}
            </Modal.Heading>
            <p className="text-[13px] text-[var(--muted)]">{strings.sendSheet.subtitle}</p>
          </Modal.Header>
          <Modal.Body className="flex flex-col gap-4">
            {!ready && <p className="text-[13px] text-[var(--warning)]">{strings.sendSheet.connectFirst}</p>}

            {current && (
              <div className="glass send-status flex items-center gap-3" role="status">
                {current.state === "starting" ? (
                  <Spinner size="sm" color="accent" />
                ) : (
                  <SendIcon size={18} className="text-[var(--muted)]" />
                )}
                <span className="min-w-0 flex-1 truncate text-[14px]">{sendText(current)}</span>
                {active && device && (
                  <Button size="sm" variant="secondary" onPress={() => send({ type: "stopMedia", id: device.id })}>
                    {strings.sendSheet.stop}
                  </Button>
                )}
              </div>
            )}

            {canPickFiles && (
              <Button
                variant="primary"
                isDisabled={!ready || picking}
                onPress={() => device && send({ type: "pickMedia", id: device.id })}
              >
                {picking ? <Spinner size="sm" /> : <SendIcon size={18} />}
                {picking ? strings.sendSheet.choosing : strings.sendSheet.chooseFile}
              </Button>
            )}

            <TextField
              value={link}
              onChange={setLink}
              onKeyDown={(event) => {
                if (event.key === "Enter") sendLink();
              }}
              isDisabled={!ready}
              fullWidth
            >
              <Label className="text-[13px] font-medium">{strings.sendSheet.link}</Label>
              <div className="flex items-center gap-2">
                <Input
                  className="flex-1"
                  type="url"
                  placeholder={strings.sendSheet.linkPlaceholder}
                  autoComplete="off"
                  spellCheck={false}
                />
                <Button variant="secondary" isDisabled={!ready || !isLink(link)} onPress={sendLink}>
                  {strings.sendSheet.sendLink}
                </Button>
              </div>
            </TextField>
            <p className="text-[12px] text-[var(--muted)]">{strings.sendSheet.formats}</p>
          </Modal.Body>
        </Modal.Dialog>
      </Modal.Container>
    </Modal.Backdrop>
  );
}
