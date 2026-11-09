import { Button, Chip, Input, Label, Modal, Separator, Spinner, TextField } from "@heroui/react";
import { useState } from "react";

import { CheckIcon } from "../icons";
import { looksLikeClientId, setupStep } from "../spotify";
import { spotifyErrorText, strings } from "../strings";
import type { Command, Spotify } from "../types";

type Send = (command: Command) => void;
const words = strings.spotify;

/** Settings' Connections section: one row per music service. */
export function ConnectionsSection({ spotify, onOpen }: { spotify: Spotify; onOpen: () => void }) {
  return (
    <section className="flex flex-col gap-2" aria-labelledby="connections-label">
      <h3 id="connections-label" className="section-title">
        {words.connections}
      </h3>
      <p className="text-[12px] text-[var(--muted)]">{words.connectionsDetail}</p>
      <div className="flex items-center gap-3">
        <span className="flex min-w-0 flex-1 flex-col">
          <span className="font-medium">{words.name}</span>
          <span className="text-[12px] text-[var(--muted)]">{words.status[spotify.state]}</span>
        </span>
        <Button size="sm" variant="secondary" onPress={onOpen}>
          {spotify.state === "not_set_up" ? words.setUp : words.manage}
        </Button>
      </div>
    </section>
  );
}

function Step({ n, done, children }: { n: number; done: boolean; children: React.ReactNode }) {
  return (
    <li className="setup-step" data-done={done || undefined}>
      <span className="setup-step-number" aria-hidden="true">
        {done ? <CheckIcon size={14} /> : n}
      </span>
      <div className="flex min-w-0 flex-1 flex-col gap-2">{children}</div>
    </li>
  );
}

function CopyField({ value }: { value: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <div className="flex items-center gap-2">
      <code className="setup-code">{value}</code>
      <Button
        size="sm"
        variant="secondary"
        onPress={() => {
          void navigator.clipboard?.writeText(value).then(
            () => setCopied(true),
            () => setCopied(false),
          );
        }}
      >
        {copied ? words.copied : words.copy}
      </Button>
    </div>
  );
}

/** The walkthrough: make a Spotify developer app, paste its Client ID, sign in. */
export function SpotifySheet({
  isOpen,
  onClose,
  onBack,
  spotify,
  send,
}: {
  isOpen: boolean;
  onClose: () => void;
  onBack: () => void;
  spotify: Spotify;
  send: Send;
}) {
  const [clientId, setClientId] = useState("");
  const step = setupStep(spotify);
  const hasClientId = spotify.state !== "not_set_up";
  const save = () => {
    if (clientId.trim()) send({ type: "setSpotifyClientId", clientId });
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
            <Modal.Heading className="text-[20px] font-semibold">{words.sheetTitle}</Modal.Heading>
            <p className="text-[13px] text-[var(--muted)]">{words.sheetSubtitle}</p>
          </Modal.Header>
          <Modal.Body className="flex flex-col gap-4">
            {spotify.error && (
              <div className="flex items-start gap-2 rounded-xl bg-[var(--field-background)] p-3" role="alert">
                <p className="flex-1 text-[13px] text-[var(--danger)]">
                  {spotifyErrorText(spotify.error, spotify.redirectUri)}
                </p>
                <Button size="sm" variant="ghost" onPress={() => send({ type: "spotifyDismissError" })}>
                  {strings.dismiss}
                </Button>
              </div>
            )}

            {step === "done" ? (
              <div className="flex flex-col gap-3">
                <p className="flex items-center gap-2">
                  <Chip size="sm" variant="soft" color="success">
                    {words.status.signed_in}
                  </Chip>
                  <span className="text-[13px]">{words.connected}</span>
                </p>
              </div>
            ) : (
              <ol className="setup-steps">
                <Step n={1} done={hasClientId}>
                  <p className="text-[13px]">{words.step1}</p>
                  <p className="text-[12px] text-[var(--muted)]">{words.premiumNote}</p>
                  <div>
                    <Button size="sm" variant="secondary" onPress={() => send({ type: "openSpotifyDashboard" })}>
                      {words.openDashboard}
                    </Button>
                  </div>
                </Step>
                <Step n={2} done={hasClientId}>
                  <p className="text-[13px]">{words.step2}</p>
                </Step>
                <Step n={3} done={hasClientId}>
                  <p className="text-[13px]">{words.step3}</p>
                  <CopyField value={spotify.redirectUri} />
                </Step>
                <Step n={4} done={hasClientId}>
                  <p className="text-[13px]">{words.step4}</p>
                </Step>
                <Step n={5} done={hasClientId}>
                  <TextField value={clientId} onChange={setClientId} onKeyDown={(e) => e.key === "Enter" && save()} fullWidth>
                    <Label className="text-[13px]">{words.step5}</Label>
                    <div className="flex items-center gap-2">
                      <Input
                        className="flex-1 font-mono"
                        placeholder={hasClientId ? words.savedClientId : words.clientIdPlaceholder}
                        autoComplete="off"
                        spellCheck={false}
                        aria-label={words.clientId}
                      />
                      <Button variant="secondary" isDisabled={!looksLikeClientId(clientId)} onPress={save}>
                        {words.saveClientId}
                      </Button>
                    </div>
                  </TextField>
                </Step>
                <Step n={6} done={false}>
                  <p className="text-[13px]">{words.step6}</p>
                  {spotify.state === "signing_in" ? (
                    <div className="flex items-center gap-3" aria-live="polite">
                      <Spinner size="sm" />
                      <span className="text-[13px] text-[var(--muted)]">{words.waiting}</span>
                      <Button size="sm" variant="ghost" onPress={() => send({ type: "spotifyCancelSignIn" })}>
                        {words.cancel}
                      </Button>
                    </div>
                  ) : (
                    <div>
                      <Button variant="primary" isDisabled={step !== "signIn"} onPress={() => send({ type: "spotifySignIn" })}>
                        {words.signIn}
                      </Button>
                    </div>
                  )}
                </Step>
              </ol>
            )}

            {hasClientId && (
              <>
                <Separator />
                <div className="flex flex-col gap-2">
                  <p className="text-[12px] text-[var(--muted)]">{words.forgetDetail}</p>
                  <div className="flex flex-wrap gap-2">
                    {spotify.state === "signed_in" && (
                      <Button size="sm" variant="secondary" onPress={() => send({ type: "spotifySignOut" })}>
                        {words.signOut}
                      </Button>
                    )}
                    <Button size="sm" variant="danger-soft" onPress={() => send({ type: "spotifySignOut", forget: true })}>
                      {words.forget}
                    </Button>
                  </div>
                </div>
              </>
            )}
            <p className="text-[11px] text-[var(--muted)]">{words.privacy}</p>
          </Modal.Body>
          <Modal.Footer className="flex flex-wrap gap-2">
            <Button variant="secondary" onPress={onBack}>
              {strings.settingsSheet.back}
            </Button>
            <Button variant="primary" onPress={onClose}>
              {strings.settingsSheet.done}
            </Button>
          </Modal.Footer>
        </Modal.Dialog>
      </Modal.Container>
    </Modal.Backdrop>
  );
}
