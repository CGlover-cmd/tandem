import { Button, Modal, Separator, Slider, Spinner, Switch, ToggleButton, ToggleButtonGroup } from "@heroui/react";
import { useState } from "react";

import { delayLabel, groupOutputs, outputLive, outputVolume } from "../audio";
import { DeviceIcon, HeadphonesIcon, VolumeIcon } from "../icons";
import { strings } from "../strings";
import type { AudioOutput, AudioPanel, AudioSource, Command } from "../types";

interface Props {
  isOpen: boolean;
  onClose: () => void;
  audio: AudioPanel;
  send: (command: Command) => void;
}

const MAX_DELAY_MS = 10_000;

function sliderValue(value: number | number[]): number {
  return Array.isArray(value) ? (value[0] ?? 0) : value;
}

/** A slider that shows the dragged value at once and sends only when the drag ends. */
function LiveSlider({
  label,
  value,
  min,
  max,
  step,
  onCommit,
  format,
}: {
  label: string;
  value: number;
  min: number;
  max: number;
  step: number;
  onCommit: (value: number) => void;
  format?: (value: number) => string;
}) {
  const [dragging, setDragging] = useState<number | null>(null);
  const shown = dragging ?? value;
  return (
    <Slider
      aria-label={label}
      className="flex-1"
      minValue={min}
      maxValue={max}
      step={step}
      value={shown}
      onChange={(v) => setDragging(sliderValue(v))}
      onChangeEnd={(v) => {
        setDragging(null);
        onCommit(sliderValue(v));
      }}
      aria-valuetext={format ? format(shown) : undefined}
    >
      <Slider.Track>
        <Slider.Fill />
        <Slider.Thumb />
      </Slider.Track>
    </Slider>
  );
}

function OutputRow({ output, send }: { output: AudioOutput; send: (command: Command) => void }) {
  const live = outputLive(output);
  const busy = output.state === "starting" || output.state === "waiting";
  const status = output.needsPairing ? strings.audio.pairFirst : strings.audio.state[output.state];
  return (
    <li className="output-row glass" data-on={live || undefined}>
      <div className="flex items-center gap-3">
        <span className="device-icon" data-connected={live || undefined}>
          {output.kind === "pc" ? (
            <HeadphonesIcon size={22} />
          ) : (
            <DeviceIcon kind={output.deviceKind ?? "other"} size={22} />
          )}
        </span>
        <div className="min-w-0 flex-1">
          <p className="truncate text-[15px] font-semibold">{output.name}</p>
          <p className="flex items-center gap-2 text-[12px] text-[var(--muted)]" aria-live="polite">
            {busy && <Spinner size="sm" color="accent" />}
            {status}
          </p>
        </div>
        <Switch
          isSelected={live}
          isDisabled={output.needsPairing}
          onChange={(on) => send({ type: "setOutput", id: output.id, on })}
        >
          <Switch.Content>
            <Switch.Control>
              <Switch.Thumb />
            </Switch.Control>
            <span className="sr-only">{strings.audio.turnOn(output.name)}</span>
          </Switch.Content>
        </Switch>
      </div>
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
          <div className="flex items-center gap-3">
            <span className="w-16 text-[12px] text-[var(--muted)]">{strings.audio.delay}</span>
            <LiveSlider
              label={strings.audio.delayOf(output.name)}
              value={output.delayMs}
              min={0}
              max={MAX_DELAY_MS}
              step={50}
              format={delayLabel}
              onCommit={(ms) => send({ type: "setOutputDelay", id: output.id, ms })}
            />
            <span className="w-12 text-right text-[12px] tabular-nums text-[var(--muted)]">
              {delayLabel(output.delayMs)}
            </span>
          </div>
        </div>
      )}
    </li>
  );
}

export function AudioSheet({ isOpen, onClose, audio, send }: Props) {
  const { airplay, pc } = groupOutputs(audio.outputs);
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
            <section className="flex flex-col gap-2" aria-labelledby="source-label">
              <h3 id="source-label" className="section-title">
                {strings.audio.source}
              </h3>
              <ToggleButtonGroup
                aria-labelledby="source-label"
                selectionMode="single"
                disallowEmptySelection
                selectedKeys={new Set([audio.source])}
                onSelectionChange={(keys) => {
                  const [source] = [...keys];
                  if (source === "system" || source === "player") {
                    send({ type: "setAudioSource", source: source as AudioSource });
                  }
                }}
                fullWidth
              >
                <ToggleButton id="system">{strings.audio.sourceSystem}</ToggleButton>
                <ToggleButton id="player">{strings.audio.sourcePlayer}</ToggleButton>
              </ToggleButtonGroup>
              <p className="text-[12px] text-[var(--muted)]">
                {audio.source === "system" ? strings.audio.sourceSystemDetail : strings.audio.sourcePlayerDetail}
              </p>
            </section>

            <Separator />

            <section className="flex flex-col gap-2" aria-labelledby="airplay-label">
              <h3 id="airplay-label" className="section-title">
                {strings.audio.airplay}
              </h3>
              {airplay.length === 0 ? (
                <p className="text-[13px] text-[var(--muted)]">{strings.audio.noOutputs}</p>
              ) : (
                <ul className="flex flex-col gap-2" aria-labelledby="airplay-label">
                  {airplay.map((output) => (
                    <OutputRow key={output.id} output={output} send={send} />
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
                    <OutputRow key={output.id} output={output} send={send} />
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
            <Button variant="primary" onPress={onClose}>
              {strings.audio.done}
            </Button>
          </Modal.Footer>
        </Modal.Dialog>
      </Modal.Container>
    </Modal.Backdrop>
  );
}
