import { Button, SearchField, Spinner } from "@heroui/react";
import { useEffect, useRef, useState } from "react";

import { ComputerIcon, MusicIcon, PlayIcon, RefreshIcon, SpeakerIcon } from "../icons";
import { itemDetail, spotifyArtUrl, targetName } from "../spotify";
import { spotifyErrorText, strings } from "../strings";
import type { Command, Spotify, SpotifyDevice, SpotifyItem } from "../types";

type Send = (command: Command) => void;
const words = strings.spotify;

/** An item's artwork, fetched from Spotify through Tandem; a drawn note if there is none. */
function Art({ item, size }: { item: SpotifyItem; size: number }) {
  const [broken, setBroken] = useState(false);
  return (
    <span className="library-art" style={{ width: size, height: size }} aria-hidden="true">
      {item.hasArt && !broken ? (
        <img src={spotifyArtUrl(window.location.search, item.id)} alt="" loading="lazy" draggable={false} onError={() => setBroken(true)} />
      ) : (
        <MusicIcon size={Math.round(size * 0.42)} />
      )}
    </span>
  );
}

/** One playlist, album or song: press it to play; "Open in Spotify" links back to Spotify. */
function ItemRow({ item, send }: { item: SpotifyItem; send: Send }) {
  return (
    <li className="song-row">
      <button type="button" className="song-row-main" aria-label={words.play(item.title)} onClick={() => send({ type: "spotifyPlay", id: item.id })}>
        <Art item={item} size={44} />
        <span className="flex min-w-0 flex-1 flex-col">
          <span className="truncate font-medium">{item.title}</span>
          <span className="truncate text-[12px] text-[var(--muted)]">{itemDetail(item)}</span>
        </span>
        <PlayIcon size={16} className="flex-none text-[var(--muted)]" />
      </button>
      <Button
        size="sm"
        variant="ghost"
        className="flex-none"
        aria-label={words.openOnSpotify(item.title)}
        onPress={() => send({ type: "openInSpotify", id: item.id })}
      >
        {words.openShort}
      </Button>
    </li>
  );
}

function DeviceRow({ device, target, send }: { device: SpotifyDevice; target: string | null; send: Send }) {
  const Icon = device.kind === "computer" ? ComputerIcon : SpeakerIcon;
  const chosen = device.id === target;
  return (
    <li className="catalog-row" data-current={chosen || undefined}>
      <Icon size={20} className="flex-none text-[var(--muted)]" />
      <button
        type="button"
        className="flex min-w-0 flex-1 flex-col border-0 bg-transparent p-0 text-left text-inherit disabled:cursor-default"
        disabled={device.restricted}
        aria-pressed={chosen}
        aria-label={words.useDevice(device.name)}
        onClick={() => send({ type: "spotifyChooseDevice", id: device.id })}
      >
        <span className={`truncate ${chosen ? "font-semibold" : "font-medium"}`}>{device.name}</span>
        <span className="text-[12px] text-[var(--muted)]">
          {device.restricted ? words.cantControl : device.active ? words.playingHere : ""}
        </span>
      </button>
      {!device.restricted && !device.active && (
        <Button size="sm" variant="secondary" onPress={() => send({ type: "spotifyTransfer", id: device.id })}>
          {words.playHere}
        </Button>
      )}
    </li>
  );
}

/** "Spotify" in the Music tab: playlists, search and devices. Spotify's own apps play. */
export function SpotifyView({ spotify, send, onOpenConnections }: { spotify: Spotify; send: Send; onOpenConnections: () => void }) {
  const [text, setText] = useState(spotify.query);
  const timer = useRef<number | undefined>(undefined);
  useEffect(() => () => window.clearTimeout(timer.current), []);

  if (spotify.state !== "signed_in") {
    return (
      <div className="flex flex-col items-start gap-3">
        <p className="text-[var(--muted)]">{spotify.state === "not_set_up" ? words.notConnected : words.signedOut}</p>
        {spotify.error && <p className="text-[13px] text-[var(--danger)]">{spotifyErrorText(spotify.error, spotify.redirectUri)}</p>}
        <Button variant="primary" onPress={onOpenConnections}>
          {words.connect}
        </Button>
      </div>
    );
  }

  const search = (value: string) => {
    setText(value);
    window.clearTimeout(timer.current);
    // Wait for a pause in typing: every search is a call to Spotify.
    timer.current = window.setTimeout(() => send({ type: "spotifySearch", text: value }), 500);
  };
  const query = text.trim();
  const asked = query.replace(/\s+/g, " ").slice(0, 100);
  const target = targetName(spotify);

  let results = null;
  if (query) {
    if (spotify.searching || spotify.query !== asked) {
      results = (
        <p className="flex items-center gap-2 text-[var(--muted)]" aria-live="polite">
          <Spinner size="sm" />
          {words.searching}
        </p>
      );
    } else if (spotify.results.length === 0) {
      results = <p className="text-[var(--muted)]">{words.noMatch(query)}</p>;
    } else {
      results = (
        <ul className="song-list glass" aria-live="polite">
          {spotify.results.map((item) => (
            <ItemRow key={item.id} item={item} send={send} />
          ))}
        </ul>
      );
    }
  }

  return (
    <div className="flex flex-col gap-4">
      {spotify.error && (
        <div className="flex items-start gap-2 rounded-xl bg-[var(--field-background)] p-3" role="alert">
          <p className="flex-1 text-[13px] text-[var(--danger)]">{spotifyErrorText(spotify.error, spotify.redirectUri)}</p>
          <Button size="sm" variant="ghost" onPress={() => send({ type: "spotifyDismissError" })}>
            {strings.dismiss}
          </Button>
        </div>
      )}

      <SearchField aria-label={words.search} value={text} onChange={search}>
        <SearchField.Group>
          <SearchField.SearchIcon />
          <SearchField.Input placeholder={words.search} />
          <SearchField.ClearButton />
        </SearchField.Group>
      </SearchField>
      {results}

      <section className="flex flex-col gap-2">
        <div className="flex items-center justify-between gap-2">
          <h2 className="section-title">{words.devices}</h2>
          <Button size="sm" variant="ghost" isDisabled={spotify.loading} onPress={() => send({ type: "spotifyRefresh" })}>
            {spotify.loading ? <Spinner size="sm" /> : <RefreshIcon size={16} />}
            {words.refresh}
          </Button>
        </div>
        {spotify.devices.length === 0 ? (
          <p className="text-[13px] text-[var(--muted)]">{words.noDevices}</p>
        ) : (
          <ul className="song-list glass">
            {spotify.devices.map((device) => (
              <DeviceRow key={device.id} device={device} target={spotify.target} send={send} />
            ))}
          </ul>
        )}
        {target && <p className="px-2 text-[12px] text-[var(--muted)]">{words.playsOn(target)}</p>}
      </section>

      {!query && (
        <section className="flex flex-col gap-2">
          <h2 className="section-title">{words.playlists}</h2>
          {spotify.playlists.length === 0 ? (
            <p className="text-[13px] text-[var(--muted)]">{spotify.loading ? words.searching : words.noPlaylists}</p>
          ) : (
            <ul className="song-list glass">
              {spotify.playlists.map((item) => (
                <ItemRow key={item.id} item={item} send={send} />
              ))}
            </ul>
          )}
        </section>
      )}

      <p className="px-2 text-[11px] text-[var(--muted)]">{words.hearIt}</p>
      <p className="px-2 text-[11px] text-[var(--muted)]">{words.credit}</p>
    </div>
  );
}
