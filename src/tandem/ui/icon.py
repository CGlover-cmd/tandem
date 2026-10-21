"""Tandem's icon: two overlapping circles, drawn at runtime so the repo needs no binary file."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

_BLUE = (0, 102, 204, 255)
_SKY = (90, 200, 250, 220)
_LENS = (255, 255, 255, 120)


def draw_icon(size: int = 64) -> Image.Image:
    scale = 4  # draw large, then shrink, for smooth edges
    big = size * scale
    image = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    radius = big * 0.30
    centre_y = big * 0.5

    def circle(layer: Image.Image, x: float, colour: tuple[int, int, int, int]) -> None:
        ImageDraw.Draw(layer).ellipse(
            (x - radius, centre_y - radius, x + radius, centre_y + radius), fill=colour
        )

    circle(image, big * 0.36, _BLUE)
    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    circle(overlay, big * 0.64, _SKY)
    image = Image.alpha_composite(image, overlay)
    lens = Image.new("RGBA", image.size, (0, 0, 0, 0))
    half = radius * 0.55 / 2
    ImageDraw.Draw(lens).ellipse(
        (big * 0.5 - half, centre_y - half * 2, big * 0.5 + half, centre_y + half * 2), fill=_LENS
    )
    image = Image.alpha_composite(image, lens)
    return image.resize((size, size), Image.Resampling.LANCZOS)


def write_ico(path: Path) -> Path:
    """Save a multi-size .ico for the window and taskbar."""
    path.parent.mkdir(parents=True, exist_ok=True)
    draw_icon(256).save(path, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (256, 256)])
    return path
