"""Run inside the game's Python environment to diagnose a real webcam."""

import argparse
import importlib.metadata
import sys
import time
from parkside.hand import HandControl


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--device", choices=["auto", "0", "1", "2", "3"], default="auto"
    )
    args = parser.parse_args()
    print("Python:", sys.version.split()[0])
    print("Interpreter:", sys.executable)
    for package in ["pygame-ce", "mediapipe", "opencv-contrib-python", "opencv-python"]:
        try:
            print(package + ":", importlib.metadata.version(package))
        except importlib.metadata.PackageNotFoundError:
            print(package + ": not installed")
    hand = HandControl()
    hand.device = None if args.device == "auto" else int(args.device)
    try:
        hand.start()
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            hand.read()
            if hand.preview is not None or not hand.running:
                break
            time.sleep(0.05)
        print("Status:", hand.status)
        print("Details:", hand.detail)
        print(
            "Active camera:",
            hand.active_device,
            "Backend:",
            hand.backend,
            "Tracker:",
            hand.api,
        )
        print("Preview:", hand.preview is not None, "Landmarks:", len(hand.landmarks))
        return 0 if hand.preview is not None and hand.tracking_available else 1
    finally:
        hand.close()


if __name__ == "__main__":
    raise SystemExit(main())
