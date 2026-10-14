import math
from array import array
import pygame


def lerp(a, b, t):
    return a + (b - a) * t


class Audio:
    """Small synthesized cues; no external audio assets."""

    def __init__(self):
        self.muted = False
        self.sounds = {}
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init(22050, -16, 1)
            rate, _, channels = pygame.mixer.get_init()
            for key, f0, f1, duration in [
                ("hop", 420, 650, 0.075),
                ("coin", 880, 1440, 0.16),
                ("click", 550, 750, 0.055),
                ("death", 220, 60, 0.35),
            ]:
                data = array("h")
                phase = 0.0
                count = int(rate * duration)
                for i in range(count):
                    p = i / count
                    phase += math.tau * lerp(f0, f1, p) / rate
                    value = int(math.sin(phase) * 3000 * (1 - p) ** 2 * min(1, p * 20))
                    data.extend([value] * channels)
                self.sounds[key] = pygame.mixer.Sound(buffer=data.tobytes())
        except pygame.error:
            pass

    def play(self, name):
        if not self.muted and name in self.sounds:
            self.sounds[name].play()
