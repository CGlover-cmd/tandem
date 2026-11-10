import { Button, Modal, Spinner, Switch } from "@heroui/react";

import {
  directSwitch,
  groupOutputs,
  masterChanges,
  masterVolume,
  outputDirect,
  outputLive,
  outputVolume,
  problemText,
} from "../audio";
import { DeviceIcon, HeadphonesIcon, VolumeIcon } from "../icons";
import { strings } from "../strings";
import type { AudioOutput, AudioPanel, Command } from "../types";
import { GroupsSection } from "./GroupsSection";
import { LiveSlider } from "./LiveSlider";

interface Props {
  isOpen: boolean;
  onClose: () => void;
  audio: AudioPanel;
  /** Windows treats the network as Public: speakers can't reach Tandem. */
  untrusted: boolean;
  send: (command: Command) => void;
}

function OutputRow({
  output,
  untrusted,
  send,
}: {
  output: AudioOutput;
  untrusted: boolean;
  send: (command: Command) => void;
}) {
  const problem = problemText(output, untrusted);
  const direct = outputDirect(output);
  const live = outputLive(output);
  const pcSwitch = direct ? directSwitch(output) : null;
  const on = live || (pcSwitch?.on ?? false);
  const note =
    output.state === "muted"
      ? strings.audio.mutedNote
      : output.state === "ahead"
        ? strings.audio.aheadNote
        : direct
          ? strings.audio.directNote
          : null;
  const busy = output.state === "starting" || output.state === "waiting";
  const status = output.needsPairing ? strings.audio.pairFirst : strings.audio.state[output.state];
  return (
    <li className="output-row glass" data-on={on || undefined} aria-busy={busy || undefined}>
      <div className="flex items-center gap-3">
        <span className="device-icon" data-connected={on || undefined}>
          {output.kind === "pc" ? (
            <HeadphonesIcon size={22} />
          ) : (
            <DeviceIcon kind={output.deviceKind ?? "other"} size={22} />
          )}
        </span>
        <div className="min-w-0 flex-1">
          <p className="truncate text-[15px] font-semibold">{output.name}</p>
          <p className="flex items-center gap-2 text-[12px] text-[var(--muted)]" aria-live="polite">
            {status}
          </p>
        </div>
        {busy && <Spinner size="sm" color="accent" aria-hidden="true" />}
        <Switch
          isSelected={on}
          isDisabled={output.needsPairing || (pcSwitch !== null && !pcSwitch.enabled)}
          onChange={(turnOn) => send({ type: "setOutput", id: output.id, on: turnOn })}
        >
          <Switch.Content>
            <Switch.Control>
              <Switch.Thumb />
            </Switch.Control>
            <span className="sr-only">
              {direct ? strings.audio.turnPcOn(output.name) : strings.audio.turnOn(output.name)}
            </span>
          </Switch.Content>
        </Switch>
      </div>
      {note && <p className="mt-2 text-[12px] text-[var(--muted)]">{note}</p>}
      {problem && (
        <div className="mt-2 flex flex-col items-start gap-2" role="status">
          <p className="text-[12px] text-[var(--danger)]">{problem}</p>
          {untrusted && output.kind === "airplay" && (
            <Button size="sm" variant="secondary" onPress={() => send({ type: "openNetworkSettings" })}>
              {strings.audio.trustNetwork}
            </Button>
          )}
        </div>
      )}
      {live && (
        <div className="mt-3 flex flex-col gap-2">
          <div className="flex items-center gap-3">
            <VolumeIcon level={1} size={16} className="text-[var(--muted)]" />
            <LiveSlider
              label={strings.audio.volumeOf(output.name)}
              value={outputVolume(output)}
              min={0}
              max={100}
              step={1}
              onCommit={(level) => send({ type: "setOutputVolume", id: output.id, level })}
            />
          </div>
        </div>
      )}
    </li>
  );
}

export function AudioSheet({ isOpen, onClose, audio, untrusted, send }: Props) {
  const { airplay, pc } = groupOutputs(audio.outputs);
  const master = masterVolume(audio.outputs);
  return (
    <Modal.Backdrop
      isOpen={isOpen}
      onOpenChange={(open) => {
        if (!open) onClose();
      }}
      variant="blur"
    >
      <Modal.Container placement="center" size="lg" scroll="inside">
        <Modal.Dialog className="sheet">
          <Modal.CloseTrigger />
          <Modal.Header className="flex flex-col items-start gap-1">
            <Modal.Heading className="text-[20px] font-semibold">{strings.audio.title}</Modal.Heading>
            <p className="text-[13px] text-[var(--muted)]">{strings.audio.subtitle}</p>
          </Modal.Header>
          <Modal.Body className="flex flex-col gap-5">
            {master !== null && (
              <section className="glass output-row flex items-center gap-3" aria-label={strings.audio.master}>
                <span className="w-24 text-[13px] font-semibold">{strings.audio.master}</span>
                <VolumeIcon level={1} size={16} className="text-[var(--muted)]" />
                <LiveSlider
                  label={strings.audio.masterOf}
                  value={master}
                  min={0}
                  max={100}
                  step={1}
                  onCommit={(level) => {
                    for (const change of masterChanges(audio.outputs, level)) {
                      send({ type: "setOutputVolume", id: change.id, level: change.level });
                    }
                  }}
                />
              </section>
            )}
            <GroupsSection groups={audio.groups} outputs={audio.outputs} send={send} />

            <section className="flex flex-col gap-2" aria-labelledby="airplay-label">
              <h3 id="airplay-label" className="section-title">
                {strings.audio.airplay}
              </h3>
              {airplay.length === 0 ? (
                <p className="text-[13px] text-[var(--muted)]">{strings.audio.noOutputs}</p>
              ) : (
                <ul className="flex flex-col gap-2" aria-labelledby="airplay-label">
                  {airplay.map((output) => (
                    <OutputRow key={output.id} output={output} untrusted={untrusted} send={send} />
                  ))}
                </ul>
              )}
              <p className="text-[12px] text-[var(--muted)]">{strings.audio.delayHint}</p>
            </section>

            <section className="flex flex-col gap-2" aria-labelledby="pc-label">
              <h3 id="pc-label" className="section-title">
                {strings.audio.pc}
              </h3>
              {pc.length === 0 ? (
                <p className="text-[13px] text-[var(--muted)]">{strings.audio.noPcOutputs}</p>
              ) : (
                <ul className="flex flex-col gap-2" aria-labelledby="pc-label">
                  {pc.map((output) => (
                    <OutputRow key={output.id} output={output} untrusted={untrusted} send={send} />
                  ))}
                </ul>
              )}
              {audio.pcOutputsHidden && (
                <p className="text-[12px] text-[var(--muted)]">{strings.audio.echoNote}</p>
              )}
            </section>
          </Modal.Body>
          <Modal.Footer>
            <Button
              variant="secondary"
              isDisabled={audio.streaming === 0}
              onPress={() => send({ type: "allOutputsOff" })}
            >
              {strings.audio.allOff}
            </Button>
          </Modal.Footer>
        </Modal.Dialog>
      </Modal.Container>
    </Modal.Backdrop>
  );
}
