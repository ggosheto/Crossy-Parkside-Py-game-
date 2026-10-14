"""Logical UI coordinates on a high-resolution canvas."""

from pathlib import Path
import pygame
from .config import SCREEN_W

UI_SCALE = 2
FONT_ROOT = Path(__file__).resolve().parent.parent / "assets" / "fonts"


def scale_of(surface):
    return surface.get_width() / SCREEN_W


def rect_for(surface, rect):
    k = scale_of(surface)
    r = pygame.Rect(rect)
    return pygame.Rect(round(r.x * k), round(r.y * k), round(r.w * k), round(r.h * k))


def draw_rect(surface, color, rect, width=0, border_radius=0):
    k = scale_of(surface)
    return pygame.draw.rect(
        surface,
        color,
        rect_for(surface, rect),
        round(width * k),
        border_radius=round(border_radius * k),
    )


def draw_line(surface, color, start, end, width=1):
    k = scale_of(surface)
    return pygame.draw.line(
        surface,
        color,
        tuple(round(v * k) for v in start),
        tuple(round(v * k) for v in end),
        max(1, round(width * k)),
    )


def draw_circle(surface, color, center, radius, width=0):
    k = scale_of(surface)
    return pygame.draw.circle(
        surface,
        color,
        tuple(round(v * k) for v in center),
        max(1, round(radius * k)),
        round(width * k),
    )


def blit(surface, image, destination, native=False, logical_size=None):
    k = scale_of(surface)
    if logical_size is not None:
        size = tuple(max(1, round(v * k)) for v in logical_size)
        if image.get_size() != size:
            image = pygame.transform.smoothscale(image, size)
    elif not native and k != 1:
        image = pygame.transform.smoothscale(
            image, tuple(max(1, round(v * k)) for v in image.get_size())
        )
    pos = destination.topleft if isinstance(destination, pygame.Rect) else destination
    return surface.blit(image, tuple(round(v * k) for v in pos))


def load_font(size, bold=False):
    path = FONT_ROOT / ("DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf")
    if path.is_file():
        return pygame.font.Font(str(path), round(size * UI_SCALE))
    return pygame.font.SysFont(
        "segoeui,arial,dejavusans", round(size * UI_SCALE), bold=bold
    )
