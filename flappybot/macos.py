"""macOS glue: screen capture (mss), mouse clicks (Quartz), permissions."""
from __future__ import annotations

import ctypes
import subprocess

import numpy as np


class Screen:
    def __init__(self):
        import mss

        self._mss = mss.mss()

    def grab(self, region: dict, target_height: int = 300) -> np.ndarray:
        """Return an RGB uint8 image of the region, downscaled to ~target_height."""
        shot = self._mss.grab(region)
        a = np.frombuffer(shot.bgra, np.uint8).reshape(shot.height, shot.width, 4)
        step = max(1, int(round(shot.height / target_height)))
        return a[::step, ::step, 2::-1]  # BGRA -> RGB


def mouse_pos() -> tuple[float, float]:
    import Quartz

    p = Quartz.CGEventGetLocation(Quartz.CGEventCreate(None))
    return float(p.x), float(p.y)


def click(x: float, y: float):
    import Quartz

    pt = Quartz.CGPointMake(x, y)
    for kind in (Quartz.kCGEventLeftMouseDown, Quartz.kCGEventLeftMouseUp):
        ev = Quartz.CGEventCreateMouseEvent(None, kind, pt, Quartz.kCGMouseButtonLeft)
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, ev)


def has_screen_recording() -> bool:
    try:
        import Quartz

        return bool(Quartz.CGPreflightScreenCaptureAccess())
    except Exception:
        return True  # older macOS: no API, assume OK


def request_screen_recording():
    try:
        import Quartz

        Quartz.CGRequestScreenCaptureAccess()
    except Exception:
        pass
    subprocess.run(["open", "x-apple.systempreferences:com.apple.preference.security?Privacy_ScreenCapture"])


def has_accessibility() -> bool:
    try:
        lib = ctypes.cdll.LoadLibrary(
            "/System/Library/Frameworks/ApplicationServices.framework/ApplicationServices")
        lib.AXIsProcessTrusted.restype = ctypes.c_bool
        return bool(lib.AXIsProcessTrusted())
    except Exception:
        return True


def request_accessibility():
    subprocess.run(["open", "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility"])
