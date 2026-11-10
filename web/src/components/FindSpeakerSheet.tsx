import { Button, Input, Label, Modal, Separator, Spinner, TextField } from "@heroui/react";
import { useState } from "react";

import { strings } from "../strings";
import type { Command, NetworkState } from "../types";

interface Props {
  isOpen: boolean;
  onClose: () => void;
  network: NetworkState;
  send: (command: Command) => void;
}

/** "Can't find a speaker?": add one by its address, and check this PC for the usual reasons. */
export function FindSpeakerSheet({ isOpen, onClose, network, send }: Props) {
  const words = strings.findSpeaker;
  const [address, setAddress] = useState("");
  const add = () => {
    const text = address.trim();
    if (!text || network.adding) return;
    send({ type: "addSpeakerAddress", address: text });
    setAddress("");
  };
  return (
    <Modal.Backdrop
      isOpen={isOpen}
      onOpenChange={(open) => {
        if (!open) onClose();
      }}
      variant="blur"
    >
      <Modal.Container placement="center" size="md" scroll="inside">
        <Modal.Dialog className="sheet">
          <Modal.CloseTrigger />
          <Modal.Header className="flex flex-col items-start gap-1">
            <Modal.Heading className="text-[20px] font-semibold">{words.title}</Modal.Heading>
            <p className="text-[13px] text-[var(--muted)]">{words.subtitle}</p>
          </Modal.Header>
          <Modal.Body className="flex flex-col gap-5">
            <section className="flex flex-col gap-2" aria-labelledby="add-address-title">
              <h3 id="add-address-title" className="section-title">
                {words.addTitle}
              </h3>
              <p className="text-[13px] text-[var(--muted)]">{words.addDetail}</p>
              <form
                className="flex items-center gap-2"
                onSubmit={(event) => {
                  event.preventDefault();
                  add();
                }}
              >
                <TextField value={address} onChange={setAddress} maxLength={64} className="flex-1">
                  <Label className="sr-only">{words.addressLabel}</Label>
                  <Input placeholder={words.addressPlaceholder} autoComplete="off" inputMode="decimal" />
                </TextField>
                <Button size="sm" variant="primary" type="submit" isDisabled={!address.trim() || network.adding}>
                  {network.adding ? words.adding : words.add}
                </Button>
              </form>
              {network.addresses.length > 0 && (
                <ul className="flex flex-col gap-1" aria-label={words.saved}>
                  {network.addresses.map((saved) => (
                    <li key={saved} className="glass output-row flex items-center gap-3">
                      <span className="min-w-0 flex-1 truncate text-[14px]">{saved}</span>
                      <span className="text-[12px] text-[var(--muted)]">{words.saved}</span>
                      <Button
                        size="sm"
                        variant="tertiary"
                        aria-label={words.remove(saved)}
                        onPress={() => send({ type: "removeSpeakerAddress", address: saved })}
                      >
                        {strings.groups.remove}
                      </Button>
                    </li>
                  ))}
                </ul>
              )}
            </section>

            <Separator />

            <section className="flex flex-col gap-2" aria-labelledby="check-title">
              <h3 id="check-title" className="section-title">
                {words.checkTitle}
              </h3>
              <p className="text-[13px] text-[var(--muted)]">{words.checkDetail}</p>
              <div className="flex items-center gap-3">
                <Button
                  size="sm"
                  variant="secondary"
                  isDisabled={network.checking}
                  onPress={() => send({ type: "checkNetwork" })}
                >
                  {network.checking ? words.checking : words.check}
                </Button>
                {network.checking && <Spinner size="sm" color="accent" />}
              </div>
              {network.findings !== null && !network.checking && (
                <div className="flex flex-col gap-2" role="status">
                  <p className="text-[13px] text-[var(--muted)]">{words.seen(network.speakersSeen)}</p>
                  {network.findings.length === 0 ? (
                    <p className="text-[13px]">{words.nothingFound}</p>
                  ) : (
                    <ul className="flex list-disc flex-col gap-1 pl-5 text-[13px]">
                      {network.findings.map((finding) => (
                        <li key={finding}>{words.finding[finding]}</li>
                      ))}
                    </ul>
                  )}
                </div>
              )}
            </section>
          </Modal.Body>
          <Modal.Footer>
            <Button variant="primary" onPress={onClose}>
              {words.close}
            </Button>
          </Modal.Footer>
        </Modal.Dialog>
      </Modal.Container>
    </Modal.Backdrop>
  );
}
