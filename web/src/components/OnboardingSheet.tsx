import { Button, Modal, Spinner } from "@heroui/react";

import { CheckIcon } from "../icons";
import { allDone, onboardingSteps, type Step } from "../onboarding";
import { strings } from "../strings";
import type { AppState } from "../types";

interface Props {
  isOpen: boolean;
  state: AppState;
  onClose: () => void;
  onOpenAudio: () => void;
  onPair: (deviceId: string) => void;
}

function Mark({ step, index }: { step: Step; index: number }) {
  if (step.state === "done") {
    return (
      <span className="step-mark" data-done="true" aria-hidden="true">
        <CheckIcon size={16} />
      </span>
    );
  }
  if (step.state === "waiting") {
    return (
      <span className="step-mark" aria-hidden="true">
        <Spinner size="sm" color="accent" />
      </span>
    );
  }
  return (
    <span className="step-mark" aria-hidden="true">
      {index + 1}
    </span>
  );
}

export function OnboardingSheet({ isOpen, state, onClose, onOpenAudio, onPair }: Props) {
  const steps = onboardingSteps(state);
  const words = strings.onboarding;
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
          <Modal.Header className="flex flex-col items-start gap-1">
            <Modal.Heading className="text-[20px] font-semibold">{words.title}</Modal.Heading>
            <p className="text-[13px] text-[var(--muted)]">{words.subtitle}</p>
          </Modal.Header>
          <Modal.Body className="flex flex-col gap-3">
            <ol className="flex flex-col gap-2" aria-label={words.title}>
              {steps.map((step, index) => (
                <li key={step.id} className="glass onboarding-step flex items-start gap-3">
                  <Mark step={step} index={index} />
                  <div className="min-w-0 flex-1">
                    <p className="text-[15px] font-semibold">
                      {step.title}
                      <span className="sr-only">{step.state === "done" ? `, ${words.done}` : ""}</span>
                    </p>
                    <p className="text-[13px] text-[var(--muted)]">{step.detail}</p>
                  </div>
                  {step.id === "pair" && step.state === "todo" && step.deviceId && (
                    <Button size="sm" variant="primary" onPress={() => onPair(step.deviceId!)}>
                      {words.pair}
                    </Button>
                  )}
                  {step.id === "play" && step.state !== "done" && (
                    <Button size="sm" variant="secondary" onPress={onOpenAudio}>
                      {words.openAudio}
                    </Button>
                  )}
                </li>
              ))}
            </ol>
            <section className="flex flex-col gap-1" aria-labelledby="help-label">
              <h3 id="help-label" className="section-title">
                {words.helpTitle}
              </h3>
              <ul className="flex list-disc flex-col gap-1 pl-5 text-[12px] text-[var(--muted)]">
                {words.tips.map((tip) => (
                  <li key={tip}>{tip}</li>
                ))}
              </ul>
            </section>
          </Modal.Body>
          <Modal.Footer>
            <Button variant={allDone(steps) ? "primary" : "tertiary"} onPress={onClose}>
              {allDone(steps) ? words.finish : words.later}
            </Button>
          </Modal.Footer>
        </Modal.Dialog>
      </Modal.Container>
    </Modal.Backdrop>
  );
}
