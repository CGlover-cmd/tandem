import { Button } from "@heroui/react";

import { strings } from "../strings";
import type { Command } from "../types";

/** Shown while Windows treats the network as Public: the firewall keeps speakers out until
 * the user marks it Private in Windows (Tandem's per-network trust list; ADR-0017). */
export function NetworkNote({ send, onDismiss }: { send: (command: Command) => void; onDismiss: () => void }) {
  const words = strings.network;
  return (
    <section className="glass network-note flex flex-col gap-2" role="status" aria-labelledby="network-title">
      <h2 id="network-title" className="text-[15px] font-semibold">
        {words.title}
      </h2>
      <p className="text-[13px] text-[var(--muted)]">{words.body}</p>
      <p className="text-[12px] text-[var(--muted)]">{words.steps}</p>
      <div className="flex flex-wrap gap-2">
        <Button size="sm" variant="primary" onPress={() => send({ type: "openNetworkSettings" })}>
          {words.trust}
        </Button>
        <Button size="sm" variant="secondary" onPress={onDismiss}>
          {words.later}
        </Button>
      </div>
    </section>
  );
}
