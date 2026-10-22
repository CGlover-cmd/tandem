// The command bar's logic (Phase 9a), kept out of the component so Vitest can check it.

import { strings } from "./strings";
import type { CommandBarState, CommandOutcome } from "./types";

const words = strings.commands;

/** The outcome to show for what's in the box now: the result if it's for this text, else the
 * preview if it's for this text, else nothing (an answer for older text is out of date). */
export function visibleOutcome(state: CommandBarState, text: string): CommandOutcome | null {
  if (state.result && state.resultFor === text) return state.result;
  if (state.preview && state.text === text) return state.preview;
  return null;
}

function pick(table: Record<string, (p: Record<string, string>) => string>, code: string) {
  return Object.prototype.hasOwnProperty.call(table, code) ? table[code] : undefined;
}

/** One line saying what Enter will do, what happened, or what went wrong. */
export function outcomeText(outcome: CommandOutcome): string {
  const { status, code, params } = outcome;
  const words_ =
    status === "ready"
      ? pick(words.ready, code)
      : status === "done"
        ? pick(words.done, code)
        : pick(words.problem, code);
  return words_ ? words_(params) : words.somethingWrong;
}

export type Tone = "neutral" | "success" | "warning" | "danger";

export function outcomeTone(outcome: CommandOutcome): Tone {
  switch (outcome.status) {
    case "done":
      return "success";
    case "failed":
      return "danger";
    case "ready":
    case "help":
    case "needsInfo": // a question, not an error
      return "neutral";
    default:
      return "warning";
  }
}

/** The heading over the suggestions, or null when there are none to show. */
export function suggestionsTitle(outcome: CommandOutcome): string | null {
  if (outcome.suggestions.length === 0) return null;
  if (outcome.status === "help") return words.examples;
  if (outcome.status === "needsInfo") return words.didYouMean;
  return words.tryThese;
}

/** Picking a suggestion that answers a question ("Which device?") runs it straight away;
 * an example only fills the box, so the user can change it first. */
export function runsWhenPicked(outcome: CommandOutcome): boolean {
  return outcome.status === "needsInfo";
}

/** Ctrl+K (or Cmd+K) opens the command bar from anywhere in the window. */
export function isCommandShortcut(event: Pick<KeyboardEvent, "key" | "ctrlKey" | "metaKey" | "altKey" | "shiftKey">): boolean {
  return (
    (event.ctrlKey || event.metaKey) &&
    !event.altKey &&
    !event.shiftKey &&
    event.key.toLowerCase() === "k"
  );
}
