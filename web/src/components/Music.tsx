import { Button, Chip, ProgressBar, Slider } from "@heroui/react";
import { useEffect, useState, type ReactNode } from "react";

import { formatTime } from "../controls";
import {
  MusicIcon,
  NextIcon,
  PauseIcon,
  PlayIcon,
  PreviousIcon,
  SkipBackwardIcon,
  SkipForwardIcon,
} from "../icons";
import {
  allows,
  artworkUrl,
  canSkip,
  isPlaying,
  musicPosition,
  musicSubtitle,
  progressKind,
  seekTarget,
} from "../music";
import { strings } from "../strings";
import type { Command, Music, MusicCommand } from "../types";

type Send = (command: Command) => void;

function useNow(active: boolean): number {
  const [now, setNow] = useState(() => performance.now());
  useEffect(() => {
    if (!active) return;
    const timer = window.setInterval(() => setNow(performance.now()), 500);
    return () => window.clearInterval(timer);
  }, [active]);
  return now;
}

/** Count on from the last position the app reported, while it plays. */
function useMusicPosition(music: Music): number | null {
  const [since, setSince] = useState(() => performance.now());
  useEffect(() => setSince(performance.now()), [music.position, music.state]);
  const now = useNow(isPlaying(music));
  return musicPosition(music, (now - since) / 1000);
}

/** The artwork, or a drawn note when there is none (or it won't load). */
function Artwork({ music, size, className }: { music: Music; size: number; className: string }) {
  const [failed, setFailed] = useState<number | null>(null);
  const version = music.artwork;
  const src = version !== null && failed !== version ? artworkUrl(window.location.search, version) : null;
  return (
    <div className={className} style={{ width: size, height: size }} aria-hidden="true">
      {src ? (
        <img src={src} alt="" draggable={false} onError={() => setFailed(version)} />
      ) : (
        <MusicIcon size={Math.round(size * 0.42)} />
      )}
    </div>
  );
}

function MusicButton({
  music,
  command,
  send,
  main = false,
  children,
  label,
}: {
  music: Music;
  command: MusicCommand;
  send: Send;
  main?: boolean;
  children: ReactNode;
  label: string;
}) {
  return (
    <Button
      isIconOnly
      variant={main ? "secondary" : "ghost"}
      size={main ? "lg" : "md"}
      aria-label={label}
      isDisabled={!allows(music, command)}
      onPress={() => send({ type: "music", command })}
      className={main ? "media-main" : undefined}
    >
      {children}
    </Button>
  );
}

function PlayPauseButton({ music, send, main, size }: { music: Music; send: Send; main?: boolean; size: number }) {
  const playing = isPlaying(music);
  return (
    <MusicButton
      music={music}
      command="play_pause"
      send={send}
      main={main}
      label={playing ? strings.music.pause : strings.music.play}
    >
      {playing ? <PauseIcon size={size} /> : <PlayIcon size={size} />}
    </MusicButton>
  );
}

function Progress({ music, send }: { music: Music; send: Send }) {
  const position = useMusicPosition(music);
  // Follow the app, but don't fight the user while they drag.
  const [dragging, setDragging] = useState<number | null>(null);
  const kind = progressKind(music);
  if (kind === "live" || position === null || music.duration === null) {
    return (
      <div className="flex">
        <Chip size="sm" variant="soft" color="accent">
          {strings.music.live}
        </Chip>
      </div>
    );
  }
  const shown = dragging ?? position;
  const times = (
    <div className="flex justify-between text-[11px] tabular-nums text-[var(--muted)]">
      <span>{formatTime(shown)}</span>
      <span>-{formatTime(music.duration - shown)}</span>
    </div>
  );
  const label = strings.music.of(formatTime(shown), formatTime(music.duration));
  if (kind === "bar") {
    return (
      <div className="flex flex-col gap-1">
        <ProgressBar aria-label={label} value={shown} maxValue={music.duration} size="sm">
          <ProgressBar.Track>
            <ProgressBar.Fill />
          </ProgressBar.Track>
        </ProgressBar>
        {times}
      </div>
    );
  }
  return (
    <div className="flex flex-col gap-1">
      <Slider
        aria-label={strings.music.position}
        minValue={0}
        maxValue={music.duration}
        step={1}
        value={shown}
        onChange={(value) => setDragging(Array.isArray(value) ? (value[0] ?? 0) : value)}
        onChangeEnd={(value) => {
          const next = Array.isArray(value) ? (value[0] ?? 0) : value;
          setDragging(null);
          send({ type: "musicSeek", position: next });
        }}
      >
        <Slider.Track>
          <Slider.Fill />
          <Slider.Thumb />
        </Slider.Track>
      </Slider>
      {times}
    </div>
  );
}

/** The Music tab: what any app on the PC is playing, with its controls. */
export function MusicPanel({ music, send }: { music: Music | null; send: Send }) {
  if (music === null) {
    return (
      <div className="empty-state glass">
        <span className="music-empty-icon">
          <MusicIcon size={28} />
        </span>
        <h2 className="text-[17px] font-semibold">{strings.music.nothingTitle}</h2>
        <p className="max-w-md text-center text-[var(--muted)]">{strings.music.nothingBody}</p>
      </div>
    );
  }
  const title = music.title ?? strings.music.untitled;
  const subtitle = musicSubtitle(music);
  return (
    <div className="flex flex-col gap-4">
      <section className="music-card glass" aria-label={title}>
        <Artwork music={music} size={220} className="music-art" />
        <div className="music-details">
          <p className="now-playing-app">{strings.music.from(music.app ?? strings.music.anApp)}</p>
          <h2 className="music-title">{title}</h2>
          {subtitle && <p className="music-subtitle">{subtitle}</p>}
          <Progress music={music} send={send} />
          <div className="flex items-center gap-2" role="group" aria-label={strings.music.title}>
            <MusicButton music={music} command="previous" send={send} label={strings.music.previous}>
              <PreviousIcon size={22} />
            </MusicButton>
            <PlayPauseButton music={music} send={send} main size={26} />
            <MusicButton music={music} command="next" send={send} label={strings.music.next}>
              <NextIcon size={22} />
            </MusicButton>
          </div>
        </div>
      </section>
      <p className="px-2 text-[12px] text-[var(--muted)]">{strings.music.note}</p>
    </div>
  );
}

/** A compact bar at the bottom of the window, on the other tabs. */
export function NowPlayingBar({ music, send, onOpen }: { music: Music; send: Send; onOpen: () => void }) {
  const title = music.title ?? strings.music.untitled;
  const subtitle = musicSubtitle(music) ?? music.app;
  return (
    <div className="now-playing-bar glass" role="region" aria-label={strings.music.bar(title)}>
      <button type="button" className="now-playing-bar-open" onClick={onOpen} aria-label={strings.music.bar(title)}>
        <Artwork music={music} size={40} className="music-art music-art-small" />
        <span className="flex min-w-0 flex-col text-left">
          <span className="now-playing-bar-title">{title}</span>
          {subtitle && <span className="now-playing-bar-subtitle">{subtitle}</span>}
        </span>
      </button>
      <PlayPauseButton music={music} send={send} size={20} />
      <MusicButton music={music} command="next" send={send} label={strings.music.next}>
        <NextIcon size={18} />
      </MusicButton>
    </div>
  );
}

const SKIP_SECONDS = 15;

/** A speaker's remote while it plays this PC's sound: the PC's app is what plays, so the
 *  buttons drive it (previous, back 15 s, play or pause, forward 15 s, next). */
export function PcPlaybackCard({ music, send }: { music: Music | null; send: Send }) {
  if (music === null) {
    return (
      <section className="now-playing glass" aria-label={strings.music.nothingTitle}>
        <p className="now-playing-title">{strings.music.nothingTitle}</p>
        <p className="now-playing-subtitle">{strings.speakerRemote.nothingBody}</p>
      </section>
    );
  }
  return <PcPlaybackControls music={music} send={send} />;
}

function PcPlaybackControls({ music, send }: { music: Music; send: Send }) {
  const position = useMusicPosition(music);
  const title = music.title ?? strings.music.untitled;
  const subtitle = musicSubtitle(music);
  const skip = canSkip(music) && position !== null;
  const seek = (by: number) => {
    if (position !== null) send({ type: "musicSeek", position: seekTarget(music, position, by) });
  };
  return (
    <section className="now-playing glass" aria-label={title}>
      <div className="flex items-center gap-3">
        <Artwork music={music} size={56} className="music-art music-art-small" />
        <div className="min-w-0 flex-1">
          <p className="now-playing-app">{strings.music.from(music.app ?? strings.music.anApp)}</p>
          <p className="now-playing-title">{title}</p>
          {subtitle && <p className="now-playing-subtitle">{subtitle}</p>}
        </div>
      </div>
      <div className="flex items-center justify-center gap-1" role="group" aria-label={strings.speakerRemote.controls}>
        <MusicButton music={music} command="previous" send={send} label={strings.music.previous}>
          <PreviousIcon size={22} />
        </MusicButton>
        {skip && (
          <Button isIconOnly variant="ghost" aria-label={strings.speakerRemote.back(SKIP_SECONDS)} onPress={() => seek(-SKIP_SECONDS)}>
            <SkipBackwardIcon size={22} />
          </Button>
        )}
        <PlayPauseButton music={music} send={send} main size={26} />
        {skip && (
          <Button isIconOnly variant="ghost" aria-label={strings.speakerRemote.forward(SKIP_SECONDS)} onPress={() => seek(SKIP_SECONDS)}>
            <SkipForwardIcon size={22} />
          </Button>
        )}
        <MusicButton music={music} command="next" send={send} label={strings.music.next}>
          <NextIcon size={22} />
        </MusicButton>
      </div>
    </section>
  );
}
