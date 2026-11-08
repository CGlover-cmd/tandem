import { Button, Modal, Separator, Switch } from "@heroui/react";

import { delayLabel, delayOutputs } from "../audio";
import { strings } from "../strings";
import type { Appearance, AudioPanel, Command, HomeBridge } from "../types";
import { LiveSlider } from "./LiveSlider";

interface Props {
  isOpen: boolean;
  onClose: () => void;
  onBack: () => void;
  appearance: Appearance;
  audio: AudioPanel;
  home: HomeBridge;
  send: (command: Command) => void;
}

const MAX_DELAY_MS = 10_000;

/** Settings most people never need: speaker delays, app icon lookups and the Home app bridge. */
export function AdvancedSheet({ isOpen, onClose, onBack, appearance, audio, home, send }: Props) {
  const words = strings.settingsSheet;
  const outputs = delayOutputs(audio.outputs);
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
            <Modal.Heading className="text-[20px] font-semibold">{words.advancedTitle}</Modal.Heading>
            <p className="text-[13px] text-[var(--muted)]">{words.advancedSubtitle}</p>
          </Modal.Header>
          <Modal.Body className="flex flex-col gap-5">
            <section className="flex flex-col gap-2" aria-labelledby="delay-label">
              <h3 id="delay-label" className="section-title">
                {words.delays}
              </h3>
              <p className="text-[12px] text-[var(--muted)]">{words.delaysDetail}</p>
              {outputs.length === 0 ? (
                <p className="text-[13px] text-[var(--muted)]">{words.noDelays}</p>
              ) : (
                <ul className="flex flex-col gap-3" aria-labelledby="delay-label">
                  {outputs.map((output) => (
                    <li key={output.id} className="flex flex-col gap-1">
                      <span className="flex items-center justify-between text-[13px]">
                        <span className="truncate font-medium">{output.name}</span>
                        <span className="tabular-nums text-[var(--muted)]">{delayLabel(output.delayMs)}</span>
                      </span>
                      <LiveSlider
                        label={strings.audio.delayOf(output.name)}
                        value={output.delayMs}
                        min={0}
                        max={MAX_DELAY_MS}
                        step={50}
                        format={delayLabel}
                        onCommit={(ms) => send({ type: "setOutputDelay", id: output.id, ms })}
                      />
                    </li>
                  ))}
                </ul>
              )}
            </section>

            <Separator />

            <Switch
              isSelected={appearance.appIcons}
              onChange={(appIcons) => send({ type: "setAppearance", appIcons })}
              className="items-start gap-3"
            >
              <Switch.Content className="flex items-start gap-3">
                <Switch.Control>
                  <Switch.Thumb />
                </Switch.Control>
                <span className="flex flex-col gap-1">
                  <span className="section-title">{words.appIcons}</span>
                  <span className="text-[12px] text-[var(--muted)]">{words.appIconsDetail}</span>
                </span>
              </Switch.Content>
            </Switch>

            <Separator />

            <section className="flex flex-col gap-2" aria-labelledby="home-label">
              <h3 id="home-label" className="section-title">
                {strings.home.title}
              </h3>
              <Switch
                isSelected={home.enabled}
                onChange={(on) => send({ type: "setHomeBridge", on })}
                className="items-start gap-3"
              >
                <Switch.Content className="flex items-start gap-3">
                  <Switch.Control>
                    <Switch.Thumb />
                  </Switch.Control>
                  <span className="flex flex-col gap-1">
                    <span className="text-[14px] font-medium">{strings.home.toggle}</span>
                    <span className="text-[12px] text-[var(--muted)]">{strings.home.detail}</span>
                  </span>
                </Switch.Content>
              </Switch>
              {home.enabled && home.failed && (
                <p className="text-[12px] text-[var(--danger)]" role="status">
                  {strings.home.failed}
                </p>
              )}
              {home.running && home.paired && (
                <p className="text-[12px] text-[var(--success)]" role="status">
                  {strings.home.added}
                </p>
              )}
              {home.running && !home.paired && home.setupCode && (
                <div className="glass send-status flex flex-col gap-1" role="status">
                  <span className="text-[12px] text-[var(--muted)]">{strings.home.addSteps}</span>
                  <span className="text-[22px] font-semibold tabular-nums tracking-wider">{home.setupCode}</span>
                </div>
              )}
            </section>
          </Modal.Body>
          <Modal.Footer>
            <Button variant="secondary" onPress={onBack}>
              {words.back}
            </Button>
            <Button variant="primary" onPress={onClose}>
              {words.done}
            </Button>
          </Modal.Footer>
        </Modal.Dialog>
      </Modal.Container>
    </Modal.Backdrop>
  );
}
