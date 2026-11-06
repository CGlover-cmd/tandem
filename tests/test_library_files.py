"""The music library's file access, on a temporary folder of invented files."""

from __future__ import annotations

from pathlib import Path

from tandem.engine.adapters import library_files as lf


def test_lists_audio_files_and_cover_folders(tmp_path: Path) -> None:
    album = tmp_path / "Example Band" / "Daybreak"
    album.mkdir(parents=True)
    (album / "01 Morning Light.mp3").write_bytes(b"x" * 10)
    (album / "02 Paper Boats.FLAC").write_bytes(b"x")
    (album / "notes.txt").write_text("not music")
    (album / "Cover.jpg").write_bytes(b"\xff\xd8\xff")
    hidden = tmp_path / ".cache"
    hidden.mkdir()
    (hidden / "skip.mp3").write_bytes(b"x")

    entries, covers = lf.list_files(str(tmp_path))

    names = sorted(Path(e.path).name for e in entries)
    assert names == ["01 Morning Light.mp3", "02 Paper Boats.FLAC"]
    assert next(e for e in entries if e.path.endswith(".mp3")).size == 10
    assert covers == {str(album)}


def test_cover_images_beside_the_files(tmp_path: Path) -> None:
    track = tmp_path / "song.wav"
    track.write_bytes(b"RIFF....WAVE")  # no embedded art
    assert lf.read_art(str(track)) is None
    (tmp_path / "folder.png").write_bytes(b"\x89PNG-invented")
    art = lf.read_art(str(track))
    assert art is not None
    assert (art.data, art.mimetype) == (b"\x89PNG-invented", "image/png")
    assert lf.read_art(str(tmp_path / "missing" / "x.mp3")) is None


def test_tag_value_cleanup() -> None:
    assert lf._int("3/12") == 3  # pyright: ignore[reportPrivateUsage]
    assert lf._int("") is None  # pyright: ignore[reportPrivateUsage]
    assert lf._int("x") is None  # pyright: ignore[reportPrivateUsage]
    assert lf._year("2021-05-01") == 2021  # pyright: ignore[reportPrivateUsage]
    assert lf._year(None) is None  # pyright: ignore[reportPrivateUsage]
    assert lf._is_cover("cover.jpg")  # pyright: ignore[reportPrivateUsage]
    assert not lf._is_cover("cover.gif")  # pyright: ignore[reportPrivateUsage]
    assert not lf._is_cover(".jpg")  # pyright: ignore[reportPrivateUsage]
