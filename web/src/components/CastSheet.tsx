import { Button, Modal, Spinner, Switch, ToggleButton, ToggleButtonGroup } from "@heroui/react";
import { useEffect, useState } from "react";

import { castFor } from "../devices";
import { CastIcon } from "../icons";
import { problemText, strings } from "../strings";
import type { AudioSource, CastPanel, CastQuality, Command, Device } from "../types";

interface Props {
  device: Device | null;
  cast: CastPanel;
  /** The name of the TV the screen is cast to now, if that's another one. */
  elsewhere: string | null;
  source: AudioSource;
  onClose: () => void;
  send: (command: Command) => void;
}

const QUALITIES: CastQuality[] = ["low", "standard", "high"];

export function CastSheet({ device, cast, elsewhere, source, onClose, send }: Props) {
  const words = strings.castSheet;
  const open = device !== null;
  const screens = cast.screens;
  const [screen, setScreen] = useState<number | null>(null);
  const [quality, setQuality] = useState<CastQuality>("standard");
  const [sound, setSound] = useState(true);
  // Look at the PC's displays each time the sheet opens: a monitor may have come or gone.
  useEffect(() => {
    if (device !== null) send({ type: "loadScreens" });
  }, [device?.id, send]);
  const chosen = screens.find((s) => s.index === screen) ?? screens[0] ?? null;
  const here = device ? castFor(device, cast.active) : "off";
  const status = device && cast.active?.deviceId === device.id ? cast.active : null;
  const live = here !== "off";

  const start = () => {
    if (device && chosen) {
      send({ type: "castScreen", id: device.id, screen: chosen.index, quality, sound });
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
              {device ? words.title(device.name) : ""}
            </Modal.Heading>
            <p className="text-[13px] text-[var(--muted)]">{words.subtitle}</p>
          </Modal.Header>
          <Modal.Body className="flex flex-col gap-5">
            {status && (
              <div className="glass send-status flex items-center gap-3" role="status">
                {status.state === "starting" ? (
                  <Spinner size="sm" color="accent" />
                ) : (
                  <CastIcon size={18} className="text-[var(--muted)]" />
                )}
                <span className="min-w-0 flex-1 text-[14px]">
                  {status.state === "starting"
                    ? words.starting
                    : status.state === "playing"
                      ? words.playing(device?.name ?? "")
                      : status.state === "ended"
                        ? words.ended
                        : problemText(status.problem ?? { code: "castRefused" })}
                </span>
                {live && (
                  <Button size="sm" variant="secondary" onPress={() => send({ type: "stopCast" })}>
                    {words.stop}
                  </Button>
                )}
              </div>
            )}
            {elsewhere && !live && <p className="text-[13px] text-[var(--muted)]">{words.elsewhere(elsewhere)}</p>}

            {screens.length === 0 ? (
              <p className="text-[13px] text-[var(--warning)]">{words.noScreens}</p>
            ) : (
              screens.length > 1 && (
                <section className="flex flex-col gap-2">
                  <h3 id="cast-screen-label" className="section-title">
                    {words.screen}
                  </h3>
                  <ToggleButtonGroup
                    aria-labelledby="cast-screen-label"
                    selectionMode="single"
                    disallowEmptySelection
                    selectedKeys={new Set(chosen ? [String(chosen.index)] : [])}
                    onSelectionChange={(keys) => {
                      const [key] = [...keys];
                      if (key !== undefined) setScreen(Number(key));
                    }}
                    fullWidth
                  >
                    {screens.map((s, position) => (
                      <ToggleButton key={s.index} id={String(s.index)} className="flex h-auto flex-col py-2">
                        <span>{words.screenName(position + 1, s.primary)}</span>
                        <span className="text-[11px] text-[var(--muted)]">{words.size(s.width, s.height)}</span>
                      </ToggleButton>
                    ))}
                  </ToggleButtonGroup>
                </section>
              )
            )}

            <section className="flex flex-col gap-2">
              <h3 id="cast-quality-label" className="section-title">
                {words.quality}
              </h3>
              <ToggleButtonGroup
                aria-labelledby="cast-quality-label"
                aria-describedby="cast-quality-detail"
                selectionMode="single"
                disallowEmptySelection
                selectedKeys={new Set([quality])}
                onSelectionChange={(keys) => {
                  const [key] = [...keys];
                  if (key === "low" || key === "standard" || key === "high") setQuality(key);
                }}
                fullWidth
              >
                {QUALITIES.map((q) => (
                  <ToggleButton key={q} id={q}>
                    {words.qualities[q]}
                  </ToggleButton>
                ))}
              </ToggleButtonGroup>
              <p id="cast-quality-detail" className="text-[12px] text-[var(--muted)]">
                {words.qualityDetail[quality]}
              </p>
            </section>

            <Switch isSelected={sound} onChange={setSound} className="items-start gap-3">
              <Switch.Content className="flex items-start gap-3">
                <Switch.Control>
                  <Switch.Thumb />
                </Switch.Control>
                <span className="flex flex-col gap-1">
                  <span className="section-title">{words.sound}</span>
                  <span className="text-[12px] text-[var(--muted)]">
                    {sound && source === "player" ? words.soundPlayer : words.soundDetail}
                  </span>
                </span>
              </Switch.Content>
            </Switch>

            <Button
              variant="primary"
              isDisabled={chosen === null || here === "starting"}
              onPress={start}
            >
              {here === "starting" ? <Spinner size="sm" color="current" /> : <CastIcon size={18} />}
              {live ? words.restart : words.start}
            </Button>
          </Modal.Body>
        </Modal.Dialog>
      </Modal.Container>
    </Modal.Backdrop>
  );
}
