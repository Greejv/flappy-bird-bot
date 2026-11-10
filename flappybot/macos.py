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


# --- global kill shortcut ----------------------------------------------------
# Works whichever app is in front (e.g. the browser with the game): we poll
# the system-wide key state instead of waiting for key events.

KEYCODES = {  # macOS virtual key codes (ANSI layout)
    "a": 0, "s": 1, "d": 2, "f": 3, "h": 4, "g": 5, "z": 6, "x": 7, "c": 8, "v": 9,
    "b": 11, "q": 12, "w": 13, "e": 14, "r": 15, "y": 16, "t": 17, "1": 18, "2": 19,
    "3": 20, "4": 21, "6": 22, "5": 23, "9": 25, "7": 26, "8": 28, "0": 29, "o": 31,
    "u": 32, "i": 34, "p": 35, "l": 37, "j": 38, "k": 40, "n": 45, "m": 46,
    "return": 36, "enter": 36, "tab": 48, "space": 49, "esc": 53, "escape": 53,
    "f1": 122, "f2": 120, "f3": 99, "f4": 118, "f5": 96, "f6": 97, "f7": 98, "f8": 100,
    "f9": 101, "f10": 109, "f11": 103, "f12": 111,
}
MODIFIERS = {"ctrl": "kCGEventFlagMaskControl", "control": "kCGEventFlagMaskControl",
             "alt": "kCGEventFlagMaskAlternate", "option": "kCGEventFlagMaskAlternate",
             "opt": "kCGEventFlagMaskAlternate", "cmd": "kCGEventFlagMaskCommand",
             "command": "kCGEventFlagMaskCommand", "shift": "kCGEventFlagMaskShift"}


def parse_hotkey(text: str) -> tuple[int, int]:
    """'esc' or 'ctrl+alt+k' -> (keycode, modifier mask). Raises ValueError."""
    import Quartz

    parts = [p.strip().lower() for p in text.replace("-", "+").split("+") if p.strip()]
    if not parts or parts[-1] not in KEYCODES:
        raise ValueError(f"unknown key in {text!r}; use e.g. esc, f12, ctrl+alt+k")
    mask = 0
    for m in parts[:-1]:
        if m not in MODIFIERS:
            raise ValueError(f"unknown modifier {m!r}; use ctrl, alt/option, cmd, shift")
        mask |= getattr(Quartz, MODIFIERS[m])
    return KEYCODES[parts[-1]], mask


def hotkey_pressed(keycode: int, mask: int) -> bool:
    import Quartz

    state = Quartz.kCGEventSourceStateCombinedSessionState
    if not Quartz.CGEventSourceKeyState(state, keycode):
        return False
    return (Quartz.CGEventSourceFlagsState(state) & mask) == mask


def start_kill_switch(hotkey: str, on_kill) -> None:
    """Background thread: calls on_kill() as soon as the hotkey is held."""
    import threading
    import time

    keycode, mask = parse_hotkey(hotkey)

    def watch():
        while True:
            try:
                if hotkey_pressed(keycode, mask):
                    on_kill()
                    return
            except Exception:
                pass
            time.sleep(0.01)

    threading.Thread(target=watch, name="kill-switch", daemon=True).start()
