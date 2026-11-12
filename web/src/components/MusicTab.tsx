import { Tabs } from "@heroui/react";
import { useState } from "react";

import { strings } from "../strings";
import type { AppState, Command } from "../types";
import { AppleMusicView } from "./AppleMusic";
import { LibraryView, PlayerStrip, QueueView, RadioView } from "./Library";
import { MusicPanel } from "./Music";
import { SpotifyView } from "./Spotify";

type Source = "now" | "pc" | "radio" | "apple" | "spotify" | "queue";
const SOURCES: Source[] = ["now", "pc", "radio", "apple", "spotify", "queue"];

/** The Music tab: Tandem's own player on top, then what to play from. */
export function MusicTab({
  state,
  send,
  onOpenAudio,
  onOpenConnections,
}: {
  state: AppState;
  send: (command: Command) => void;
  onOpenAudio: () => void;
  onOpenConnections: () => void;
}) {
  const [source, setSource] = useState<Source>("now");
  const words = strings.library;
  const label: Record<Source, string> = {
    now: words.nowPlaying,
    pc: words.thisPc,
    radio: words.radio,
    apple: strings.appleMusic.source,
    spotify: strings.spotify.source,
    queue: `${words.queue}${state.player.queue.length > 0 ? ` (${state.player.queue.length})` : ""}`,
  };
  return (
    <div className="flex flex-col gap-4">
      <PlayerStrip player={state.player} speakers={state.audio.streaming} send={send} onOpenAudio={onOpenAudio} />
      <Tabs
        variant="secondary"
        selectedKey={source}
        onSelectionChange={(key) => setSource(SOURCES.find((s) => s === key) ?? "now")}
        className="music-sources"
      >
        <Tabs.List aria-label={words.sources} className="app-tabs">
          {SOURCES.map((id) => (
            <Tabs.Tab key={id} id={id}>
              {label[id]}
              <Tabs.Indicator />
            </Tabs.Tab>
          ))}
        </Tabs.List>
        <Tabs.Panel id="now">
          <MusicPanel music={state.music} send={send} />
        </Tabs.Panel>
        <Tabs.Panel id="pc">
          <LibraryView library={state.library} send={send} />
        </Tabs.Panel>
        <Tabs.Panel id="radio">
          <RadioView radio={state.radio} send={send} />
        </Tabs.Panel>
        <Tabs.Panel id="apple">
          <AppleMusicView catalog={state.catalog} send={send} />
        </Tabs.Panel>
        <Tabs.Panel id="spotify">
          <SpotifyView spotify={state.spotify} send={send} onOpenConnections={onOpenConnections} />
        </Tabs.Panel>
        <Tabs.Panel id="queue">
          <QueueView player={state.player} send={send} />
        </Tabs.Panel>
      </Tabs>
    </div>
  );
}
