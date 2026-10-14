import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
import pygame
from parkside.hand import (
    HandControl,
    HandDetector,
    GestureFilter,
    CameraFrame,
    FRAME_SIZE,
)
from parkside.ui import Arcade, State, pointer
from parkside.ui_canvas import UI_SCALE, FONT_ROOT
from parkside.rendering import portrait
from parkside.config import CHARACTERS, SCREEN_W, SCREEN_H


class GestureTests(unittest.TestCase):
    def test_requires_neutral_before_initial_move(self):
        f = GestureFilter()
        for n in range(10):
            self.assertIsNone(f.sample((0.5, 0.1), n * 0.04))
        self.assertFalse(f.armed)

    def test_one_move_then_return_to_neutral(self):
        f = GestureFilter()
        f.sample((0.5, 0.5), 0)
        f.sample((0.5, 0.5), 0.04)
        moves = [f.sample((0.5, 0.1), 0.1 + n * 0.04) for n in range(12)]
        self.assertEqual([m for m in moves if m], ["up"])
        for n in range(10):
            f.sample((0.5, 0.5), 1 + n * 0.04)
        moves = [f.sample((0.9, 0.5), 2 + n * 0.04) for n in range(12)]
        self.assertEqual([m for m in moves if m], ["right"])

    def test_loss_and_nonfinite_landmarks_disarm(self):
        f = GestureFilter()
        f.sample((0.5, 0.5), 0)
        f.sample((0.5, 0.5), 0.04)
        self.assertTrue(f.armed)
        f.sample(None, 0.1)
        self.assertFalse(f.armed)
        self.assertIsNone(f.sample((float("nan"), 0.5), 0.2))

    def test_neutral_jitter_does_not_trigger_hops(self):
        f = GestureFilter()
        for n in range(40):
            self.assertIsNone(f.sample((0.5 + (-1) ** n * 0.04, 0.51), n * 0.03))
        self.assertTrue(f.armed)

    def test_calibrated_center_and_down_direction(self):
        f = GestureFilter((0.35, 0.4))
        f.sample((0.35, 0.4), 0)
        f.sample((0.35, 0.4), 0.04)
        moves = [f.sample((0.35, 0.8), 0.1 + n * 0.04) for n in range(12)]
        self.assertEqual([m for m in moves if m], ["down"])


class FakeFrame:
    size = 1

    def tobytes(self):
        return bytes(FRAME_SIZE[0] * FRAME_SIZE[1] * 3)


class FakeCapture:
    def __init__(self, works):
        self.works = works
        self.released = False

    def isOpened(self):
        return self.works

    def set(self, *args):
        return True

    def read(self):
        return self.works, FakeFrame() if self.works else None

    def release(self):
        self.released = True


class FakeCV:
    CAP_DSHOW = 700
    CAP_MSMF = 1400
    CAP_ANY = 0
    CAP_PROP_FRAME_WIDTH = 3
    CAP_PROP_FRAME_HEIGHT = 4
    CAP_PROP_FPS = 5
    CAP_PROP_BUFFERSIZE = 6
    COLOR_BGR2RGB = 7

    def __init__(self, working=(1, 1400)):
        self.working = working
        self.attempts = []
        self.captures = []

    def VideoCapture(self, index, backend):
        self.attempts.append((index, backend))
        cap = FakeCapture((index, backend) == self.working)
        self.captures.append(cap)
        return cap

    def flip(self, frame, n):
        return frame

    def cvtColor(self, frame, n):
        return frame

    def resize(self, frame, size):
        return frame


class FastStop:
    def is_set(self):
        return False

    def wait(self, n):
        return False


class FakeDetector:
    api = "Test tracker"

    def __init__(self):
        self.closed = False

    def process(self, rgb, stamp):
        return (0.5, 0.5), tuple((0.5, 0.5) for _ in range(21))

    def close(self):
        self.closed = True


def wait_until(predicate, timeout=1.5):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if predicate():
            return True
        time.sleep(0.005)
    return False


class CameraTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pygame.init()
        pygame.display.set_mode((1280, 800))

    @classmethod
    def tearDownClass(cls):
        pygame.quit()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "camera.json"
        self.h = HandControl(config_path=self.path)

    def tearDown(self):
        self.h.close()
        self.temp.cleanup()

    def test_missing_opencv_has_actionable_error(self):
        def missing():
            raise ModuleNotFoundError("cv2")

        self.h.cv_loader = missing
        self.h.start()
        self.assertTrue(wait_until(lambda: not self.h.running))
        self.assertIn("OPENCV", self.h.status)
        self.assertIn("setup_camera.bat", self.h.detail)

    def test_windows_fallback_to_usb_and_msmf_and_releases_failed_caps(self):
        cv = FakeCV()
        with patch("parkside.hand.platform.system", return_value="Windows"):
            cap, frame = self.h._open_camera(cv, FastStop(), None)
        self.assertEqual(self.h.active_device, 1)
        self.assertEqual(self.h.backend, "MSMF")
        self.assertEqual(cv.attempts[:3], [(0, 700), (0, 1400), (0, 0)])
        self.assertTrue(all(c.released for c in cv.captures[:-1]))
        self.assertFalse(cap.released)
        cap.release()

    def test_explicit_device_does_not_open_unrelated_devices(self):
        cv = FakeCV(working=None)
        with patch("parkside.hand.platform.system", return_value="Windows"):
            cap, frame = self.h._open_camera(cv, FastStop(), 3)
        self.assertIsNone(cap)
        self.assertTrue(all(i == 3 for i, b in cv.attempts))
        self.assertIn("NO CAMERA", self.h.status)

    def test_start_is_nonblocking_and_closes_cleanly(self):
        gate = threading.Event()

        def loading():
            gate.wait(0.8)
            raise ModuleNotFoundError("cv2")

        self.h.cv_loader = loading
        start = time.monotonic()
        self.h.start()
        elapsed = time.monotonic() - start
        self.assertLess(elapsed, 0.1)
        gate.set()
        self.h.close()
        self.assertFalse(self.h.ok)
        self.assertIsNone(self.h.preview)

    def test_worker_frames_tracking_and_shutdown(self):
        cv = FakeCV((0, 0))
        detector = FakeDetector()
        self.h.cv_loader = lambda: cv
        self.h.detector_factory = lambda: detector
        with patch("parkside.hand.platform.system", return_value="Linux"):
            self.h.start()
            self.assertTrue(wait_until(lambda: self.h._frame is not None))
            self.h.read()
            self.assertIsNotNone(self.h.preview)
            self.assertEqual(self.h.preview.get_size(), FRAME_SIZE)
            self.assertEqual(len(self.h.landmarks), 21)
            self.h.close()
        self.assertTrue(detector.closed)
        self.assertTrue(all(c.released for c in cv.captures))
        self.assertIsNone(self.h.read())
        self.assertIsNone(self.h.preview)

    def test_preview_still_works_when_detector_cannot_load(self):
        cv = FakeCV((0, 0))

        def broken():
            raise RuntimeError("missing model")

        self.h.cv_loader = lambda: cv
        self.h.detector_factory = broken
        with patch("parkside.hand.platform.system", return_value="Linux"):
            self.h.start()
            self.assertTrue(wait_until(lambda: self.h._frame is not None))
            self.h.read()
            self.assertIsNotNone(self.h.preview)
            self.assertFalse(self.h.tracking_available)
            self.assertEqual(self.h.status, "PREVIEW ONLY")
            self.h.close()

    def test_one_snapshot_is_not_processed_twice_and_stale_frames_disarm(self):
        self.h.running = True
        self.h.tracking_available = True
        pixels = bytes(FRAME_SIZE[0] * FRAME_SIZE[1] * 3)
        for n in (1, 2):
            self.h._frame = CameraFrame(n, pixels, (0.5, 0.5), (), time.monotonic())
            self.h.read()
        self.assertTrue(self.h.armed)
        before = self.h.gestures.neutral_frames
        self.h.read()
        self.assertEqual(before, self.h.gestures.neutral_frames)
        self.h._frame = CameraFrame(3, pixels, (0.5, 0.1), (), time.monotonic() - 2)
        self.assertIsNone(self.h.read())
        self.assertFalse(self.h.armed)
        self.assertIsNone(self.h.preview)

    def test_calibration_persists_without_touching_progress(self):
        self.h.finger_pos = (0.4, 0.45)
        self.assertTrue(self.h.calibrate())
        h = HandControl(config_path=self.path)
        self.assertEqual(h.center, (0.4, 0.45))
        h.close()
        self.h.finger_pos = (0.1, 0.2)
        self.assertFalse(self.h.calibrate())
        self.h.reset_center()
        self.assertEqual(self.h.center, (0.5, 0.5))


class SmoothUITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pygame.init()
        pygame.display.set_mode((1280, 800))

    @classmethod
    def tearDownClass(cls):
        pygame.quit()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.a = Arcade(
            enable_audio=False, save_path=Path(self.temp.name) / "scores.json"
        )
        self.a.hand.config_path = Path(self.temp.name) / "camera.json"

    def tearDown(self):
        self.a.hand.close()
        self.temp.cleanup()

    def test_high_resolution_canvas_and_bundled_fonts(self):
        self.assertEqual(
            self.a.draw().get_size(), (SCREEN_W * UI_SCALE, SCREEN_H * UI_SCALE)
        )
        self.assertTrue((FONT_ROOT / "DejaVuSans.ttf").is_file())
        self.assertGreater(self.a.fonts["big"].get_height(), 82)

    def test_camera_settings_pause_game_and_return_to_pause(self):
        a = self.a
        a.start()
        a.update(0.1)
        before = a.game.elapsed
        a.action("camera")
        a.update(2)
        self.assertEqual(a.state, State.CAMERA)
        self.assertEqual(a.game.elapsed, before)
        a.draw()
        self.assertIn("camera_toggle", a.buttons)
        self.assertNotIn("up", a.buttons)
        a.key(pygame.K_ESCAPE)
        self.assertEqual(a.state, State.PAUSE)

    def test_mouse_targets_remain_in_logical_coordinates(self):
        a = self.a
        a.draw()
        a.mouse = (600, 650)
        a.click()
        self.assertEqual(a.sel, 1)
        physical = (1200, 1300)
        self.assertEqual(pointer(physical, (2560, 1600)), (600, 650))

    def test_portrait_resolution_and_all_settings_render(self):
        for char in CHARACTERS:
            self.assertEqual(portrait(char, (690, 748)).get_size(), (690, 748))
        self.a.action("camera")
        self.a.draw()
        for device in ["auto", "0", "1", "2", "3"]:
            self.assertIn("device:" + device, self.a.buttons)


if __name__ == "__main__":
    unittest.main()
