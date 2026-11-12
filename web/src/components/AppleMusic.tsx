import { SearchField, Spinner } from "@heroui/react";
import { useEffect, useRef, useState } from "react";

import { formatTime } from "../controls";
import { MusicIcon } from "../icons";
import { badgeUrl, catalogArtUrl } from "../catalog";
import { strings } from "../strings";
import type { Catalog, CatalogAlbum, CatalogSong, Command } from "../types";

type Send = (command: Command) => void;
const words = strings.appleMusic;

/** A result's artwork, fetched from Apple through Tandem; a drawn note if there is none. */
function CatalogArt({ id, hasArt, size }: { id: string; hasArt: boolean; size: number }) {
  const [broken, setBroken] = useState(false);
  return (
    <span className="library-art" style={{ width: size, height: size }} aria-hidden="true">
      {hasArt && !broken ? (
        <img src={catalogArtUrl(window.location.search, id)} alt="" loading="lazy" draggable={false} onError={() => setBroken(true)} />
      ) : (
        <MusicIcon size={Math.round(size * 0.42)} />
      )}
    </span>
  );
}

/** Apple's "Listen on Apple Music" badge as the way to open a result (Apple's terms ask for the
 *  badge next to its artwork). Without a connection to Apple, plain words instead. */
function OpenButton({ id, title, send }: { id: string; title: string; send: Send }) {
  const [noBadge, setNoBadge] = useState(false);
  return (
    <button type="button" className="apple-badge-button" aria-label={words.open(title)} onClick={() => send({ type: "openInAppleMusic", id })}>
      {noBadge ? (
        <span className="apple-badge-text">{words.openShort}</span>
      ) : (
        <img src={badgeUrl(window.location.search)} alt="" height={34} draggable={false} onError={() => setNoBadge(true)} />
      )}
    </button>
  );
}

function SongResult({ song, send }: { song: CatalogSong; send: Send }) {
  return (
    <li className="catalog-row">
      <CatalogArt id={song.id} hasArt={song.hasArt} size={48} />
      <span className="flex min-w-0 flex-1 flex-col">
        <span className="truncate font-medium">{song.title}</span>
        <span className="truncate text-[12px] text-[var(--muted)]">
          {[song.artist, song.album, song.duration !== null ? formatTime(song.duration) : null].filter(Boolean).join(" · ")}
        </span>
      </span>
      <OpenButton id={song.id} title={song.title} send={send} />
    </li>
  );
}

function AlbumResult({ album, send }: { album: CatalogAlbum; send: Send }) {
  return (
    <li className="catalog-album">
      <CatalogArt id={album.id} hasArt={album.hasArt} size={140} />
      <span className="album-tile-title">{album.title}</span>
      <span className="album-tile-artist">{[album.artist, album.year].filter(Boolean).join(" · ")}</span>
      <OpenButton id={album.id} title={album.title} send={send} />
    </li>
  );
}

/** "Apple Music": search Apple's catalog and open results in the Apple Music app. */
export function AppleMusicView({ catalog, send }: { catalog: Catalog; send: Send }) {
  const [text, setText] = useState(catalog.query);
  const timer = useRef<number | undefined>(undefined);
  useEffect(() => () => window.clearTimeout(timer.current), []);

  const search = (value: string) => {
    setText(value);
    window.clearTimeout(timer.current);
    // Wait for a pause in typing: Apple allows about 20 searches a minute.
    timer.current = window.setTimeout(() => send({ type: "searchCatalog", text: value }), 600);
  };

  const query = text.trim();
  // The words the engine searches for (it folds spaces and keeps 100 characters). Until its
  // results are for these words, the typed search is still on its way.
  const asked = query.replace(/\s+/g, " ").slice(0, 100);
  let results = null;
  if (query) {
    if (catalog.searching || catalog.query !== asked) {
      results = (
        <p className="flex items-center gap-2 text-[var(--muted)]" aria-live="polite">
          <Spinner size="sm" />
          {words.searching}
        </p>
      );
    } else if (catalog.error) {
      results = (
        <p className="text-[var(--muted)]" role="alert">
          {catalog.error === "busy" ? words.busy : words.unavailable}
        </p>
      );
    } else if (catalog.songs.length === 0) {
      results = <p className="text-[var(--muted)]">{words.noMatch(query)}</p>;
    } else {
      results = (
        <div className="flex flex-col gap-4" aria-live="polite">
          {catalog.albums.length > 0 && (
            <section className="flex flex-col gap-2">
              <h2 className="section-title">{words.albums}</h2>
              <ul className="catalog-albums">
                {catalog.albums.map((album) => (
                  <AlbumResult key={album.id} album={album} send={send} />
                ))}
              </ul>
            </section>
          )}
          <section className="flex flex-col gap-2">
            <h2 className="section-title">{words.songs}</h2>
            <ul className="song-list glass">
              {catalog.songs.map((song) => (
                <SongResult key={song.id} song={song} send={send} />
              ))}
            </ul>
          </section>
        </div>
      );
    }
  }

  return (
    <div className="flex flex-col gap-4">
      <p className="text-[13px] text-[var(--muted)]">{words.about}</p>
      <SearchField aria-label={words.search} value={text} onChange={search}>
        <SearchField.Group>
          <SearchField.SearchIcon />
          <SearchField.Input placeholder={words.search} />
          <SearchField.ClearButton />
        </SearchField.Group>
      </SearchField>
      {results}
      <p className="px-2 text-[11px] text-[var(--muted)]">{words.noLibrary}</p>
      <p className="px-2 text-[11px] text-[var(--muted)]">{words.credit}</p>
    </div>
  );
}
