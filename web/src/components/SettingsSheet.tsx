import { Button, Modal, Separator, Spinner, ToggleButton, ToggleButtonGroup } from "@heroui/react";
import { useRef, useState } from "react";
import { Label, Radio, RadioGroup } from "react-aria-components";

import { CheckIcon } from "../icons";
import { uploadPhoto } from "../photo";
import { strings } from "../strings";
import { backgroundCss, backgrounds, PHOTO_BACKGROUND, windowBackground, type Background, type Mode } from "../theme";
import type { Appearance, Command, Spotify, ThemeChoice } from "../types";
import { ConnectionsSection } from "./Connections";

interface Props {
  isOpen: boolean;
  onClose: () => void;
  onOpenGuide: () => void;
  onOpenAdvanced: () => void;
  onOpenSpotify: () => void;
  appearance: Appearance;
  spotify: Spotify;
  mode: Mode;
  send: (command: Command) => void;
}

const THEMES: { id: ThemeChoice; label: string }[] = [
  { id: "system", label: strings.settingsSheet.themeSystem },
  { id: "light", label: strings.settingsSheet.themeLight },
  { id: "dark", label: strings.settingsSheet.themeDark },
];

function Swatch({ id, label, css }: { id: string; label: string; css: string }) {
  return (
    <Radio value={id} aria-label={label} className="swatch group flex flex-col items-center gap-1.5 outline-none">
      {({ isSelected }) => (
        <>
          <span className="swatch-chip" data-selected={isSelected || undefined} style={{ background: css }}>
            {isSelected && <CheckIcon size={18} className="swatch-check" />}
          </span>
          <span className="text-[12px] text-[var(--muted)]">{label}</span>
        </>
      )}
    </Radio>
  );
}

function PresetSwatch({ background, mode }: { background: Background; mode: Mode }) {
  return <Swatch id={background.id} label={background.label} css={backgroundCss(background, mode)} />;
}

/** "Choose a photo…": the picked picture is shrunk and sent to Tandem, which then shows it. */
function PhotoPicker({ hasPhoto }: { hasPhoto: boolean }) {
  const input = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState(false);
  const words = strings.settingsSheet;
  return (
    <div className="flex flex-col gap-1">
      <div className="flex items-center gap-3">
        <Button size="sm" variant="secondary" isDisabled={busy} onPress={() => input.current?.click()}>
          {hasPhoto ? words.changePhoto : words.choosePhoto}
        </Button>
        {busy && <Spinner size="sm" color="accent" />}
      </div>
      <input
        ref={input}
        type="file"
        accept="image/jpeg,image/png,image/webp"
        className="sr-only"
        tabIndex={-1}
        aria-hidden="true"
        onChange={(event) => {
          const file = event.target.files?.[0];
          event.target.value = "";
          if (!file) return;
          setBusy(true);
          setFailed(false);
          void uploadPhoto(file).then((ok) => {
            setBusy(false);
            setFailed(!ok);
          });
        }}
      />
      {failed && (
        <p className="text-[12px] text-[var(--danger)]" role="status">
          {words.photoFailed}
        </p>
      )}
    </div>
  );
}

export function SettingsSheet({ isOpen, onClose, onOpenGuide, onOpenAdvanced, onOpenSpotify, appearance, spotify, mode, send }: Props) {
  const neutral = backgrounds.filter((b) => b.group === "neutral");
  const gradients = backgrounds.filter((b) => b.group === "gradient");
  const words = strings.settingsSheet;

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
          <Modal.Header>
            <Modal.Heading className="text-[20px] font-semibold">{words.title}</Modal.Heading>
          </Modal.Header>
          <Modal.Body className="flex flex-col gap-5">
            <section className="flex flex-col gap-3" aria-labelledby="theme-label">
              <h3 id="theme-label" className="section-title">
                {words.theme}
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

            <section className="flex flex-col gap-3">
              <RadioGroup
                value={appearance.background}
                onChange={(background) => send({ type: "setAppearance", background })}
                className="flex flex-col gap-3"
              >
                <Label className="section-title">{words.background}</Label>
                <p className="text-[12px] text-[var(--muted)]">{words.gradients}</p>
                <div className="flex flex-wrap gap-4">
                  {gradients.map((b) => (
                    <PresetSwatch key={b.id} background={b} mode={mode} />
                  ))}
                </div>
                <p className="text-[12px] text-[var(--muted)]">{words.neutral}</p>
                <div className="flex flex-wrap gap-4">
                  {neutral.map((b) => (
                    <PresetSwatch key={b.id} background={b} mode={mode} />
                  ))}
                </div>
                <p className="text-[12px] text-[var(--muted)]">{words.photo}</p>
                {appearance.photo !== null && (
                  <div className="flex flex-wrap gap-4">
                    <Swatch
                      id={PHOTO_BACKGROUND}
                      label={words.photo}
                      css={windowBackground(PHOTO_BACKGROUND, appearance.photo, mode)}
                    />
                  </div>
                )}
              </RadioGroup>
              <PhotoPicker hasPhoto={appearance.photo !== null} />
            </section>

            <Separator />

            <ConnectionsSection spotify={spotify} onOpen={onOpenSpotify} />
          </Modal.Body>
          <Modal.Footer className="flex flex-wrap gap-2">
            <Button variant="secondary" onPress={onOpenGuide}>
              {strings.onboarding.reopen}
            </Button>
            <Button variant="secondary" onPress={onOpenAdvanced}>
              {words.advanced}
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
