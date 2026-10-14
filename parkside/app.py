"""Desktop shell: events, fixed-step application update and presentation."""

import pygame
from .config import SCREEN_W, SCREEN_H
from .ui import Arcade, State, viewport, pointer


def main():
    pygame.mixer.pre_init(22050, -16, 1, 512)
    pygame.init()
    desktop = pygame.display.get_desktop_sizes()[0]
    factor = min(1, (desktop[0] - 80) / SCREEN_W, (desktop[1] - 100) / SCREEN_H)
    window_size = max(640, int(SCREEN_W * factor)), max(400, int(SCREEN_H * factor))
    display = pygame.display.set_mode(window_size, pygame.RESIZABLE)
    pygame.display.set_caption("Crossy Parkside | Edition 04")
    clock = pygame.time.Clock()
    app = Arcade()
    fullscreen = False
    try:
        while True:
            dt = clock.tick(60) / 1000
            app.mouse = pointer(pygame.mouse.get_pos(), display.get_size())
            for e in pygame.event.get():
                if e.type == pygame.QUIT:
                    return
                if e.type == pygame.VIDEORESIZE and not fullscreen:
                    window_size = max(480, e.w), max(300, e.h)
                    display = pygame.display.set_mode(window_size, pygame.RESIZABLE)
                elif e.type == pygame.KEYDOWN:
                    if e.key == pygame.K_F11:
                        fullscreen = not fullscreen
                        display = (
                            pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
                            if fullscreen
                            else pygame.display.set_mode(window_size, pygame.RESIZABLE)
                        )
                    else:
                        app.key(e.key)
                elif e.type == pygame.KEYUP:
                    app.release(e.key)
                elif e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
                    app.mouse = pointer(e.pos, display.get_size())
                    app.click()
                elif e.type == pygame.WINDOWFOCUSLOST and app.state == State.PLAY:
                    app.action("pause")
            move = app.hand.read()
            if move:
                app.direction(move)
            app.update(dt)
            canvas = app.draw()
            view = viewport(display.get_size())
            display.fill((7, 13, 22))
            display.blit(pygame.transform.smoothscale(canvas, view.size), view)
            pygame.display.flip()
    finally:
        app.bank_coins(final=True)
        app.hand.close()
        pygame.quit()
