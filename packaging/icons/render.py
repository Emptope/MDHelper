"""Render the application icon from stylized RDF curves."""

from __future__ import annotations

import argparse
import math
from collections.abc import Callable
from pathlib import Path

from PIL import Image, ImageDraw

SIZE = 1024
ICO_SIZES = (16, 24, 32, 48, 64, 128, 256)
BACKGROUND = (248, 249, 253, 255)
RED = (242, 48, 63, 255)
BLUE = (57, 76, 232, 255)


def split_peak(
    value: float,
    center: float,
    left_width: float,
    right_width: float,
) -> float:
    """Return an asymmetric unit-height Gaussian peak."""

    width = left_width if value < center else right_width
    return math.exp(-0.5 * ((value - center) / width) ** 2)


def red_curve(value: float) -> float:
    """Return the red RDF curve with sharp and broad shells."""

    first = 0.96 * split_peak(value, 2.13, 0.075, 0.22)
    second = 0.28 * split_peak(value, 6.08, 0.57, 0.76)
    return first + second


def blue_curve(value: float) -> float:
    """Return the blue RDF curve with sharp and broad shells."""

    first = 0.38 * split_peak(value, 2.30, 0.10, 0.23)
    second = 0.47 * split_peak(value, 6.12, 0.64, 0.74)
    return first + second


def curve_points(curve: Callable[[float], float]) -> list[tuple[int, int]]:
    """Map an RDF curve into the icon drawing area."""

    left = 136
    right = SIZE - 76
    top = 126
    bottom = SIZE - 142
    value_min = 1.72
    value_max = 6.88
    points: list[tuple[int, int]] = []
    for pixel_x in range(left, right + 1, 2):
        ratio = (pixel_x - left) / (right - left)
        value = value_min + ratio * (value_max - value_min)
        height = min(curve(value), 1.0)
        pixel_y = round(bottom - height * (bottom - top))
        points.append((pixel_x, pixel_y))
    return points


def draw_curve(
    draw: ImageDraw.ImageDraw,
    points: list[tuple[int, int]],
    color: tuple[int, ...],
) -> None:
    """Draw a smooth flat curve with rounded endpoints."""

    width = 48
    radius = width // 2
    draw.line(points, fill=color, width=width, joint="curve")
    for point in (points[0], points[-1]):
        x, y = point
        draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=color)


def render() -> Image.Image:
    """Render the master application icon."""

    image = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    margin = 28
    draw.rounded_rectangle(
        (margin, margin, SIZE - margin, SIZE - margin),
        radius=210,
        fill=BACKGROUND,
    )
    draw_curve(draw, curve_points(red_curve), RED)
    draw_curve(draw, curve_points(blue_curve), BLUE)
    return image


def write_icons(output: Path) -> tuple[Path, Path]:
    """Write the PNG preview and multi-resolution Windows icon."""

    output.mkdir(parents=True, exist_ok=True)
    image = render()
    png_path = output / "mdhelper.png"
    ico_path = output / "mdhelper.ico"
    image.save(png_path, optimize=True)
    image.save(ico_path, sizes=[(size, size) for size in ICO_SIZES])
    return png_path, ico_path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    png_path, ico_path = write_icons(args.output)
    print(png_path)
    print(ico_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
