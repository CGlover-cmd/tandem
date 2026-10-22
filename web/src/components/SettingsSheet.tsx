import { Button, Modal, Separator, Switch, ToggleButton, ToggleButtonGroup } from "@heroui/react";
import { Label, Radio, RadioGroup } from "react-aria-components";

import { CheckIcon } from "../icons";
import { strings } from "../strings";
import { backgroundCss, backgrounds, type Background, type Mode } from "../theme";
import type { Appearance, Command, ThemeChoice } from "../types";

interface Props {
  isOpen: boolean;
  onClose: () => void;
  appearance: Appearance;
  mode: Mode;
  send: (command: Command) => void;
}

const THEMES: { id: ThemeChoice; label: string }[] = [
  { id: "system", label: strings.settingsSheet.themeSystem },
  { id: "light", label: strings.settingsSheet.themeLight },
  { id: "dark", label: strings.settingsSheet.themeDark },
];

function Swatch({ background, mode }: { background: Background; mode: Mode }) {
  return (
    <Radio
      value={background.id}
      aria-label={background.label}
      className="swatch group flex flex-col items-center gap-1.5 outline-none"
    >
      {({ isSelected }) => (
        <>
          <span
            className="swatch-chip"
            data-selected={isSelected || undefined}
            style={{ background: backgroundCss(background, mode) }}
          >
            {isSelected && <CheckIcon size={18} className="swatch-check" />}
          </span>
          <span className="text-[12px] text-[var(--muted)]">{background.label}</span>
        </>
      )}
    </Radio>
  );
}

export function SettingsSheet({ isOpen, onClose, appearance, mode, send }: Props) {
  const neutral = backgrounds.filter((b) => b.group === "neutral");
  const gradients = backgrounds.filter((b) => b.group === "gradient");

  return (
    <Modal.Backdrop
      isOpen={isOpen}
      onOpenChange={(open) => {
        if (!open) onClose();
      }}
      variant="blur"
    >
      <Modal.Container placement="center" size="md">
        <Modal.Dialog className="sheet">
          <Modal.CloseTrigger />
          <Modal.Header>
            <Modal.Heading className="text-[20px] font-semibold">
              {strings.settingsSheet.title}
            </Modal.Heading>
          </Modal.Header>
          <Modal.Body className="flex flex-col gap-5">
            <section className="flex flex-col gap-3" aria-labelledby="theme-label">
              <h3 id="theme-label" className="section-title">
                {strings.settingsSheet.theme}
              </h3>
              <ToggleButtonGroup
                aria-labelledby="theme-label"
                selectionMode="single"
                disallowEmptySelection
                selectedKeys={new Set([appearance.theme])}
                onSelectionChange={(keys) => {
                  const [theme] = [...keys];
                  if (typeof theme === "string") send({ type: "setAppearance", theme: theme as ThemeChoice });
                }}
                fullWidth
              >
                {THEMES.map((theme) => (
                  <ToggleButton key={theme.id} id={theme.id}>
                    {theme.label}
                  </ToggleButton>
                ))}
              </ToggleButtonGroup>
            </section>

            <Separator />

            <RadioGroup
              value={appearance.background}
              onChange={(background) => send({ type: "setAppearance", background })}
              className="flex flex-col gap-3"
            >
              <Label className="section-title">{strings.settingsSheet.background}</Label>
              <p className="text-[12px] text-[var(--muted)]">{strings.settingsSheet.neutral}</p>
              <div className="flex flex-wrap gap-4">
                {neutral.map((b) => (
                  <Swatch key={b.id} background={b} mode={mode} />
                ))}
              </div>
              <p className="text-[12px] text-[var(--muted)]">{strings.settingsSheet.gradients}</p>
              <div className="flex flex-wrap gap-4">
                {gradients.map((b) => (
                  <Swatch key={b.id} background={b} mode={mode} />
                ))}
              </div>
            </RadioGroup>

            <Separator />

            <Switch
              isSelected={appearance.appIcons}
              onChange={(appIcons) => send({ type: "setAppearance", appIcons })}
              className="items-start gap-3"
            >
              <Switch.Control>
                <Switch.Thumb />
              </Switch.Control>
              <Switch.Content className="flex flex-col gap-1">
                <span className="section-title">{strings.settingsSheet.appIcons}</span>
                <span className="text-[12px] text-[var(--muted)]">{strings.settingsSheet.appIconsDetail}</span>
              </Switch.Content>
            </Switch>
          </Modal.Body>
          <Modal.Footer>
            <Button variant="primary" onPress={onClose}>
              {strings.settingsSheet.done}
            </Button>
          </Modal.Footer>
        </Modal.Dialog>
      </Modal.Container>
    </Modal.Backdrop>
  );
}
