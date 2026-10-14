"""Nonblocking webcam capture and current/legacy MediaPipe hand tracking.

Only immutable image bytes cross the worker boundary. Pygame surfaces and
movement gestures are handled on the application thread.
"""

from dataclasses import dataclass
from pathlib import Path
import importlib
import json
import math
import platform
import threading
import time
import pygame

PREVIEW_W, PREVIEW_H = 180, 135
DEAD_ZONE = 0.20
FRAME_SIZE = (640, 480)
MODEL_PATH = (
    Path(__file__).resolve().parent.parent
    / "assets"
    / "models"
    / "hand_landmarker.task"
)


class GestureFilter:
    """Hysteresis, smoothing, stable samples and mandatory neutral arming."""

    def __init__(self, center=(0.5, 0.5)):
        self.center = center
        self.reset()

    def reset(self):
        self.armed = False
        self.smoothed = None
        self.neutral_frames = 0
        self.candidate = None
        self.candidate_frames = 0
        self.last_move = -100.0

    def sample(self, tip, now):
        if tip is None or not all(math.isfinite(v) for v in tip):
            self.reset()
            return None
        if self.smoothed is None:
            self.smoothed = tip
        else:
            self.smoothed = tuple(
                a + (b - a) * 0.55 for a, b in zip(self.smoothed, tip)
            )
        dx, dy = (self.smoothed[0] - self.center[0], self.smoothed[1] - self.center[1])
        if abs(dx) < 0.12 and abs(dy) < 0.12:
            self.neutral_frames += 1
            self.candidate = None
            self.candidate_frames = 0
            if self.neutral_frames >= 2:
                self.armed = True
            return None
        self.neutral_frames = 0
        if max(abs(dx), abs(dy)) < DEAD_ZONE or not self.armed:
            self.candidate = None
            self.candidate_frames = 0
            return None
        direction = (
            ("right" if dx > 0 else "left")
            if abs(dx) > abs(dy)
            else ("down" if dy > 0 else "up")
        )
        self.candidate_frames = (
            self.candidate_frames + 1 if direction == self.candidate else 1
        )
        self.candidate = direction
        if self.candidate_frames >= 3 and now - self.last_move >= 0.22:
            self.last_move = now
            self.armed = False
            self.candidate = None
            self.candidate_frames = 0
            return direction
        return None


class HandDetector:
    """Prefer Tasks VIDEO mode; use legacy Hands for older compatible installs."""

    def __init__(self, mp=None, model_path=MODEL_PATH):
        self.mp = mp if mp is not None else importlib.import_module("mediapipe")
        self.last_timestamp = -1
        tasks = getattr(self.mp, "tasks", None)
        if tasks is not None and hasattr(tasks, "vision"):
            if not Path(model_path).is_file():
                raise FileNotFoundError(
                    "Missing assets/models/hand_landmarker.task. Extract the entire ZIP."
                )
            options = tasks.vision.HandLandmarkerOptions(
                base_options=tasks.BaseOptions(
                    model_asset_buffer=Path(model_path).read_bytes()
                ),
                running_mode=tasks.vision.RunningMode.VIDEO,
                num_hands=1,
                min_hand_detection_confidence=0.5,
                min_hand_presence_confidence=0.5,
                min_tracking_confidence=0.5,
            )
            self.detector = tasks.vision.HandLandmarker.create_from_options(options)
            self.api = "MediaPipe Tasks"
        elif hasattr(self.mp, "solutions"):
            self.detector = self.mp.solutions.hands.Hands(
                max_num_hands=1,
                model_complexity=0,
                min_detection_confidence=0.5,
                min_tracking_confidence=0.5,
            )
            self.api = "MediaPipe Hands"
        else:
            raise RuntimeError(
                "This MediaPipe build has no hand API. Run setup_camera.bat."
            )

    def process(self, rgb, timestamp_ms):
        if self.api == "MediaPipe Tasks":
            stamp = max(self.last_timestamp + 1, int(timestamp_ms))
            self.last_timestamp = stamp
            image = self.mp.Image(image_format=self.mp.ImageFormat.SRGB, data=rgb)
            result = self.detector.detect_for_video(image, stamp)
            hands = result.hand_landmarks
        else:
            result = self.detector.process(rgb)
            hands = [hand.landmark for hand in result.multi_hand_landmarks or []]
        if not hands:
            return None, ()
        points = tuple((float(p.x), float(p.y)) for p in hands[0])
        return points[8], points

    def close(self):
        self.detector.close()


@dataclass(frozen=True)
class CameraFrame:
    sequence: int
    pixels: bytes
    tip: tuple[float, float] | None
    landmarks: tuple
    captured_at: float


class HandControl:
    def __init__(self, config_path=None, cv_loader=None, detector_factory=None):
        self.config_path = (
            Path(config_path)
            if config_path
            else Path.home() / ".crossy_neon" / "camera.json"
        )
        self.device = None
        self.mirror = True
        center = (0.5, 0.5)
        try:
            saved = json.loads(self.config_path.read_text())
            device = saved.get("device")
            self.device = (
                device if isinstance(device, int) and 0 <= device <= 3 else None
            )
            self.mirror = bool(saved.get("mirror", True))
            candidate = saved.get("center", center)
            if len(candidate) == 2 and all(0.25 <= float(x) <= 0.75 for x in candidate):
                center = tuple(map(float, candidate))
        except (OSError, ValueError, TypeError, AttributeError):
            pass
        self.gestures = GestureFilter(center)
        self.cv_loader = cv_loader or (lambda: importlib.import_module("cv2"))
        self.detector_factory = detector_factory or HandDetector
        self.ok = self.running = self.tracking_available = False
        self.preview = None
        self.finger_pos = None
        self.landmarks = ()
        self.status = "CAMERA OFF"
        self.detail = "Open camera settings to select a device and test hand control."
        self.active_device = None
        self.backend = ""
        self.api = ""
        self._lock = threading.Lock()
        self._frame = None
        self._seen_sequence = -1
        self._stop = threading.Event()
        self._thread = None
        self._started_at = 0.0

    @property
    def armed(self):
        return self.gestures.armed

    @property
    def center(self):
        return self.gestures.center

    def _status(self, status, detail=""):
        with self._lock:
            self.status = status
            self.detail = detail

    def _save_config(self):
        try:
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            temp = self.config_path.with_suffix(".tmp")
            temp.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "device": self.device,
                        "mirror": self.mirror,
                        "center": self.center,
                    }
                )
            )
            temp.replace(self.config_path)
            return True
        except OSError:
            self.detail = (
                "Camera settings work for this session, but could not be saved."
            )
            return False

    def toggle(self):
        if self.running or self.ok:
            self.close()
        else:
            self.start()

    def start(self):
        if self._thread is not None and self._thread.is_alive():
            if not self.running:
                self._status(
                    "CAMERA BUSY",
                    "The previous camera is closing. Please retry in a moment.",
                )
            return False
        self._stop = threading.Event()
        self._frame = None
        self._seen_sequence = -1
        self.gestures.reset()
        self.preview = None
        self.finger_pos = None
        self.landmarks = ()
        self.ok = False
        self.tracking_available = False
        self.running = True
        self._status(
            "STARTING CAMERA",
            "Loading the device and hand tracker in the background...",
        )
        self._started_at = time.monotonic()
        self._thread = threading.Thread(
            target=self._worker,
            args=(self._stop, self.device, self.mirror),
            daemon=True,
            name="parkside-camera",
        )
        self._thread.start()
        return True

    def retry(self):
        self.close()
        return self.start()

    def select_device(self, device):
        if device not in (None, 0, 1, 2, 3):
            raise ValueError("Camera device must be Auto or 0..3")
        was_on = self.running
        self.close()
        self.device = device
        self._save_config()
        if was_on:
            self.start()

    def calibrate(self):
        if self.finger_pos is None:
            self._status(
                "SHOW YOUR HAND",
                "Show your index finger in the preview before calibrating.",
            )
            return False
        if not all(0.25 <= v <= 0.75 for v in self.finger_pos):
            self._status(
                "MOVE TOWARD CENTER",
                "Hold the fingertip away from the frame edges, then calibrate again.",
            )
            return False
        self.gestures.center = self.finger_pos
        self.gestures.reset()
        self._save_config()
        self._status(
            "CENTER SAVED",
            "Hold still in the center, then move your finger out to hop.",
        )
        return True

    def reset_center(self):
        self.gestures.center = (0.5, 0.5)
        self.gestures.reset()
        self._save_config()

    def _open_camera(self, cv2, stop, device):
        devices = [0, 1, 2] if device is None else [device]
        backends = (
            [
                getattr(cv2, "CAP_DSHOW", 700),
                getattr(cv2, "CAP_MSMF", 1400),
                getattr(cv2, "CAP_ANY", 0),
            ]
            if platform.system() == "Windows"
            else [getattr(cv2, "CAP_ANY", 0)]
        )
        failures = []
        for index in devices:
            for backend in dict.fromkeys(backends):
                if stop.is_set():
                    return None, None
                cap = None
                try:
                    cap = cv2.VideoCapture(index, backend)
                    if cap.isOpened():
                        for prop, value in [
                            ("CAP_PROP_FRAME_WIDTH", 640),
                            ("CAP_PROP_FRAME_HEIGHT", 480),
                            ("CAP_PROP_FPS", 30),
                            ("CAP_PROP_BUFFERSIZE", 1),
                        ]:
                            cap.set(getattr(cv2, prop), value)
                        for _ in range(4):
                            if stop.is_set():
                                break
                            good, frame = cap.read()
                            if good and frame is not None and frame.size > 0:
                                self.active_device = index
                                self.backend = {
                                    700: "DirectShow",
                                    1400: "MSMF",
                                    0: "Auto",
                                }.get(backend, str(backend))
                                return cap, frame
                            if stop.wait(0.06):
                                break
                except Exception as exc:
                    failures.append(str(exc))
                if cap is not None:
                    try:
                        cap.release()
                    except Exception:
                        pass
        if not stop.is_set():
            self._status(
                "NO CAMERA FRAMES",
                "No working frames from device "
                + str(device if device is not None else "0, 1 or 2")
                + ". Check Windows camera access for desktop apps, close other camera apps, or choose another device."
                + (" " + failures[-1][:110] if failures else ""),
            )
        return None, None

    def _worker(self, stop, device, mirror):
        cap = detector = None
        try:
            try:
                cv2 = self.cv_loader()
            except Exception as exc:
                self._status(
                    "OPENCV NOT AVAILABLE",
                    "Run setup_camera.bat, then retry. " + str(exc)[:150],
                )
                return
            cap, frame = self._open_camera(cv2, stop, device)
            if cap is None or stop.is_set():
                return
            try:
                detector = self.detector_factory()
                self.api = detector.api
                self.tracking_available = True
            except Exception as exc:
                self.api = "Preview only"
                self._status(
                    "PREVIEW ONLY",
                    "Hand tracking could not load. Run setup_camera.bat. "
                    + str(exc)[:150],
                )
            sequence = 0
            lost = 0
            while not stop.is_set():
                if frame is None:
                    good, frame = cap.read()
                    if not good or frame is None or frame.size == 0:
                        frame = None
                        lost += 1
                        if lost >= 20:
                            self._status(
                                "CAMERA DISCONNECTED",
                                "The camera stopped sending frames. Reconnect it and press Retry.",
                            )
                            break
                        stop.wait(0.05)
                        continue
                if stop.is_set():
                    break
                lost = 0
                rgb = cv2.cvtColor(
                    cv2.flip(frame, 1) if mirror else frame, cv2.COLOR_BGR2RGB
                )
                rgb = cv2.resize(rgb, (640, 480))
                captured = time.monotonic()
                tip, points = (None, ())
                if detector is not None:
                    tip, points = detector.process(rgb, int(captured * 1000))
                if stop.is_set():
                    break
                small = cv2.resize(rgb, FRAME_SIZE)
                sequence += 1
                snapshot = CameraFrame(sequence, small.tobytes(), tip, points, captured)
                with self._lock:
                    self._frame = snapshot
                    self.ok = True
                frame = None
                stop.wait(0.015)
        except Exception as exc:
            if not stop.is_set():
                self._status(
                    "CAMERA ERROR",
                    "Retry the camera. " + type(exc).__name__ + ": " + str(exc)[:180],
                )
        finally:
            if detector is not None:
                try:
                    detector.close()
                except Exception:
                    pass
            if cap is not None:
                try:
                    cap.release()
                except Exception:
                    pass
            self.running = False
            self.ok = False
            if stop.is_set():
                self.active_device = None
            if not stop.is_set():
                with self._lock:
                    self._frame = None

    def read(self):
        """Poll newest snapshot; this method never reads a camera or runs inference."""
        if not self.running:
            self.preview = None
            self.finger_pos = None
            self.landmarks = ()
            self.gestures.reset()
            return None
        with self._lock:
            frame = self._frame
        if frame is None or time.monotonic() - frame.captured_at > 1.0:
            self.gestures.reset()
            self.finger_pos = None
            self.landmarks = ()
            self.preview = None
            if frame is not None or time.monotonic() - self._started_at > 8.0:
                self._status(
                    "WAITING FOR CAMERA",
                    "No recent frames. Check the cable or permissions, then press Retry.",
                )
            return None
        if frame.sequence == self._seen_sequence:
            return None
        self._seen_sequence = frame.sequence
        self.preview = pygame.image.frombuffer(frame.pixels, FRAME_SIZE, "RGB").copy()
        self.finger_pos = frame.tip
        self.landmarks = frame.landmarks
        move = self.gestures.sample(frame.tip, frame.captured_at)
        if self.tracking_available:
            self.status = (
                "SHOW YOUR HAND"
                if frame.tip is None
                else (
                    "HOP TRIGGERED"
                    if move
                    else "READY TO HOP" if self.armed else "RETURN TO CENTER"
                )
            )
            self.detail = "Center the fingertip to arm a hop. Move beyond the box, then return to center."
        return move

    def close(self):
        self._stop.set()
        self.running = False
        self.ok = False
        if (
            self._thread is not None
            and self._thread.is_alive()
            and self._thread is not threading.current_thread()
        ):
            self._thread.join(timeout=0.25)
        with self._lock:
            self._frame = None
        self.preview = None
        self.finger_pos = None
        self.landmarks = ()
        self.tracking_available = False
        self.active_device = None
        self.gestures.reset()
        self._status("CAMERA OFF", "Camera closed. Use Start camera to reconnect.")
