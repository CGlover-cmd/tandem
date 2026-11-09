import { Button } from "@heroui/react";

import { strings } from "../strings";
import type { Command } from "../types";

/** A newer Tandem is on GitHub (the update check in Advanced settings found it). */
export function UpdateNote({
  version,
  send,
  onDismiss,
}: {
  version: string;
  send: (command: Command) => void;
  onDismiss: () => void;
}) {
  const words = strings.update;
  return (
    <section className="glass network-note flex flex-wrap items-center gap-3" role="status">
      <div className="min-w-0 flex-1">
        <h2 className="text-[15px] font-semibold">{words.title(version)}</h2>
        <p className="text-[13px] text-[var(--muted)]">{words.body}</p>
      </div>
      <Button size="sm" variant="primary" onPress={() => send({ type: "openUpdate" })}>
        {words.open}
      </Button>
      <Button size="sm" variant="secondary" onPress={onDismiss}>
        {words.later}
      </Button>
    </section>
  );
}
