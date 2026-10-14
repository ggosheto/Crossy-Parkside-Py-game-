"""Procedural isometric models. Projection and camera belong to the renderer."""

from dataclasses import dataclass
import math
from functools import lru_cache
import pygame
from .config import COLS, CHARACTERS
from .model import Terrain


def shade(c, k):
    return tuple(max(0, min(255, int(v * k))) for v in c)


@dataclass
class Projection:
    ox: float = 460
    oy: float = 650
    sx: float = 36
    sy: float = 18
    sz: float = 45

    def point(self, x, y, z=0):
        return self.ox + (x - y) * self.sx, self.oy - (x + y) * self.sy - z * self.sz

    def box(self, s, x, y, z, w, d, h, color, edge=False):
        p = [
            self.point(x, y, z),
            self.point(x + w, y, z),
            self.point(x + w, y + d, z),
            self.point(x, y + d, z),
        ]
        q = [
            self.point(x, y, z + h),
            self.point(x + w, y, z + h),
            self.point(x + w, y + d, z + h),
            self.point(x, y + d, z + h),
        ]
        # The near corner is p0: both visible walls meet there.
        pygame.draw.polygon(s, shade(color, 0.70), [p[3], p[0], q[0], q[3]])
        pygame.draw.polygon(s, shade(color, 0.87), [p[0], p[1], q[1], q[0]])
        pygame.draw.polygon(s, shade(color, 1.08), q)
        if edge:
            pygame.draw.lines(s, shade(color, 1.18), True, q, 1)

    def shadow(self, s, x, y, w=1, d=1, alpha=45):
        points = [
            self.point(x - 0.12, y - 0.12, 0.01),
            self.point(x + w + 0.12, y - 0.12, 0.01),
            self.point(x + w + 0.12, y + d + 0.12, 0.01),
            self.point(x - 0.12, y + d + 0.12, 0.01),
        ]
        # Tiny local alpha surfaces avoid allocating a full-screen layer per object.
        xs, ys = zip(*points)
        left, top = int(min(xs)) - 2, int(min(ys)) - 2
        layer = pygame.Surface(
            (int(max(xs) - min(xs)) + 5, int(max(ys) - min(ys)) + 5), pygame.SRCALPHA
        )
        pygame.draw.polygon(
            layer, (27, 45, 41, alpha), [(a - left, b - top) for a, b in points]
        )
        s.blit(layer, (left, top))

    def line(self, s, color, start, end, width=1):
        pygame.draw.line(s, color, self.point(*start), self.point(*end), width)


def face_eyes(
    s, p, cx, y, z, color=(39, 49, 57), gap=0.16, width=0.075, height=0.10, glint=True
):
    """Both eyes share one face plane, height and distance from the head centre."""
    for side in (-1, 1):
        x = cx + side * gap - width / 2
        p.box(s, x, y, z, width, 0.018, height, color)
        if glint:
            p.box(
                s,
                x + width * 0.28,
                y - 0.009,
                z + height * 0.59,
                width * 0.26,
                0.012,
                height * 0.23,
                (252, 252, 238),
            )


def chicken(s, p, x, y, z, char, t=0):
    b = p.box
    col = char.color
    acc = char.accent
    # Feet, tail, full body, separate head, two wings and comb.
    for dx in (0.22, 0.58):
        b(s, x + dx, y + 0.3, z, 0.13, 0.3, 0.12, (232, 170, 70))
    b(s, x + 0.12, y + 0.16, z + 0.12, 0.74, 0.66, 0.53, col, True)
    b(s, x + 0.20, y + 0.02, z + 0.50, 0.57, 0.48, 0.46, col, True)
    b(s, x + 0.10, y + 0.70, z + 0.35, 0.25, 0.3, 0.33, col)
    b(s, x + 0.06, y + 0.28, z + 0.29, 0.13, 0.38, 0.30, (228, 222, 204))
    b(s, x + 0.77, y + 0.28, z + 0.29, 0.13, 0.38, 0.30, (238, 231, 211))
    for dy in (0.1, 0.23, 0.36):
        b(s, x + 0.44, y + dy, z + 0.96, 0.14, 0.12, 0.17, acc)
    b(s, x + 0.40, y - 0.15, z + 0.57, 0.25, 0.21, 0.16, (247, 190, 79))
    b(s, x + 0.47, y - 0.11, z + 0.43, 0.12, 0.12, 0.14, acc)
    face_eyes(s, p, x + 0.485, y - 0.002, z + 0.75)


def bunny(s, p, x, y, z, char, t=0):
    b = p.box
    col = char.color
    acc = char.accent
    b(s, x + 0.15, y + 0.2, z, 0.7, 0.65, 0.55, col, True)
    b(s, x + 0.21, y + 0.06, z + 0.4, 0.56, 0.52, 0.5, col, True)
    for dx in (0.25, 0.58):
        b(s, x + dx, y + 0.25, z + 0.9, 0.15, 0.19, 0.62, col, True)
        b(s, x + dx + 0.025, y + 0.235, z + 1.01, 0.10, 0.035, 0.43, acc)
    for dx in (0.18, 0.59):
        b(s, x + dx, y + 0.07, z, 0.23, 0.35, 0.13, (230, 208, 211))
    b(s, x + 0.4, y - 0.02, z + 0.56, 0.17, 0.08, 0.12, acc)
    face_eyes(s, p, x + 0.49, y + 0.038, z + 0.71, gap=0.165, width=0.07)
    b(s, x + 0.27, y + 0.72, z + 0.23, 0.27, 0.25, 0.27, (255, 242, 233))


def robot(s, p, x, y, z, char, t=0):
    b = p.box
    col = char.color
    acc = char.accent
    for dx in (0.22, 0.57):
        b(s, x + dx, y + 0.22, z, 0.2, 0.37, 0.14, (69, 96, 106))
    b(s, x + 0.2, y + 0.16, z + 0.17, 0.6, 0.57, 0.40, col, True)
    b(s, x + 0.13, y + 0.08, z + 0.61, 0.75, 0.63, 0.43, col, True)
    b(s, x + 0.20, y + 0.055, z + 0.72, 0.61, 0.025, 0.21, (30, 57, 67))
    face_eyes(
        s,
        p,
        x + 0.505,
        y + 0.029,
        z + 0.78,
        acc,
        gap=0.175,
        width=0.10,
        height=0.07,
        glint=False,
    )
    for dx in (0.07, 0.83):
        b(s, x + dx, y + 0.25, z + 0.29, 0.1, 0.25, 0.30, (99, 133, 146))
    b(s, x + 0.42, y + 0.33, z + 1.04, 0.08, 0.08, 0.2, (63, 99, 113))
    b(s, x + 0.38, y + 0.29, z + 1.24, 0.16, 0.16, 0.1, acc)
    b(s, x + 0.40, y + 0.13, z + 0.33, 0.17, 0.03, 0.13, acc)


def fox(s, p, x, y, z, char, t=0):
    b = p.box
    c = char.color
    for dx in (0.23, 0.58):
        b(s, x + dx, y + 0.2, z, 0.17, 0.43, 0.14, (67, 57, 49))
    b(s, x + 0.15, y + 0.16, z + 0.13, 0.7, 0.65, 0.47, c, True)
    b(s, x + 0.20, y + 0.01, z + 0.53, 0.6, 0.51, 0.43, c, True)
    for dx in (0.24, 0.61):
        b(s, x + dx, y + 0.23, z + 0.96, 0.15, 0.19, 0.27, c, True)
        b(s, x + dx + 0.03, y + 0.217, z + 1.03, 0.09, 0.025, 0.13, (79, 60, 51))
    b(s, x + 0.33, y - 0.13, z + 0.55, 0.34, 0.16, 0.2, (253, 239, 209))
    b(s, x + 0.445, y - 0.155, z + 0.62, 0.11, 0.035, 0.09, (51, 50, 51))
    face_eyes(s, p, x + 0.5, y - 0.012, z + 0.77, gap=0.17)
    b(s, x + 0.32, y + 0.74, z + 0.18, 0.36, 0.49, 0.40, c, True)
    b(s, x + 0.32, y + 1.10, z + 0.18, 0.36, 0.15, 0.40, (252, 235, 208))


def penguin(s, p, x, y, z, char, t=0):
    b = p.box
    c = char.color
    for dx in (0.19, 0.6):
        b(s, x + dx, y + 0.06, z, 0.22, 0.34, 0.1, char.accent)
    b(s, x + 0.18, y + 0.14, z + 0.1, 0.64, 0.62, 0.57, c, True)
    b(s, x + 0.22, y + 0.105, z + 0.19, 0.56, 0.04, 0.38, (241, 236, 218))
    b(s, x + 0.20, y + 0.08, z + 0.67, 0.60, 0.51, 0.38, c, True)
    b(s, x + 0.23, y + 0.059, z + 0.69, 0.54, 0.027, 0.30, (245, 240, 224))
    for dx in (0.06, 0.83):
        b(s, x + dx, y + 0.32, z + 0.24, 0.11, 0.34, 0.32, c)
    b(s, x + 0.4, y - 0.075, z + 0.72, 0.20, 0.14, 0.12, char.accent)
    face_eyes(s, p, x + 0.5, y + 0.038, z + 0.86, gap=0.17)


def turtle(s, p, x, y, z, char, t=0):
    b = p.box
    c = char.color
    for dx in (0.12, 0.68):
        for dy in (0.12, 0.65):
            b(s, x + dx, y + dy, z, 0.21, 0.23, 0.13, c)
    b(s, x + 0.12, y + 0.17, z + 0.12, 0.76, 0.70, 0.29, (79, 120, 84), True)
    b(s, x + 0.24, y + 0.27, z + 0.41, 0.52, 0.5, 0.17, (111, 154, 93), True)
    for dx in (0.29, 0.51):
        b(s, x + dx, y + 0.30, z + 0.58, 0.2, 0.38, 0.025, (143, 181, 109), True)
    b(s, x + 0.28, y - 0.10, z + 0.17, 0.44, 0.34, 0.30, c, True)
    face_eyes(s, p, x + 0.5, y - 0.12, z + 0.34, gap=0.147, width=0.065, height=0.075)
    b(s, x + 0.44, y - 0.115, z + 0.24, 0.12, 0.025, 0.04, (64, 101, 75))


MODELS = {
    "Chicken": chicken,
    "Bunny": bunny,
    "Robot": robot,
    "Fox": fox,
    "Penguin": penguin,
    "Turtle": turtle,
}


@dataclass(frozen=True)
class Voxel:
    x: float
    y: float
    z: float
    w: float
    d: float
    h: float
    color: tuple
    edge: bool = False


class VoxelCollector:
    def __init__(self):
        self.parts = []

    def box(self, s, x, y, z, w, d, h, color, edge=False):
        self.parts.append(Voxel(x, y, z, w, d, h, color, edge))


def rotate_point(x, y, facing):
    return {
        "down": (x, y),
        "up": (1 - x, 1 - y),
        "right": (1 - y, x),
        "left": (y, 1 - x),
    }[facing]


@lru_cache(maxsize=24)
def model_voxels(char, facing="down"):
    collector = VoxelCollector()
    MODELS[char.name](None, collector, 0, 0, 0, char)
    result = []
    for v in collector.parts:
        points = [
            rotate_point(xx, yy, facing)
            for xx, yy in [
                (v.x, v.y),
                (v.x + v.w, v.y),
                (v.x + v.w, v.y + v.d),
                (v.x, v.y + v.d),
            ]
        ]
        xs, ys = zip(*points)
        result.append(
            Voxel(
                min(xs),
                min(ys),
                v.z,
                max(xs) - min(xs),
                max(ys) - min(ys),
                v.h,
                v.color,
                v.edge,
            )
        )
    return tuple(result)


@lru_cache(maxsize=24)
def ordered_model(char, facing="down"):
    """Order intersecting projected cuboids by their actual separation in 3D.

    A centre-only sort can paint a large face plate over one of its eyes.
    Face attachments and glints instead follow the solid behind them.
    """
    parts = model_voxels(char, facing)

    def bounds(v):
        pts = [
            (2 * (x - y), -(x + y) - 2.5 * z)
            for x in (v.x, v.x + v.w)
            for y in (v.y, v.y + v.d)
            for z in (v.z, v.z + v.h)
        ]
        xx, yy = zip(*pts)
        return min(xx), min(yy), max(xx), max(yy)

    def behind(a, b):
        return (
            a.x >= b.x + b.w - 1e-8
            or a.y >= b.y + b.d - 1e-8
            or a.z + a.h <= b.z + 1e-8
        )

    rectangles = [bounds(v) for v in parts]
    edges = [set() for _ in parts]
    indegree = [0 for _ in parts]
    for i, a in enumerate(parts):
        for j in range(i + 1, len(parts)):
            b = parts[j]
            ra, rb = rectangles[i], rectangles[j]
            if ra[2] <= rb[0] or rb[2] <= ra[0] or ra[3] <= rb[1] or rb[3] <= ra[1]:
                continue
            ab, ba = behind(a, b), behind(b, a)
            if ab and not ba:
                edges[i].add(j)
                indegree[j] += 1
            elif ba and not ab:
                edges[j].add(i)
                indegree[i] += 1
    pending = set(range(len(parts)))
    order = []
    while pending:
        ready = [i for i in pending if indegree[i] == 0] or list(pending)
        i = max(
            ready,
            key=lambda k: parts[k].x
            + parts[k].w / 2
            + parts[k].y
            + parts[k].d / 2
            - parts[k].z * 0.08,
        )
        pending.remove(i)
        order.append(parts[i])
        for j in edges[i]:
            indegree[j] -= 1
    return tuple(order)


def character(s, p, char, x, y, z=0, t=0, facing="down"):
    p.shadow(s, x + 0.12, y + 0.12, 0.8, 0.8, 65)
    for v in ordered_model(char, facing):
        p.box(s, x + v.x, y + v.y, z + v.z, v.w, v.d, v.h, v.color, v.edge)


def portrait(char, size, t=0):
    phase = max(0, min(15, int((math.sin(t * 2.4) + 1) * 7.5)))
    return portrait_frame(char, tuple(size), phase)


@lru_cache(maxsize=48)
def portrait_frame(char, size, phase):
    k = max(size[0] / 240, size[1] / 260) * 2
    s = pygame.Surface((math.ceil(240 * k), math.ceil(260 * k)), pygame.SRCALPHA)
    p = Projection(120 * k, 215 * k, 72 * k, 36 * k, 90 * k)
    character(s, p, char, -0.5, -0.5, 0.07 + (phase / 7.5 - 1) * 0.035)
    return pygame.transform.smoothscale(s, size)


def tree(s, p, x, y, variant=0):
    b = p.box
    p.shadow(s, x - 0.05, y - 0.1, 1.2, 1.1, 70)
    b(s, x + 0.4, y + 0.4, 0, 0.19, 0.19, 0.78, (132, 101, 72))
    b(s, x + 0.26, y + 0.4, 0.45, 0.45, 0.14, 0.10, (132, 101, 72))
    color = (79, 137, 87) if variant % 2 else (79, 151, 113)
    b(s, x + 0.07, y + 0.05, 0.65, 0.85, 0.85, 0.65, color, True)
    b(s, x + 0.20, y + 0.16, 1.26, 0.63, 0.65, 0.44, shade(color, 1.09), True)
    b(s, x + 0.31, y + 0.28, 1.70, 0.4, 0.43, 0.25, shade(color, 1.17))
    b(s, x + 0.10, y + 0.08, 0.88, 0.19, 0.22, 0.2, shade(color, 1.13))


def car(s, p, body, y, direction, t):
    b = p.box
    x = body.x
    w = body.w
    c = body.color
    p.shadow(s, x, y + 0.14, w, 0.72, 65)
    # Four dark tyres remain visible under the chassis.
    for dx in (0.20, w - 0.39):
        for dy in (0.1, 0.68):
            b(s, x + dx, y + dy, 0.04, 0.22, 0.13, 0.22, (39, 51, 60))
    b(s, x, y + 0.14, 0.16, w, 0.70, 0.30, c, True)
    b(s, x + 0.04, y + 0.14, 0.43, w - 0.08, 0.70, 0.075, shade(c, 1.08))
    cabx = x + w * 0.26
    cabw = w * 0.49
    b(s, cabx, y + 0.23, 0.5, cabw, 0.51, 0.29, (160, 205, 208), True)
    b(s, cabx - 0.03, y + 0.20, 0.79, cabw + 0.06, 0.57, 0.065, shade(c, 1.12), True)
    # Window pillars, side trim, bumper, warm lamps and red tail lamps.
    b(s, cabx + cabw * 0.45, y + 0.205, 0.53, 0.065, 0.03, 0.26, c)
    b(s, x + 0.10, y + 0.12, 0.22, w - 0.20, 0.025, 0.07, shade(c, 0.82))
    front = x + w - 0.05 if direction > 0 else x - 0.025
    rear = x - 0.02 if direction > 0 else x + w - 0.06
    for dy in (0.2, 0.65):
        b(s, front, y + dy, 0.25, 0.075, 0.14, 0.11, (255, 233, 162))
        b(s, rear, y + dy, 0.26, 0.07, 0.12, 0.09, (229, 92, 80))
    b(s, x, y + 0.1, 0.15, 0.07, 0.8, 0.08, (189, 196, 187))


def truck(s, p, body, y, direction, t):
    x, w = body.x, body.w
    p.shadow(s, x, y + 0.1, w, 0.8, 70)
    p.box(s, x, y + 0.12, 0.13, w, 0.76, 0.28, body.color, True)
    cabx = x + w - 0.68 if direction > 0 else x
    cargo_x = x if direction > 0 else x + 0.72
    p.box(s, cargo_x, y + 0.13, 0.41, w - 0.76, 0.74, 0.67, (198, 199, 181), True)
    p.box(s, cabx, y + 0.2, 0.41, 0.64, 0.59, 0.48, body.color, True)
    p.box(s, cabx + 0.1, y + 0.18, 0.62, 0.44, 0.035, 0.22, (169, 206, 201))
    for dx in (0.2, w - 0.4):
        for dy in (0.08, 0.73):
            p.box(s, x + dx, y + dy, 0.04, 0.23, 0.13, 0.23, (40, 53, 59))
    for k in range(3):
        p.box(
            s,
            cargo_x + 0.15 + k * 0.36,
            y + 0.108,
            0.5,
            0.045,
            0.025,
            0.43,
            (170, 175, 163),
        )


def log_model(s, p, body, y, t):
    b = p.box
    x, w = body.x, body.w
    bob = math.sin(t * 2 + x) * 0.018
    b(s, x, y + 0.12, -0.04 + bob, w, 0.75, 0.20, (138, 99, 65), True)
    b(s, x + 0.04, y + 0.16, 0.16 + bob, w - 0.08, 0.66, 0.08, (173, 131, 86), True)
    for k in range(int(w * 2)):
        xx = x + 0.2 + k * 0.45
        p.line(
            s,
            (126, 92, 60),
            (xx, y + 0.17, 0.245 + bob),
            (xx + 0.16, y + 0.76, 0.245 + bob),
        )
    b(s, x + 0.13, y + 0.32, 0.247 + bob, 0.24, 0.15, 0.012, (146, 106, 69))


class SceneRenderer:
    def __init__(self, size=(972, 668)):
        self.surface = pygame.Surface(size)
        self.size = size
        self.projection = Projection()
        self.camera_x = 5.5
        self.sky = pygame.Surface(size)
        for y in range(size[1]):
            f = y / size[1]
            c = tuple(
                int(a + (b - a) * f) for a, b in zip((185, 214, 211), (237, 224, 184))
            )
            pygame.draw.line(self.sky, c, (0, y), (size[0], y))

    def update_camera(self, game, dt):
        self.camera_x += (game.visual_x - self.camera_x) * (1 - math.exp(-6 * dt))

    def ground(self, lane, cam, t):
        p, s = self.projection, self.surface
        y = lane.row - cam
        if lane.kind == Terrain.GRASS:
            base = (127, 168, 118) if lane.row % 2 else (137, 177, 125)
            p.box(s, -1.4, y, -0.38, COLS + 2.8, 1, 0.38, base)
            # Defined playable tiles, with subtle deterministic colour variation.
            for x in range(COLS):
                color = shade(base, 1 + ((x * 13 + lane.row * 7) % 5 - 2) * 0.018)
                p.box(s, x + 0.012, y + 0.012, 0, 0.976, 0.976, 0.015, color)
            for x, kind in lane.decorations:
                if kind == "flower":
                    for dx, dy in ((0.17, 0.18), (0.31, 0.26)):
                        p.box(
                            s,
                            x + dx,
                            y + dy,
                            0.04,
                            0.07,
                            0.07,
                            0.12,
                            (245, 219, 141) if x % 2 else (229, 170, 168),
                        )
                elif kind == "stone":
                    p.box(s, x + 0.7, y + 0.7, 0.02, 0.15, 0.2, 0.1, (166, 176, 157))
                else:
                    for dx in (0.18, 0.28):
                        p.line(
                            s,
                            (85, 132, 95),
                            (x + dx, y + 0.7, 0.03),
                            (x + dx - 0.025, y + 0.7, 0.16),
                            1,
                        )
        elif lane.kind == Terrain.ROAD:
            p.box(s, -1.4, y, -0.38, COLS + 2.8, 1, 0.38, (62, 77, 86))
            for x in range(-1, COLS + 2, 2):
                p.box(s, x + 0.25, y + 0.48, 0.012, 0.8, 0.045, 0.01, (221, 219, 180))
            for x in (-1.4, COLS):
                p.box(s, x, y, 0, 1.4, 1, 0.12, (194, 193, 169))
                p.box(s, x, y + 0.06, 0.12, 1.4, 0.045, 0.012, (226, 218, 190))
        elif lane.kind == Terrain.RIVER:
            p.box(s, -1.4, y, -0.48, COLS + 2.8, 1, 0.35, (83, 154, 179))
            for x in range(-1, COLS + 1):
                xx = x + math.sin(t * 0.9 + x + lane.row) * 0.13
                p.line(
                    s,
                    (154, 204, 205),
                    (xx + 0.1, y + 0.3, -0.11),
                    (xx + 0.48, y + 0.3, -0.11),
                    2,
                )
                p.line(
                    s,
                    (108, 182, 194),
                    (xx + 0.45, y + 0.73, -0.11),
                    (xx + 0.8, y + 0.73, -0.11),
                    1,
                )
        elif lane.kind == Terrain.SPIKES:
            p.box(s, -1.4, y, -0.38, COLS + 2.8, 1, 0.38, (142, 148, 135))
            for x in range(COLS):
                p.box(
                    s,
                    x + 0.06,
                    y + 0.06,
                    0.015,
                    0.88,
                    0.88,
                    0.035,
                    (83, 102, 99) if x in lane.hazard_cols else (156, 185, 136),
                    True,
                )
            col = (
                (111, 225, 153)
                if lane.phase == "safe"
                else (250, 194, 85) if lane.phase == "warn" else (244, 108, 87)
            )
            p.box(s, -1.1, y + 0.24, 0.05, 0.28, 0.28, 0.23, col, True)
        else:
            p.box(s, -1.4, y, -0.38, COLS + 2.8, 1, 0.38, (168, 159, 133))
            for x in range(-1, COLS + 1):
                p.box(s, x + 0.25, y + 0.08, 0.025, 0.23, 0.84, 0.035, (128, 111, 85))
            for yy in (0.22, 0.72):
                p.box(
                    s,
                    -1.4,
                    y + yy,
                    0.06,
                    COLS + 2.8,
                    0.07,
                    0.075,
                    (173, 183, 179),
                    True,
                )

    def render(self, g, t):
        s, p = self.surface, self.projection
        s.blit(self.sky, (0, 0))
        # Gentle cloud layers leave the horizon open, instead of filling it with HUD.
        for x, y, scale in [(130, 55, 1), (510, 25, 0.8), (805, 85, 0.65)]:
            xx = x + math.sin(t * 0.04 + x) * 15
            pygame.draw.ellipse(s, (215, 230, 216), (xx, y, 160 * scale, 25 * scale))
            pygame.draw.ellipse(
                s,
                (215, 230, 216),
                (xx + 35 * scale, y - 12 * scale, 70 * scale, 35 * scale),
            )
        p.ox = self.size[0] / 2 - (self.camera_x - (g.visual_y - g.cam)) * p.sx
        p.oy = 590
        if g.shake_time > 0:
            p.ox += math.sin(g.elapsed * 81) * g.shake_time * 12
            p.oy += math.cos(g.elapsed * 94) * g.shake_time * 9
        start = max(0, int(g.cam) - 3)
        stop = int(g.cam) + 19
        for row in range(stop, start - 1, -1):
            if row in g.lanes:
                self.ground(g.lanes[row], g.cam, t)
        # Global ground-depth sorting, including the interpolated player position.
        drawables = []
        for row in range(start, stop + 1):
            lane = g.lanes.get(row)
            if not lane:
                continue
            y = row - g.cam
            for x in lane.trees:
                drawables.append((x + y + 1, "tree", (x, y, row)))
            for x in lane.rocks:
                drawables.append((x + y + 1, "rock", (x, y)))
            if lane.kind == Terrain.SPIKES:
                for x in lane.hazard_cols:
                    drawables.append((x + y + 1, "spikes", (x, y, lane)))
            if lane.kind == Terrain.GRASS:
                for x in (-1.25, COLS + 0.3):
                    if row % 3 == 0:
                        drawables.append((x + y + 1, "tree", (x, y, row)))
                for x in lane.coins:
                    drawables.append((x + y + 0.9, "coin", (x, y)))
            for body in lane.things:
                drawables.append(
                    (body.x + body.w / 2 + y + 0.5, "body", (lane, body, y))
                )
            if lane.kind == Terrain.RAIL:
                drawables.append((COLS + y + 1, "signal", (lane, y)))
        if not g.dead:
            drawables.append((g.visual_x + g.visual_y - g.cam + 0.5, "player", None))
        for _, kind, data in sorted(drawables, key=lambda item: item[0], reverse=True):
            if kind == "tree":
                tree(s, p, data[0], data[1], data[2])
            elif kind == "rock":
                x, y = data
                p.shadow(s, x + 0.1, y + 0.1, 0.8, 0.8, 50)
                p.box(s, x + 0.15, y + 0.16, 0, 0.69, 0.68, 0.3, (152, 156, 143), True)
                p.box(
                    s, x + 0.27, y + 0.24, 0.30, 0.42, 0.47, 0.22, (173, 178, 162), True
                )
            elif kind == "spikes":
                x, y, lane = data
                height = (
                    0.37
                    if lane.phase == "active"
                    else 0.08 if lane.phase == "warn" else 0.018
                )
                for dx, dy in ((0.26, 0.25), (0.62, 0.25), (0.26, 0.65), (0.62, 0.65)):
                    base = [
                        p.point(x + dx - 0.09, y + dy - 0.09, 0.06),
                        p.point(x + dx + 0.09, y + dy - 0.09, 0.06),
                        p.point(x + dx + 0.09, y + dy + 0.09, 0.06),
                        p.point(x + dx - 0.09, y + dy + 0.09, 0.06),
                    ]
                    tip = p.point(x + dx, y + dy, 0.06 + height)
                    pygame.draw.polygon(s, (192, 205, 199), [base[0], base[1], tip])
                    pygame.draw.polygon(s, (138, 163, 164), [base[3], base[0], tip])
                if lane.phase == "warn":
                    p.box(
                        s, x + 0.18, y + 0.09, 0.068, 0.62, 0.045, 0.025, (246, 190, 83)
                    )
            elif kind == "coin":
                x, y = data
                spin = max(0.045, abs(math.cos(t * 3 + x)) * 0.18)
                p.shadow(s, x + 0.4, y + 0.4, 0.2, 0.2, 30)
                p.box(
                    s,
                    x + 0.5 - spin / 2,
                    y + 0.43,
                    0.28 + math.sin(t * 3 + x) * 0.05,
                    spin,
                    0.13,
                    0.3,
                    (249, 207, 109),
                    True,
                )
                p.box(
                    s,
                    x + 0.5 - spin / 4,
                    y + 0.417,
                    0.37,
                    spin / 2,
                    0.02,
                    0.12,
                    (255, 235, 164),
                )
            elif kind == "player":
                z = (
                    math.sin(g.hop_t * math.pi) * 0.48
                    if g.player.hop
                    else math.sin(t * 2) * 0.01
                )
                if g.player.invuln <= 0 or int(t * 12) % 2 == 0:
                    character(
                        s,
                        p,
                        g.char,
                        g.visual_x - 0.5,
                        g.visual_y - g.cam,
                        z,
                        t,
                        g.player.facing,
                    )
                # A clear ground marker keeps the hero readable amongst larger props.
                pos = p.point(g.visual_x, g.visual_y - g.cam + 0.5, 0.03)
                pygame.draw.ellipse(
                    s, (251, 221, 147), (pos[0] - 18, pos[1] - 8, 36, 16), 2
                )
            elif kind == "body":
                lane, body, y = data
                if lane.kind == Terrain.ROAD:
                    (
                        truck(s, p, body, y, lane.direction, t)
                        if body.variant == 2
                        else car(s, p, body, y, lane.direction, t)
                    )
                elif lane.kind == Terrain.RIVER:
                    log_model(s, p, body, y, t)
                else:
                    for k in range(4):
                        x = body.x + k * 3.2
                        p.box(s, x, y + 0.12, 0.08, 3, 0.77, 0.78, (89, 126, 142), True)
                        p.box(s, x, y + 0.1, 0.86, 3, 0.81, 0.12, (230, 175, 100), True)
                        for j in range(4):
                            p.box(
                                s,
                                x + 0.3 + j * 0.65,
                                y + 0.09,
                                0.5,
                                0.43,
                                0.025,
                                0.24,
                                (186, 215, 208),
                            )
            elif kind == "signal":
                lane, y = data
                p.box(s, COLS + 0.12, y + 0.35, 0, 0.12, 0.12, 1.0, (97, 109, 100))
                p.box(s, COLS + 0.04, y + 0.27, 1, 0.28, 0.23, 0.25, (59, 68, 66))
                pos = p.point(COLS + 0.15, y + 0.24, 1.12)
                col = (
                    (246, 103, 85)
                    if lane.phase == "warn" and int(t * 6) % 2
                    else (218, 192, 103)
                )
                pygame.draw.circle(s, col, (int(pos[0]), int(pos[1])), 4)
        if g.shield_time > 0:
            sx, sy = p.point(g.visual_x, g.visual_y - g.cam + 0.5, 0.6)
            bubble = pygame.Surface((90, 90), pygame.SRCALPHA)
            pygame.draw.ellipse(bubble, (142, 234, 166, 40), (7, 5, 76, 78))
            pygame.draw.ellipse(bubble, (173, 249, 178, 190), (7, 5, 76, 78), 2)
            s.blit(bubble, (sx - 45, sy - 45))
        for q in g.particles:
            p.box(s, q.x, q.y - g.cam, q.z, q.size, q.size, q.size, q.color)
        if g.eagle_active:
            z = max(0.1, g.eagle_timer * 4)
            x, y = g.visual_x - 0.5, g.visual_y - g.cam - 0.8
            p.box(s, x + 0.3, y + 0.2, z, 0.4, 0.7, 0.3, (118, 90, 66))
            flap = math.sin(t * 15) * 0.15
            p.box(s, x - 0.5, y + 0.25, z + flap, 0.8, 0.35, 0.1, (98, 76, 62))
            p.box(s, x + 0.7, y + 0.25, z - flap, 0.8, 0.35, 0.1, (98, 76, 62))
            p.box(s, x + 0.35, y + 0.05, z + 0.1, 0.3, 0.3, 0.26, (242, 228, 197))
        return s
