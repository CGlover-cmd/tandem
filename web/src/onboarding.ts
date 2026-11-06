// The first-run checklist's steps, worked out from the live state so Vitest can check them.

import { strings } from "./strings";
import type { AppState } from "./types";

export type StepState = "done" | "todo" | "waiting";

export interface Step {
  id: "find" | "pair" | "play";
  title: string;
  detail: string;
  state: StepState;
}

export function onboardingSteps(state: AppState): Step[] {
  const words = strings.onboarding;
  const steps: Step[] = [];
  const found = state.devices.length > 0;
  steps.push({
    id: "find",
    title: words.findTitle,
    detail: found ? words.findDone(state.devices.length) : words.findDetail,
    state: found ? "done" : state.discovering ? "waiting" : "todo",
  });
  const tvs = state.devices.filter((d) => d.kind === "apple_tv");
  if (tvs.length > 0) {
    const paired = tvs.some((d) => !d.needsPairing);
    steps.push({
      id: "pair",
      title: words.pairTitle,
      detail: paired ? words.pairDone : words.pairDetail,
      state: paired ? "done" : "todo",
    });
  }
  const playing = state.audio.outputs.some((o) => o.state === "streaming");
  steps.push({
    id: "play",
    title: words.playTitle,
    detail: playing ? words.playDone : words.playDetail,
    state: playing ? "done" : "todo",
  });
  return steps;
}

export function allDone(steps: Step[]): boolean {
  return steps.every((s) => s.state === "done");
}
