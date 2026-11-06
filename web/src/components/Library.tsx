import { Button, Chip, ProgressBar, SearchField, Spinner } from "@heroui/react";
import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";

import { formatTime } from "../controls";
import {
  CloseIcon,
  FolderIcon,
  MusicIcon,
  NextIcon,
  PauseIcon,
  PlayIcon,
  PlayNextIcon,
  PlusIcon,
  PreviousIcon,
  RadioIcon,
  RefreshIcon,
  SpeakerIcon,
  StopIcon,
} from "../icons";
import {
  albumArtUrl,
  currentItem,
  folderName,
  groupByArtist,
  isSaved,
  playerPosition,
  stationDetails,
  upNext,
} from "../library";
import { strings } from "../strings";
import type { Command, Library, LibraryAlbum, LibrarySong, Player, QueueItem, Radio, Station } from "../types";

type Send = (command: Command) => void;
const words = strings.library;

/** An album's artwork from the library, or a drawn note (or radio) when there is none. */
export function AlbumArt({
  albumId,
  size,
  radio = false,
  className = "",
}: {
  albumId: string | null;
  size: number;
  radio?: boolean;
  className?: string;
}) {
  const [broken, setBroken] = useState<string | null>(null);
  const src = albumId && broken !== albumId ? albumArtUrl(window.location.search, albumId) : null;
  return (
    <span className={`library-art ${className}`} style={{ width: size, height: size }} aria-hidden="true">
      {src ? (
        <img src={src} alt="" draggable={false} loading="lazy" onError={() => setBroken(albumId)} />
      ) : radio ? (
        <RadioIcon size={Math.round(size * 0.45)} />
      ) : (
        <MusicIcon size={Math.round(size * 0.42)} />
      )}
    </span>
  );
}

function IconButton({ label, onPress, children, disabled = false }: {
  label: string;
  onPress: () => void;
  children: ReactNode;
  disabled?: boolean;
}) {
  return (
    <Button isIconOnly variant="ghost" size="sm" aria-label={label} onPress={onPress} isDisabled={disabled}>
      {children}
    </Button>
  );
}

function useTicking(active: boolean): number {
  const [now, setNow] = useState(() => performance.now());
  useEffect(() => {
    if (!active) return;
    const timer = window.setInterval(() => setNow(performance.now()), 500);
    return () => window.clearInterval(timer);
  }, [active]);
  return now;
}

/** Tandem's own player: what it plays, its transport, and where the sound goes. */
export function PlayerStrip({
  player,
  speakers,
  send,
  onOpenAudio,
}: {
  player: Player;
  speakers: number;
  send: Send;
  onOpenAudio: () => void;
}) {
  const item = currentItem(player);
  const [since, setSince] = useState(() => performance.now());
  useEffect(() => setSince(performance.now()), [player.position, player.state]);
  const now = useTicking(player.state === "playing");
  if (player.queue.length === 0) return null;
  const position = playerPosition(player, (now - since) / 1000);
  const playing = player.state === "playing";
  const control = (command: "play_pause" | "next" | "previous" | "stop") => send({ type: "player", command });
  const status =
    player.error ? words.failed : player.state === "loading" ? words.loading : player.state === "stopped" ? words.stopped : null;
  return (
    <section className="player-strip glass" aria-label={words.nowPlayingLabel}>
      <AlbumArt albumId={item?.art ?? null} radio={item?.kind === "radio"} size={56} className="library-art-small" />
      <div className="flex min-w-0 flex-1 flex-col gap-1">
        <p className="now-playing-app">{words.nowPlayingLabel}</p>
        <p className="truncate text-[15px] font-semibold">{item?.title ?? words.stopped}</p>
        <p className="truncate text-[12px] text-[var(--muted)]">
          {status ?? (item?.kind === "radio" ? words.live : [item?.artist, item?.album].filter(Boolean).join(" · "))}
        </p>
        {player.duration !== null && player.duration > 0 && item?.kind !== "radio" && (
          <div className="flex items-center gap-2">
            <ProgressBar
              aria-label={strings.music.of(formatTime(position), formatTime(player.duration))}
              value={position}
              maxValue={player.duration}
              size="sm"
              className="flex-1"
            >
              <ProgressBar.Track>
                <ProgressBar.Fill />
              </ProgressBar.Track>
            </ProgressBar>
            <span className="text-[11px] tabular-nums text-[var(--muted)]">
              {formatTime(position)} / {formatTime(player.duration)}
            </span>
          </div>
        )}
      </div>
      <div className="flex items-center gap-1" role="group" aria-label={words.queue}>
        <IconButton label={strings.music.previous} onPress={() => control("previous")} disabled={item === null}>
          <PreviousIcon size={20} />
        </IconButton>
        <Button
          isIconOnly
          variant="secondary"
          aria-label={playing ? strings.music.pause : strings.music.play}
          onPress={() => control("play_pause")}
          className="media-main"
        >
          {playing ? <PauseIcon size={22} /> : <PlayIcon size={22} />}
        </Button>
        <IconButton label={strings.music.next} onPress={() => control("next")} disabled={upNext(player).length === 0}>
          <NextIcon size={20} />
        </IconButton>
        <IconButton label={words.stop} onPress={() => control("stop")} disabled={player.state === "stopped"}>
          <StopIcon size={18} />
        </IconButton>
      </div>
      <Button variant={speakers > 0 ? "tertiary" : "secondary"} size="sm" onPress={onOpenAudio} className="player-speakers">
        <SpeakerIcon size={16} />
        <span>{speakers > 0 ? words.toSpeakers(speakers) : words.noSpeakers}</span>
      </Button>
    </section>
  );
}

function SongRow({ song, send, showAlbum }: { song: LibrarySong; send: Send; showAlbum: boolean }) {
  return (
    <li className="song-row">
      <button type="button" className="song-row-main" onClick={() => send({ type: "playSong", id: song.id })} aria-label={words.play(song.title)}>
        <span className="song-number">{showAlbum ? <AlbumArt albumId={song.albumId} size={32} className="library-art-tiny" /> : song.number ?? ""}</span>
        <span className="flex min-w-0 flex-col">
          <span className="truncate">{song.title}</span>
          {showAlbum && (
            <span className="truncate text-[12px] text-[var(--muted)]">
              {[song.artist, song.album].filter(Boolean).join(" · ")}
            </span>
          )}
        </span>
        <span className="song-duration">{song.duration !== null ? formatTime(song.duration) : ""}</span>
      </button>
      <IconButton label={words.playNext} onPress={() => send({ type: "queueSong", id: song.id, next: true })}>
        <PlayNextIcon size={18} />
      </IconButton>
      <IconButton label={words.addToQueue} onPress={() => send({ type: "queueSong", id: song.id, next: false })}>
        <PlusIcon size={18} />
      </IconButton>
    </li>
  );
}

function AlbumGrid({ albums, send }: { albums: LibraryAlbum[]; send: Send }) {
  return (
    <ul className="album-grid">
      {albums.map((album) => (
        <li key={album.id}>
          <button type="button" className="album-tile" onClick={() => send({ type: "openAlbum", id: album.id })}>
            <AlbumArt albumId={album.hasArt ? album.id : null} size={156} className="album-tile-art" />
            <span className="album-tile-title">{album.title}</span>
            <span className="album-tile-artist">{album.artist ?? words.unknownArtist}</span>
          </button>
        </li>
      ))}
    </ul>
  );
}

function AlbumView({ album, songs, send }: { album: LibraryAlbum; songs: LibrarySong[]; send: Send }) {
  return (
    <section className="flex flex-col gap-4" aria-label={album.title}>
      <div>
        <Button variant="ghost" size="sm" onPress={() => send({ type: "closeAlbum" })}>
          {words.back}
        </Button>
      </div>
      <div className="album-header">
        <AlbumArt albumId={album.hasArt ? album.id : null} size={176} className="album-header-art" />
        <div className="flex min-w-0 flex-col gap-2">
          <h2 className="music-title">{album.title}</h2>
          <p className="music-subtitle">
            {[album.artist ?? words.unknownArtist, album.year, words.songsCount(album.trackCount)].filter(Boolean).join(" · ")}
          </p>
          <div className="flex flex-wrap gap-2">
            <Button variant="primary" onPress={() => send({ type: "playAlbum", id: album.id })}>
              <PlayIcon size={16} />
              {words.playAlbum}
            </Button>
            <Button variant="secondary" onPress={() => send({ type: "queueAlbum", id: album.id, next: true })}>
              <PlayNextIcon size={16} />
              {words.playNext}
            </Button>
            <Button variant="secondary" onPress={() => send({ type: "queueAlbum", id: album.id, next: false })}>
              <PlusIcon size={16} />
              {words.addToQueue}
            </Button>
          </div>
        </div>
      </div>
      <ul className="song-list glass">
        {songs.map((song) => (
          <SongRow key={song.id} song={song} send={send} showAlbum={false} />
        ))}
      </ul>
    </section>
  );
}

/** "This PC": the music library. */
export function LibraryView({ library, send }: { library: Library; send: Send }) {
  const [text, setText] = useState(library.search.text);
  const [mode, setMode] = useState<"albums" | "artists">("albums");
  const [artist, setArtist] = useState<string | null | undefined>(undefined);
  const groups = useMemo(() => groupByArtist(library.albums), [library.albums]);
  const searching = text.trim().length > 0;
  const open = library.openAlbum;
  const openAlbum = open ? library.albums.find((a) => a.id === open.id) : undefined;

  const search = (value: string) => {
    setText(value);
    send({ type: "searchLibrary", text: value });
  };

  const header = (
    <div className="library-toolbar">
      <SearchField aria-label={words.search} value={text} onChange={search} className="library-search">
        <SearchField.Group>
          <SearchField.SearchIcon />
          <SearchField.Input placeholder={words.search} />
          <SearchField.ClearButton />
        </SearchField.Group>
      </SearchField>
      <div className="flex flex-wrap items-center gap-2" aria-label={words.folders}>
        {library.folders.map((folder) => (
          <Chip key={folder} size="sm" variant="soft" title={folder}>
            <FolderIcon size={14} />
            <span>{folderName(folder)}</span>
            <button
              type="button"
              className="chip-remove"
              aria-label={words.removeFolder(folder)}
              onClick={() => send({ type: "removeMusicFolder", folder })}
            >
              <CloseIcon size={12} />
            </button>
          </Chip>
        ))}
        <Button
          size="sm"
          variant="secondary"
          isDisabled={!library.canPickFolders || library.picking}
          onPress={() => send({ type: "addMusicFolder" })}
        >
          <PlusIcon size={14} />
          {library.picking ? words.adding : words.addFolder}
        </Button>
        {library.folders.length > 0 && (
          <IconButton label={words.rescan} onPress={() => send({ type: "rescanLibrary" })} disabled={library.scanning}>
            <RefreshIcon size={16} />
          </IconButton>
        )}
      </div>
    </div>
  );

  let body: ReactNode;
  if (library.folders.length === 0) {
    body = (
      <div className="empty-state glass">
        <span className="music-empty-icon">
          <FolderIcon size={28} />
        </span>
        <h2 className="text-[17px] font-semibold">{words.emptyTitle}</h2>
        <p className="max-w-md text-center text-[var(--muted)]">
          {library.canPickFolders ? words.emptyBody : words.noFolderPicker}
        </p>
      </div>
    );
  } else if (searching) {
    body =
      library.search.songs.length === 0 ? (
        <p className="py-8 text-center text-[var(--muted)]" aria-live="polite">
          {words.noMatch(text.trim())}
        </p>
      ) : (
        <ul className="song-list glass" aria-live="polite">
          {library.search.songs.map((song) => (
            <SongRow key={song.id} song={song} send={send} showAlbum />
          ))}
        </ul>
      );
  } else if (open && openAlbum) {
    body = <AlbumView album={openAlbum} songs={open.songs} send={send} />;
  } else {
    const shown = mode === "artists" && artist !== undefined ? groups.find((g) => g.name === artist)?.albums ?? [] : library.albums;
    body = (
      <div className="flex flex-col gap-3">
        <div className="flex items-center gap-2" role="group" aria-label={words.albums}>
          <Button size="sm" variant={mode === "albums" ? "secondary" : "ghost"} onPress={() => { setMode("albums"); setArtist(undefined); }}>
            {words.albums}
          </Button>
          <Button size="sm" variant={mode === "artists" ? "secondary" : "ghost"} onPress={() => setMode("artists")}>
            {words.artists}
          </Button>
          <span className="ml-auto text-[12px] text-[var(--muted)]" aria-live="polite">
            {library.scanning ? (
              <span className="flex items-center gap-2">
                <Spinner size="sm" />
                {words.scanning(library.scanned)}
              </span>
            ) : (
              words.summary(library.albums.length, library.songCount)
            )}
          </span>
        </div>
        {mode === "artists" && (
          <div className="flex flex-wrap gap-2" aria-label={words.artists}>
            <Button size="sm" variant={artist === undefined ? "secondary" : "ghost"} onPress={() => setArtist(undefined)}>
              {words.allArtists}
            </Button>
            {groups.map((group) => (
              <Button
                key={group.name ?? ""}
                size="sm"
                variant={artist === group.name ? "secondary" : "ghost"}
                onPress={() => setArtist(group.name)}
              >
                {group.name ?? words.unknownArtist}
              </Button>
            ))}
          </div>
        )}
        <AlbumGrid albums={shown} send={send} />
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-4">
      {header}
      {body}
    </div>
  );
}

function StationRow({ station, saved, send }: { station: Station; saved: boolean; send: Send }) {
  return (
    <li className="song-row">
      <button type="button" className="song-row-main" onClick={() => send({ type: "playStation", id: station.id })} aria-label={words.listen(station.name)}>
        <span className="song-number">
          <RadioIcon size={18} />
        </span>
        <span className="flex min-w-0 flex-col">
          <span className="truncate">{station.name}</span>
          <span className="truncate text-[12px] text-[var(--muted)]">{stationDetails(station, words.kbps)}</span>
        </span>
      </button>
      {saved ? (
        <Button size="sm" variant="ghost" onPress={() => send({ type: "removeStation", id: station.id })}>
          {words.remove}
        </Button>
      ) : (
        <Button size="sm" variant="ghost" onPress={() => send({ type: "saveStation", id: station.id })}>
          {words.save}
        </Button>
      )}
    </li>
  );
}

/** "Radio": search the open station directory, and saved stations. */
export function RadioView({ radio, send }: { radio: Radio; send: Send }) {
  const [text, setText] = useState(radio.query);
  const timer = useRef<number | undefined>(undefined);
  useEffect(() => () => window.clearTimeout(timer.current), []);

  const search = (value: string) => {
    setText(value);
    window.clearTimeout(timer.current);
    // Wait for a pause in typing: each search is a request to the public directory.
    timer.current = window.setTimeout(() => send({ type: "searchRadio", text: value }), 450);
  };

  const query = text.trim();
  return (
    <div className="flex flex-col gap-4">
      <SearchField aria-label={words.radioSearch} value={text} onChange={search}>
        <SearchField.Group>
          <SearchField.SearchIcon />
          <SearchField.Input placeholder={words.radioSearch} />
          <SearchField.ClearButton />
        </SearchField.Group>
      </SearchField>
      {query && (
        <section className="flex flex-col gap-2" aria-live="polite">
          {radio.searching ? (
            <p className="flex items-center gap-2 text-[var(--muted)]">
              <Spinner size="sm" />
              {words.radioSearching}
            </p>
          ) : radio.error ? (
            <p className="text-[var(--muted)]" role="alert">
              {words.radioUnavailable}
            </p>
          ) : radio.results.length === 0 && radio.query === query ? (
            <p className="text-[var(--muted)]">{words.radioNoMatch(query)}</p>
          ) : (
            <ul className="song-list glass">
              {radio.results.map((station) => (
                <StationRow key={station.id} station={station} saved={isSaved(radio.saved, station.id)} send={send} />
              ))}
            </ul>
          )}
        </section>
      )}
      <section className="flex flex-col gap-2">
        <h2 className="section-title">{words.radioSaved}</h2>
        {radio.saved.length === 0 ? (
          <p className="text-[13px] text-[var(--muted)]">{words.radioNoSaved}</p>
        ) : (
          <ul className="song-list glass">
            {radio.saved.map((station) => (
              <StationRow key={station.id} station={station} saved send={send} />
            ))}
          </ul>
        )}
      </section>
      <p className="px-2 text-[11px] text-[var(--muted)]">{words.radioCredit}</p>
    </div>
  );
}

function QueueRow({ item, current, send }: { item: QueueItem; current: boolean; send: Send }) {
  return (
    <li className="song-row" data-current={current ? "" : undefined}>
      <button type="button" className="song-row-main" onClick={() => send({ type: "playQueueItem", id: item.id })} aria-label={words.play(item.title)} aria-current={current ? "true" : undefined}>
        <span className="song-number">
          <AlbumArt albumId={item.art} radio={item.kind === "radio"} size={32} className="library-art-tiny" />
        </span>
        <span className="flex min-w-0 flex-col">
          <span className="truncate">{item.title}</span>
          <span className="truncate text-[12px] text-[var(--muted)]">
            {item.kind === "radio" ? words.live : [item.artist, item.album].filter(Boolean).join(" · ")}
          </span>
        </span>
      </button>
      <IconButton label={words.removeFromQueue(item.title)} onPress={() => send({ type: "removeQueueItem", id: item.id })}>
        <CloseIcon size={16} />
      </IconButton>
    </li>
  );
}

/** "Queue": what Tandem's player is playing and what comes next. */
export function QueueView({ player, send }: { player: Player; send: Send }) {
  if (player.queue.length === 0) {
    return (
      <div className="empty-state glass">
        <span className="music-empty-icon">
          <MusicIcon size={28} />
        </span>
        <p className="max-w-md text-center text-[var(--muted)]">{words.queueEmpty}</p>
      </div>
    );
  }
  return (
    <section className="flex flex-col gap-2" aria-label={words.queue}>
      <div className="flex items-center justify-between">
        <h2 className="section-title">{words.upNext}</h2>
        <Button size="sm" variant="ghost" onPress={() => send({ type: "clearQueue" })}>
          {words.clearQueue}
        </Button>
      </div>
      <ul className="song-list glass">
        {player.queue.map((item, index) => (
          <QueueRow key={item.id} item={item} current={index === player.index} send={send} />
        ))}
      </ul>
    </section>
  );
}
