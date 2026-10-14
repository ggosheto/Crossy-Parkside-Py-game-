"""Application states and layout; simulation and geometry live in separate modules."""

import math
import random
from functools import lru_cache
from enum import Enum
import pygame
from .config import SCREEN_W, SCREEN_H, CHARACTERS, DIRS, STEP, IDLE_LIMIT
from .model import Game, Terrain
from .rendering import SceneRenderer, Projection, portrait
from .hand import HandControl, PREVIEW_W, PREVIEW_H, DEAD_ZONE
from .audio import Audio
from .storage import ScoreStore
from .economy import Progression
from .ui_canvas import (
    UI_SCALE,
    scale_of,
    rect_for,
    draw_rect,
    draw_line,
    draw_circle,
    blit,
    load_font,
)

KEYS = {
    pygame.K_UP: "up",
    pygame.K_w: "up",
    pygame.K_SPACE: "up",
    pygame.K_DOWN: "down",
    pygame.K_s: "down",
    pygame.K_LEFT: "left",
    pygame.K_a: "left",
    pygame.K_RIGHT: "right",
    pygame.K_d: "right",
}
# ---------------------------------------------------------------- Neon UI
INK = (11, 15, 30)
WHITE = (239, 244, 255)
MUTED = (150, 165, 193)
CYAN = (105, 242, 218)
VIOLET = (161, 133, 255)
GOLD = (255, 211, 117)
RED = (255, 111, 137)
ACCENTS = [
    GOLD,
    (255, 153, 202),
    CYAN,
    (246, 175, 114),
    (158, 210, 238),
    (159, 217, 146),
]


def lerp(a, b, t):
    return a + (b - a) * t


def mix(a, b, t):
    return tuple(int(lerp(x, y, t)) for x, y in zip(a, b))


@lru_cache(maxsize=24)
def glow(radius, color):
    layer = pygame.Surface((radius * 2, radius * 2), pygame.SRCALPHA)
    for r in range(radius, 0, -3):
        alpha = int(35 * (1 - r / radius) ** 2)
        pygame.draw.circle(layer, (*color, alpha), (radius, radius), r)
    return layer


def halo(surface, center, radius, color):
    k = scale_of(surface)
    r = round(radius * k)
    surface.blit(glow(r, color), (round(center[0] * k - r), round(center[1] * k - r)))


def panel(surface, rect, color=(20, 27, 47, 235), border=(56, 66, 94), radius=22):
    logical = pygame.Rect(rect)
    r = rect_for(surface, rect)
    k = scale_of(surface)
    layer = pygame.Surface(r.size, pygame.SRCALPHA)
    pygame.draw.rect(layer, color, layer.get_rect(), border_radius=round(radius * k))
    pygame.draw.rect(
        layer,
        (*border[:3], 180),
        layer.get_rect(),
        max(1, round(k)),
        border_radius=round(radius * k),
    )
    pygame.draw.line(
        layer,
        (255, 255, 255, 18),
        (round(radius * k), round(k)),
        (r.w - round(radius * k), round(k)),
        max(1, round(k)),
    )
    surface.blit(layer, r)
    return logical


def label(surface, font, text, pos, color=WHITE, center=False):
    img = font.render(str(text), True, color)
    k = scale_of(surface)
    if k != UI_SCALE:
        img = pygame.transform.smoothscale(
            img,
            (
                max(1, round(img.get_width() * k / UI_SCALE)),
                max(1, round(img.get_height() * k / UI_SCALE)),
            ),
        )
    position = tuple(round(v * scale_of(surface)) for v in pos)
    rect = img.get_rect(center=position) if center else img.get_rect(topleft=position)
    surface.blit(img, rect)
    return rect


def icon(surface, kind, center, color=CYAN, size=12):
    k = scale_of(surface)
    x, y = (round(v * k) for v in center)

    def point(dx, dy):
        return round(x + dx * k), round(y + dy * k)

    stroke = max(1, round(2 * k))
    if kind == "coin":
        pygame.draw.circle(surface, color, (x, y), round(size * k), stroke)
        pygame.draw.line(
            surface, color, point(0, -size + 4), point(0, size - 4), stroke
        )
    elif kind == "heart":
        pygame.draw.polygon(
            surface,
            color,
            [
                point(-size, -3),
                point(-size / 2, -size),
                point(0, -size / 2),
                point(size / 2, -size),
                point(size, -3),
                point(0, size),
            ],
        )
    elif kind == "pause":
        for dx in (-5, 4):
            pygame.draw.rect(
                surface,
                color,
                (x + round(dx * k), y - round(8 * k), round(3 * k), round(16 * k)),
                border_radius=round(k),
            )
    elif kind == "arrow":
        pygame.draw.lines(
            surface, color, False, [point(-6, -6), point(0, 0), point(-6, 6)], stroke
        )
        pygame.draw.line(surface, color, point(-14, 0), point(0, 0), stroke)


class State(str, Enum):
    MENU = "menu"
    PLAY = "play"
    PAUSE = "pause"
    OVER = "over"
    SHOP = "shop"
    CAMERA = "camera"


class Arcade:
    def __init__(self, enable_audio=True, save_path=None):
        self.surface = pygame.Surface((SCREEN_W * UI_SCALE, SCREEN_H * UI_SCALE))
        self.fonts = {
            name: load_font(size, bold=bold)
            for name, size, bold in [
                ("micro", 11, True),
                ("small", 14, False),
                ("body", 18, True),
                ("sub", 24, True),
                ("title", 48, True),
                ("score", 70, True),
                ("big", 82, True),
            ]
        }
        self.state = State.MENU
        self.sel = 0
        self.game = None
        self.t = self.state_time = self.accumulator = 0.0
        self.mouse = (-100, -100)
        self.buttons = {}
        self.hover = {}
        self.hand = HandControl()
        self.audio = Audio() if enable_audio else None
        self.store = ScoreStore(save_path)
        self.progression = Progression(self.store)
        self.sel = next(
            i for i, c in enumerate(CHARACTERS) if c.name == self.stats.selected
        )
        self.banked_run_coins = 0
        self.save_error_reported = False
        self.score_bump = self.coin_bump = self.flash = 0.0
        self.toast = ""
        self.toast_time = 0.0
        self.record = False
        self.renderer = SceneRenderer()
        self.held = None
        self.repeat_timer = 0.0
        self.background = pygame.Surface((SCREEN_W * UI_SCALE, SCREEN_H * UI_SCALE))
        self.camera_return = State.MENU
        for y in range(SCREEN_H):
            draw_line(
                self.background,
                mix((14, 23, 36), (24, 39, 49), y / SCREEN_H),
                (0, y),
                (SCREEN_W, y),
            )

        self.background_logical = pygame.transform.smoothscale(
            self.background, (SCREEN_W, SCREEN_H)
        )

    @property
    def stats(self):
        return self.progression.stats

    def bank_coins(self, final=False):
        if self.game is None:
            return True
        delta = max(0, self.game.coins_collected - self.banked_run_coins)
        if not self.progression.deposit(delta, self.game.score if final else 0):
            if not self.save_error_reported:
                self.notify("Progress could not be saved. Check storage.")
            self.save_error_reported = True
            return False
        self.banked_run_coins = self.game.coins_collected
        self.save_error_reported = False
        return True

    @property
    def high(self):
        return self.stats.best

    @property
    def total_coins(self):
        return self.stats.coins

    def text(self, text, pos, style="body", color=WHITE, center=False):
        return label(self.surface, self.fonts[style], text, pos, color, center)

    def portrait(self, char, size, t=0):
        return portrait(char, tuple(round(v * scale_of(self.surface)) for v in size), t)

    def wrapped_text(self, text, pos, width, style="small", color=MUTED, max_lines=5):
        font = self.fonts[style]
        words = str(text).split()
        lines = []
        line = ""
        for word in words:
            candidate = (line + " " + word).strip()
            if font.size(candidate)[0] / UI_SCALE > width and line:
                lines.append(line)
                line = word
            else:
                line = candidate
        if line:
            lines.append(line)
        for i, line in enumerate(lines[:max_lines]):
            self.text(
                line,
                (pos[0], pos[1] + i * (font.get_linesize() / UI_SCALE + 3)),
                style,
                color,
            )

    def sound(self, name):
        if self.audio:
            self.audio.play(name)

    def notify(self, text):
        self.toast, self.toast_time = text, 2.6

    def change_state(self, state):
        self.state, self.state_time = State(state), 0.0
        k = 1 if self.state == State.PLAY else UI_SCALE
        size = (SCREEN_W * k, SCREEN_H * k)
        if self.surface.get_size() != size:
            self.surface = pygame.Surface(size)
        self.accumulator = 0.0
        self.held = None

    def start(self):
        if CHARACTERS[self.sel].name not in self.stats.owned:
            self.change_state(State.SHOP)
            self.notify("Unlock this companion in the shop first.")
            return
        if not self.bank_coins(final=True):
            return
        self.progression.select(CHARACTERS[self.sel].name)
        self.banked_run_coins = 0
        self.game = Game(CHARACTERS[self.sel])
        self.renderer.camera_x = self.game.px
        self.score_bump = self.coin_bump = self.flash = 0.0
        self.toast_time = 0.0
        self.record = False
        self.change_state(State.PLAY)
        self.sound("click")

    def finish(self):
        self.record = self.game.score > self.stats.best
        self.bank_coins(final=True)
        self.change_state(State.OVER)

    def action(self, action):
        if action.startswith("select:"):
            self.sel = int(action.split(":")[1])
            if CHARACTERS[self.sel].name in self.stats.owned:
                self.progression.select(CHARACTERS[self.sel].name)
            self.sound("click")
        elif action in ("start", "retry"):
            self.start()
        elif action == "menu":
            if self.bank_coins(final=True):
                self.change_state(State.MENU)
        elif action == "shop":
            if self.state in (State.MENU, State.OVER):
                self.change_state(State.SHOP)
        elif action.startswith("buy:") and self.state == State.SHOP:
            index = int(action.split(":")[1])
            result = self.progression.buy(CHARACTERS[index].name)
            if result == "bought":
                self.sel = index
                self.sound("coin")
                self.notify(
                    CHARACTERS[index].name.upper() + " UNLOCKED / READY TO PLAY"
                )
            elif result == "funds":
                self.notify("Not enough coins. Collect more during a run.")
            elif result == "save_error":
                self.notify("Purchase not saved. Your coins were not spent.")
        elif action == "gallery_next":
            self.sel = (self.sel + 3) % len(CHARACTERS)
        elif action == "gallery_previous":
            self.sel = (self.sel - 3) % len(CHARACTERS)
        elif action == "ability" and self.state == State.PLAY:
            self.game.activate_ability()
        elif action == "pause" and self.state == State.PLAY and not self.game.dead:
            self.change_state(State.PAUSE)
        elif action == "resume" and self.state == State.PAUSE:
            self.change_state(State.PLAY)
        elif action == "camera":
            if self.state != State.CAMERA:
                self.camera_return = (
                    State.PAUSE if self.state == State.PLAY else self.state
                )
                self.change_state(State.CAMERA)
        elif action == "camera_back":
            self.change_state(self.camera_return)
        elif action == "camera_toggle":
            self.hand.toggle()
        elif action == "camera_retry":
            self.hand.retry()
        elif action.startswith("device:") and self.state == State.CAMERA:
            value = action.split(":")[1]
            self.hand.select_device(None if value == "auto" else int(value))
        elif action == "calibrate":
            if self.hand.calibrate():
                self.notify("CENTER SAVED / RETURN HERE BETWEEN HOPS")
        elif action == "reset_center":
            self.hand.reset_center()
            self.notify("CENTER RESET")
        elif action == "mute" and self.audio:
            self.audio.muted = not self.audio.muted
        elif action in DIRS and self.state == State.PLAY:
            self.game.move(action)

    def direction(self, direction):
        if self.state == State.MENU:
            if direction in ("left", "right"):
                self.sel = (self.sel + (1 if direction == "right" else -1)) % len(
                    CHARACTERS
                )
                if CHARACTERS[self.sel].name in self.stats.owned:
                    self.progression.select(CHARACTERS[self.sel].name)
                self.sound("click")
            elif direction == "up":
                self.start()
        elif self.state == State.SHOP:
            if direction in ("left", "right"):
                self.sel = (self.sel + (1 if direction == "right" else -1)) % len(
                    CHARACTERS
                )
        elif self.state == State.OVER:
            if direction == "up":
                self.start()
            elif direction == "down":
                self.change_state(State.MENU)
        elif self.state == State.PLAY:
            self.game.move(direction)

    def key(self, key):
        if key == pygame.K_e:
            self.action("ability")
        elif key == pygame.K_b and self.state in (State.MENU, State.OVER):
            self.action("shop")
        elif key == pygame.K_h:
            self.hand.toggle()
        elif key == pygame.K_z and self.state == State.CAMERA:
            self.action("calibrate")
        elif key == pygame.K_m:
            self.action("mute")
        elif key == pygame.K_ESCAPE and self.state == State.CAMERA:
            self.action("camera_back")
        elif key in (pygame.K_ESCAPE, pygame.K_p):
            self.action(
                "resume"
                if self.state == State.PAUSE
                else "pause" if self.state == State.PLAY else "menu"
            )
        elif key == pygame.K_r and self.state == State.CAMERA:
            self.hand.retry()
        elif key == pygame.K_r and self.state in (State.PAUSE, State.OVER):
            self.start()
        elif key in (pygame.K_RETURN, pygame.K_KP_ENTER):
            if self.state == State.PLAY:
                self.game.move("up")
            elif self.state == State.CAMERA:
                self.hand.toggle()
            elif self.state == State.SHOP:
                name = CHARACTERS[self.sel].name
                self.action(
                    f"select:{self.sel}"
                    if name in self.stats.owned
                    else f"buy:{self.sel}"
                )
            else:
                self.action("resume" if self.state == State.PAUSE else "start")
        elif key in KEYS:
            self.direction(KEYS[key])
            if self.state == State.PLAY:
                self.held = key
                self.repeat_timer = 0.24

    def release(self, key):
        if key == self.held:
            self.held = None

    def click(self):
        for action, rect in reversed(list(self.buttons.items())):
            if rect.collidepoint(self.mouse):
                self.action(action)
                break

    def update(self, dt):
        self.t += dt
        self.state_time += dt
        self.score_bump = max(0, self.score_bump - dt * 4)
        self.coin_bump = max(0, self.coin_bump - dt * 4)
        self.flash = max(0, self.flash - dt * 3)
        self.toast_time = max(0, self.toast_time - dt)
        for key, rect in self.buttons.items():
            self.hover[key] = lerp(
                self.hover.get(key, 0),
                float(rect.collidepoint(self.mouse)),
                min(1, dt * 12),
            )
        if self.state != State.PLAY:
            return
        if self.held is not None:
            self.repeat_timer -= dt
            if self.repeat_timer <= 0:
                self.game.move(KEYS[self.held])
                self.repeat_timer = 0.18
        self.accumulator += min(dt, 0.25)
        while self.accumulator + 1e-10 >= STEP:
            self.game.update(STEP)
            self.accumulator = max(0.0, self.accumulator - STEP)
        self.bank_coins()
        self.renderer.update_camera(self.game, dt)
        for event in self.game.drain_events():
            if event.kind == "hop":
                self.sound("hop")
            elif event.kind == "score":
                self.score_bump = 1.0
                if event.value % 10 == 0:
                    self.notify(f"{event.value} CROSSINGS / KEEP GOING")
            elif event.kind == "coin":
                self.coin_bump = 1.0
                self.sound("coin")
            elif event.kind == "damage":
                self.flash = 0.7
                self.sound("death")
            elif event.kind == "ability":
                self.sound("coin")
                self.notify("SHELL SHIELD / 2.5 SECONDS")
            elif event.kind == "respawn":
                self.notify("SECOND CHANCE / SAFE CHECKPOINT")
        if self.game.dead and not self.game.particles:
            self.finish()

    def backdrop(self):
        self.surface.blit(
            self.background_logical if scale_of(self.surface) == 1 else self.background,
            (0, 0),
        )
        halo(self.surface, (940, 250), 280, (112, 191, 160))
        halo(self.surface, (380, 750), 260, (91, 139, 154))
        for i in range(22):
            x = (i * 137) % 1280
            y = int((i * 101 - self.t * (4 + i % 5)) % 800)
            draw_circle(self.surface, (76, 105, 109), (x, y), 1)

    def button(self, action, rect, text, primary=False, color=CYAN):
        rect = pygame.Rect(rect)
        self.buttons[action] = rect
        h = self.hover.get(action, 0)
        drawn = rect.move(0, -int(h * 2))
        if primary:
            draw_rect(
                self.surface, mix(color, WHITE, h * 0.15), drawn, border_radius=13
            )
            text_center = (
                (drawn.centerx - 10, drawn.centery) if drawn.w >= 160 else drawn.center
            )
            self.text(text, text_center, "body", INK, True)
            if drawn.w >= 160:
                icon(self.surface, "arrow", (drawn.right - 22, drawn.centery), INK)
        else:
            panel(
                self.surface,
                drawn,
                (*mix((24, 38, 49), (44, 62, 69), h), 245),
                mix((67, 87, 94), color, h),
                13,
            )
            self.text(text, drawn.center, "small", WHITE, True)

    def topbar(self):
        self.text("C / P", (30, 27), "sub", CYAN)
        self.text("CROSSY PARKSIDE", (112, 26), "micro", WHITE)
        self.text("A LITTLE ADVENTURE. ONE MORE CROSSING.", (112, 44), "micro", MUTED)
        icon(self.surface, "coin", (658, 40), GOLD, 9)
        self.text(f"WALLET {self.stats.wallet}", (678, 31), "small", GOLD)
        self.button(
            "mute",
            (877, 22, 132, 39),
            "M  " + ("MUTED" if self.audio and self.audio.muted else "SOUND ON"),
        )
        self.button(
            "camera",
            (1024, 22, 232, 39),
            "CAMERA SETTINGS / " + ("ON" if self.hand.running else "OFF"),
        )

    def draw_menu(self):
        self.backdrop()
        self.topbar()
        self.text("SMOOTH MENUS / EDITION 04", (72, 135), "micro", CYAN)
        self.text("CROSSY", (65, 165), "big")
        self.text("PARKSIDE", (70, 260), "title", (227, 204, 153))
        self.text("Small steps. Big adventures.", (73, 337), "sub")
        self.text(
            "Find your rhythm between roads, rivers and rails.",
            (73, 378),
            "small",
            MUTED,
        )
        self.button(
            "start",
            (72, 429, 440, 61),
            (
                "START YOUR RUN  /  ENTER"
                if CHARACTERS[self.sel].name in self.stats.owned
                else "LOCKED / OPEN THE SHOP"
            ),
            True,
            (236, 204, 137),
        )
        self.button("shop", (530, 436, 147, 48), "B  SHOP")
        self.text(
            f"PERSONAL BEST  {self.high:03}     /     EARNED  {self.total_coins}",
            (74, 515),
            "micro",
            CYAN,
        )
        # A real geometry portrait, sitting on a layered isometric diorama.
        s = self.surface
        p = Projection(
            930 * UI_SCALE, 431 * UI_SCALE, 120 * UI_SCALE, 60 * UI_SCALE, 65 * UI_SCALE
        )
        p.shadow(s, -1, -1, 2, 2, 100)
        p.box(s, -1, -1, -0.35, 2, 2, 0.35, (79, 116, 105), True)
        p.box(s, -1, -1, 0, 2, 2, 0.10, (133, 169, 121), True)
        p.box(s, -0.98, -0.98, 0.10, 1.96, 0.98, 0.015, (144, 179, 130))
        for x, y in [(-0.78, -0.68), (0.65, 0.58), (0.67, -0.63)]:
            p.box(s, x, y, 0.12, 0.055, 0.055, 0.12, (237, 211, 139))
        img = self.portrait(CHARACTERS[self.sel], (345, 374), self.t)
        blit(
            s,
            img,
            (
                930 - img.get_width() / (2 * UI_SCALE),
                288 - img.get_height() / (2 * UI_SCALE),
            ),
            native=True,
        )
        self.text(
            CHARACTERS[self.sel].name.upper(),
            (930, 527),
            "micro",
            ACCENTS[self.sel],
            True,
        )
        self.text("CHOOSE YOUR COMPANION", (34, 570), "micro", MUTED)
        page = self.sel // 3
        self.button("gallery_previous", (1114, 548, 50, 34), "<")
        self.button("gallery_next", (1178, 548, 50, 34), ">")
        self.text(f"{page+1} / 2", (1035, 558), "micro", MUTED)
        for slot, i in enumerate(range(page * 3, min(page * 3 + 3, len(CHARACTERS)))):
            char = CHARACTERS[i]
            rect = pygame.Rect(34 + slot * 410, 595, 392, 142)
            selected = i == self.sel
            owned = char.name in self.stats.owned
            panel(
                s,
                rect,
                (30, 44, 54, 248) if selected else (20, 33, 45, 245),
                ACCENTS[i] if selected else (62, 79, 90),
                20,
            )
            self.buttons[f"select:{i}"] = rect
            image = self.portrait(char, (105, 114), self.t + i)
            blit(s, image, (rect.x + 13, rect.y + 9), native=True)
            self.text(char.name, (rect.x + 125, rect.y + 23), "sub")
            self.text(
                "OWNED" if owned else f"LOCKED / {char.price} COINS",
                (rect.x + 125, rect.y + 66),
                "micro",
                ACCENTS[i],
            )
            self.text(char.perk, (rect.x + 125, rect.y + 96), "small", MUTED)
            if selected:
                draw_circle(s, ACCENTS[i], (rect.right - 22, rect.y + 23), 4)
        self.text(
            "ARROWS / WASD  MOVE     SPACE  HOP     P  PAUSE     F11  FULLSCREEN",
            (640, 770),
            "micro",
            MUTED,
            True,
        )

    def draw_shop(self):
        self.backdrop()
        self.topbar()
        self.text("THE COMPANION SHOP", (38, 96), "title")
        self.text(
            "Earn coins on every run. Unlock a new way to cross.",
            (40, 157),
            "small",
            MUTED,
        )
        self.button("menu", (1018, 107, 238, 45), "BACK TO THE PARK / ESC")
        for i, char in enumerate(CHARACTERS):
            col, row = i % 3, i // 3
            rect = pygame.Rect(34 + col * 410, 196 + row * 271, 392, 248)
            selected = i == self.sel
            owned = char.name in self.stats.owned
            panel(
                self.surface,
                rect,
                (30, 44, 54, 248),
                ACCENTS[i] if selected else (64, 84, 91),
                20,
            )
            self.buttons[f"select:{i}"] = rect
            image = self.portrait(char, (142, 154), self.t + i)
            blit(self.surface, image, (rect.x + 7, rect.y + 8), native=True)
            self.text(char.name, (rect.x + 158, rect.y + 35), "sub")
            self.text(
                "OWNED" if owned else f"{char.price} COINS",
                (rect.x + 158, rect.y + 75),
                "micro",
                ACCENTS[i],
            )
            self.text(char.perk, (rect.x + 22, rect.y + 169), "small", MUTED)
            if owned:
                self.button(
                    f"select:{i}",
                    (rect.x + 20, rect.y + 199, 352, 34),
                    "SELECTED" if selected else "SELECT COMPANION",
                )
            else:
                self.button(
                    f"buy:{i}",
                    (rect.x + 20, rect.y + 199, 352, 34),
                    f"UNLOCK / {char.price} COINS",
                    True,
                    ACCENTS[i] if self.stats.wallet >= char.price else (115, 131, 135),
                )
        self.text(
            "COINS BANK AUTOMATICALLY / YOUR COMPANIONS STAY UNLOCKED",
            (640, 774),
            "micro",
            MUTED,
            True,
        )

    def world(self):
        s = self.surface
        self.backdrop()
        image = self.renderer.render(self.game, self.t)
        # The scene has a dedicated viewport, so large objects cannot cover UI.
        blit(s, image, (24, 92))
        draw_rect(s, (78, 99, 103), (24, 92, 972, 668), 1, border_radius=18)
        panel(s, (46, 112, 216, 54), (17, 37, 40, 225), (98, 124, 117), 13)
        self.text("MORNING RUN", (62, 123), "micro", CYAN)
        self.text(
            f"ZONE {1+self.game.score//15:02} / PARKSIDE",
            (62, 145),
            "micro",
            (222, 217, 186),
        )
        self.text("WASD / ARROWS  MOVE    SPACE  HOP", (52, 731), "micro", (38, 65, 61))
        for pop in self.game.popups:
            x, y = self.renderer.projection.point(pop.x, pop.y - self.game.cam, pop.z)
            self.text("+1", (x + 24, y + 92), "body", (255, 246, 170), True)
        if self.flash > 0:
            layer = pygame.Surface((972, 668), pygame.SRCALPHA)
            layer.fill((*RED, int(50 * self.flash)))
            blit(s, layer, (24, 92))

    def hud(self):
        g, s = self.game, self.surface
        self.topbar()
        panel(s, (1018, 92, 238, 668), (21, 34, 45, 250), (60, 81, 89), 20)
        self.text("DISTANCE", (1042, 117), "micro", MUTED)
        self.text(
            f"{g.score:03}",
            (1037, 134 - int(self.score_bump * 4)),
            "score",
            mix(WHITE, CYAN, self.score_bump),
        )
        self.text("CROSSINGS", (1042, 222), "micro", MUTED)
        self.text(f"BEST  {self.high:03}", (1140, 222), "micro", (231, 209, 156))
        draw_line(s, (55, 76, 84), (1042, 251), (1232, 251))
        icon(s, "coin", (1055, 282), GOLD)
        self.text(
            f"{g.coins_collected:02}",
            (1080, 262 - int(self.coin_bump * 3)),
            "sub",
            GOLD,
        )
        self.text("THIS RUN", (1150, 280), "micro", MUTED)
        img = self.portrait(g.char, (118, 128), self.t)
        blit(s, img, (1058, 318), native=True)
        self.text(g.char.name.upper(), (1137, 450), "micro", WHITE, True)
        for i in range(g.char.lives):
            icon(
                s,
                "heart",
                (1127 + i * 24, 480),
                RED if i < g.lives else (68, 74, 83),
                8,
            )
        remaining = max(0, 1 - g.idle / IDLE_LIMIT)
        color = RED if remaining < 0.28 or g.eagle_active else CYAN
        self.text(
            "EAGLE INBOUND" if g.eagle_active else "MOMENTUM",
            (1042, 520),
            "micro",
            color,
        )
        self.text(f"{max(0,IDLE_LIMIT-g.idle):.1f}s", (1190, 520), "micro", MUTED)
        draw_rect(s, (48, 66, 77), (1042, 547, 190, 6), border_radius=3)
        if remaining > 0:
            draw_rect(
                s, color, (1042, 547, max(2, int(190 * remaining)), 6), border_radius=3
            )
        warning = any(
            l.kind in (Terrain.RAIL, Terrain.SPIKES)
            and l.phase == "warn"
            and abs(l.row - g.row) < 4
            for l in g.lanes.values()
        )
        self.text(
            "HAZARD INCOMING" if warning else "MOVE FORWARD TO RESET",
            (1042, 573),
            "micro",
            GOLD if warning else MUTED,
        )
        self.button("pause", (1040, 620, 194, 48), "II  PAUSE / P")
        for action, text, x in [
            ("left", "<", 1040),
            ("down", "v", 1090),
            ("up", "^", 1140),
            ("right", ">", 1190),
        ]:
            self.button(action, (x, 687, 44, 42), text)
        if g.char.ability == "shield":
            title = (
                "SHIELD ACTIVE"
                if g.shield_time > 0
                else (
                    f"RECHARGING {g.ability_cooldown:.0f}s"
                    if g.ability_cooldown > 0
                    else "E  SHELL SHIELD"
                )
            )
            self.button("ability", (1040, 735, 194, 23), title)
        elif g.char.ability in ("magnet", "swim"):
            self.text(
                (
                    "MAGNET / 2 TILES"
                    if g.char.ability == "magnet"
                    else "SWIMMING ENABLED"
                ),
                (1140, 745),
                "micro",
                CYAN,
                True,
            )
        elif g.player.invuln > 0:
            self.text("SECOND CHANCE", (1140, 745), "micro", CYAN, True)

    def modal(self, paused):
        s = self.surface
        g = self.game
        layer = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
        layer.fill((8, 16, 28, 185))
        blit(s, layer, (0, 0))
        ease = 1 - (1 - min(1, self.state_time / 0.3)) ** 3
        y = 164 + int((1 - ease) * 20)
        panel(s, (345, y, 590, 475), (22, 36, 48, 252), (103, 122, 123), 26)
        self.text(
            (
                "TAKE YOUR TIME"
                if paused
                else (
                    "A NEW PERSONAL BEST"
                    if self.record
                    else "EVERY RUN IS A NEW ADVENTURE"
                )
            ),
            (640, y + 38),
            "micro",
            CYAN,
            True,
        )
        self.text(
            "PAUSED" if paused else "RUN COMPLETE", (640, y + 96), "title", WHITE, True
        )
        self.text(
            "The world waits for you." if paused else g.cause,
            (640, y + 143),
            "small",
            MUTED,
            True,
        )
        for x, value, title, color in [
            (377, g.score, "DISTANCE", CYAN),
            (557, g.coins_collected, "COINS", GOLD),
            (737, self.high, "BEST", (202, 189, 226)),
        ]:
            panel(s, (x, y + 184, 166, 96), (30, 46, 58, 255), (60, 82, 94), 15)
            self.text(f"{value:03}", (x + 83, y + 217), "sub", color, True)
            self.text(title, (x + 83, y + 254), "micro", MUTED, True)
        self.button(
            "resume" if paused else "retry",
            (377, y + 310, 526, 58),
            "KEEP EXPLORING / ENTER" if paused else "ONE MORE ADVENTURE / ENTER",
            True,
            (233, 203, 141),
        )
        self.button("menu", (377, y + 384, 526, 46), "CHOOSE ANOTHER COMPANION")
        self.text(
            "R  RESTART" if paused else "UP  RETRY / DOWN  MENU",
            (640, y + 451),
            "micro",
            MUTED,
            True,
        )

    def draw_camera(self):
        self.backdrop()
        self.topbar()
        self.text("CAMERA & HAND CONTROL", (40, 100), "title")
        self.text(
            "Choose a camera. Center your fingertip. Take the next step.",
            (43, 163),
            "small",
            MUTED,
        )
        self.button("camera_back", (1040, 106, 216, 44), "BACK / ESC")
        panel(self.surface, (38, 205, 572, 535), (22, 37, 48, 248), (71, 95, 101), 22)
        panel(self.surface, (634, 205, 612, 535), (22, 37, 48, 248), (71, 95, 101), 22)
        if self.hand.preview is not None:
            blit(self.surface, self.hand.preview, (64, 234), logical_size=(520, 390))
            self.tracking_overlay((64, 234), (520, 390))
        else:
            panel(
                self.surface, (64, 234, 520, 390), (15, 26, 36, 255), (56, 79, 87), 17
            )
            self.text("LIVE PREVIEW", (324, 384), "sub", MUTED, True)
            self.wrapped_text(
                "Press Start camera. If dependencies are missing, run setup_camera.bat and then run_game.bat.",
                (124, 435),
                410,
            )
        self.text(
            self.hand.status,
            (64, 649),
            "body",
            CYAN if self.hand.tracking_available else GOLD,
        )
        self.wrapped_text(self.hand.detail, (64, 684), 514, "micro", MUTED, 3)
        self.text("CAMERA DEVICE", (658, 232), "micro", MUTED)
        for i, value in enumerate(["auto", "0", "1", "2", "3"]):
            selected = (
                self.hand.device is None
                if value == "auto"
                else self.hand.device == int(value)
            )
            self.button(
                "device:" + value,
                (658 + i * 108, 261, 96, 38),
                value.upper(),
                selected,
                CYAN,
            )
        self.text(
            "Active: "
            + str(
                self.hand.active_device if self.hand.active_device is not None else "-"
            )
            + " / "
            + self.hand.backend,
            (658, 317),
            "small",
            MUTED,
        )
        self.text(
            self.hand.api or "Hand tracker is loaded when the camera starts.",
            (658, 342),
            "small",
            MUTED,
        )
        self.button(
            "camera_toggle",
            (658, 388, 263, 49),
            "STOP CAMERA / H" if self.hand.running else "START CAMERA / H",
            True,
            CYAN,
        )
        self.button("camera_retry", (939, 388, 280, 49), "RETRY / R")
        self.button("calibrate", (658, 457, 263, 47), "CALIBRATE CENTER / Z")
        self.button("reset_center", (939, 457, 280, 47), "RESET CENTER")
        self.wrapped_text(
            "1. Show your index finger near the center. 2. Hold still until READY TO HOP. 3. Move outside the box to hop, then return to center.",
            (658, 530),
            540,
            "body",
            WHITE,
            5,
        )
        self.wrapped_text(
            "If there is no image: close other camera apps, check Windows Settings > Privacy & security > Camera > desktop app access, then try another device.",
            (658, 655),
            540,
            "small",
            MUTED,
            4,
        )

    def tracking_overlay(self, pos, size):
        h = self.hand
        s = self.surface
        cx, cy = h.center
        color = CYAN if h.armed else GOLD
        draw_rect(
            s,
            color,
            (
                pos[0] + (cx - DEAD_ZONE) * size[0],
                pos[1] + (cy - DEAD_ZONE) * size[1],
                DEAD_ZONE * 2 * size[0],
                DEAD_ZONE * 2 * size[1],
            ),
            2,
            5,
        )
        # A real landmark overlay makes detection visible, distinct from video alone.
        links = [
            (0, 1),
            (1, 2),
            (2, 3),
            (3, 4),
            (0, 5),
            (5, 6),
            (6, 7),
            (7, 8),
            (5, 9),
            (9, 10),
            (10, 11),
            (11, 12),
            (9, 13),
            (13, 14),
            (14, 15),
            (15, 16),
            (13, 17),
            (0, 17),
            (17, 18),
            (18, 19),
            (19, 20),
        ]
        points = [(pos[0] + x * size[0], pos[1] + y * size[1]) for x, y in h.landmarks]
        for a, b in links:
            if max(a, b) < len(points):
                draw_line(s, CYAN, points[a], points[b], 1)
        for point in points:
            draw_circle(s, WHITE, point, 2)
        if h.finger_pos is not None:
            fx, fy = h.finger_pos
            draw_circle(s, color, (pos[0] + fx * size[0], pos[1] + fy * size[1]), 5, 2)

    def webcam(self):
        if self.hand.preview is None:
            return
        x, y = 784, 557
        panel(self.surface, (x - 8, y - 30, 196, 192), (17, 34, 43, 250), CYAN, 15)
        self.text("HAND CONTROL", (x, y - 21), "micro", CYAN)
        blit(
            self.surface, self.hand.preview, (x, y), logical_size=(PREVIEW_W, PREVIEW_H)
        )
        self.tracking_overlay((x, y), (PREVIEW_W, PREVIEW_H))
        self.text(self.hand.status, (x, y + 145), "micro", CYAN)

    def draw(self):
        self.buttons = {}
        if self.state == State.MENU:
            self.draw_menu()
        elif self.state == State.SHOP:
            self.draw_shop()
        elif self.state == State.CAMERA:
            self.draw_camera()
        else:
            self.world()
            self.hud()
            if self.state in (State.PAUSE, State.OVER):
                self.buttons = {}
                self.modal(self.state == State.PAUSE)
        if self.state in (State.PLAY, State.MENU):
            self.webcam()
        if self.toast_time > 0:
            panel(self.surface, (330, 708, 620, 40), (23, 43, 51, 245), CYAN, 12)
            self.text(self.toast, (640, 728), "micro", CYAN, True)
        return self.surface


def viewport(size):
    scale = min(size[0] / SCREEN_W, size[1] / SCREEN_H)
    w, h = max(1, int(SCREEN_W * scale)), max(1, int(SCREEN_H * scale))
    return pygame.Rect((size[0] - w) // 2, (size[1] - h) // 2, w, h)


def pointer(position, size):
    v = viewport(size)
    if not v.collidepoint(position):
        return (-100, -100)
    return ((position[0] - v.x) * SCREEN_W / v.w, (position[1] - v.y) * SCREEN_H / v.h)
