import { Button, InputOTP, Label, Modal, REGEXP_ONLY_DIGITS, Spinner } from "@heroui/react";
import { useEffect, useState } from "react";

import { CheckIcon, TvIcon, WarningIcon } from "../icons";
import { problemText, strings } from "../strings";
import type { Command, Pairing } from "../types";

interface Props {
  pairing: Pairing;
  send: (command: Command) => void;
}

export function PairingSheet({ pairing, send }: Props) {
  const [pin, setPin] = useState("");
  const { state, deviceName, error } = pairing;
  const open = state !== "closed";

  // Start each attempt with an empty PIN, and clear a wrong one so the user can retype.
  useEffect(() => {
    if (state === "starting" || (state === "enterPin" && error?.code === "wrongPin")) setPin("");
  }, [state, error]);

  const submit = (value: string) => {
    if (value.length === 4) send({ type: "submitPin", pin: value });
  };
  const dismiss = () =>
    send({ type: state === "done" || state === "failed" ? "closePairing" : "cancelPairing" });

  return (
    <Modal.Backdrop
      isOpen={open}
      onOpenChange={(isOpen) => {
        if (!isOpen) dismiss();
      }}
      variant="blur"
      isDismissable={state !== "checking"}
    >
      <Modal.Container placement="center" size="sm">
        <Modal.Dialog className="sheet" aria-label={strings.pairing.title(deviceName)}>
          <Modal.Header className="items-center text-center">
            <span className="sheet-icon" data-tone={state === "failed" ? "danger" : undefined}>
              {state === "done" ? (
                <CheckIcon size={28} />
              ) : state === "failed" ? (
                <WarningIcon size={28} />
              ) : (
                <TvIcon size={28} />
              )}
            </span>
            <Modal.Heading className="text-[20px] font-semibold">
              {state === "failed"
                ? strings.pairing.failedTitle
                : state === "done"
                  ? strings.pairing.doneTitle
                  : strings.pairing.title(deviceName)}
            </Modal.Heading>
          </Modal.Header>

          <Modal.Body className="flex flex-col items-center gap-4 text-center">
            {state === "starting" && (
              <p className="flex items-center gap-3 text-[var(--muted)]">
                <Spinner size="sm" color="accent" />
                {strings.pairing.starting(deviceName)}
              </p>
            )}

            {(state === "enterPin" || state === "checking") && (
              <>
                <p className="text-[var(--muted)]">{strings.pairing.enterPin}</p>
                <div className="flex flex-col items-center gap-2">
                  <Label className="sr-only">{strings.pairing.pinLabel}</Label>
                  <InputOTP
                    aria-label={strings.pairing.pinLabel}
                    maxLength={4}
                    pattern={REGEXP_ONLY_DIGITS}
                    value={pin}
                    onChange={setPin}
                    onComplete={submit}
                    isDisabled={state === "checking"}
                    autoFocus
                  >
                    <InputOTP.Group>
                      <InputOTP.Slot index={0} />
                      <InputOTP.Slot index={1} />
                      <InputOTP.Slot index={2} />
                      <InputOTP.Slot index={3} />
                    </InputOTP.Group>
                  </InputOTP>
                </div>
                <p className="min-h-5 text-[13px]" role="alert">
                  {state === "checking" ? (
                    <span className="flex items-center gap-2 text-[var(--muted)]">
                      <Spinner size="sm" color="accent" />
                      {strings.pairing.checking}
                    </span>
                  ) : error ? (
                    <span className="text-[var(--danger)]">{problemText(error)}</span>
                  ) : null}
                </p>
              </>
            )}

            {state === "done" && <p className="text-[var(--muted)]">{strings.pairing.done(deviceName)}</p>}

            {state === "failed" && error && (
              <p className="text-[var(--muted)]" role="alert">
                {problemText(error)}
              </p>
            )}
          </Modal.Body>

          <Modal.Footer className="justify-center">
            {state === "done" ? (
              <Button variant="primary" onPress={() => send({ type: "closePairing" })} autoFocus>
                {strings.pairing.close}
              </Button>
            ) : state === "failed" ? (
              <>
                <Button variant="secondary" onPress={() => send({ type: "closePairing" })}>
                  {strings.pairing.close}
                </Button>
                <Button
                  variant="primary"
                  onPress={() => {
                    send({ type: "closePairing" });
                    send({ type: "pair", id: pairing.deviceId });
                  }}
                >
                  {strings.pairing.tryAgain}
                </Button>
              </>
            ) : (
              <>
                <Button variant="secondary" onPress={() => send({ type: "cancelPairing" })}>
                  {strings.pairing.cancel}
                </Button>
                <Button
                  variant="primary"
                  isDisabled={state !== "enterPin" || pin.length !== 4}
                  onPress={() => submit(pin)}
                >
                  {strings.pairing.pair}
                </Button>
              </>
            )}
          </Modal.Footer>
        </Modal.Dialog>
      </Modal.Container>
    </Modal.Backdrop>
  );
}
