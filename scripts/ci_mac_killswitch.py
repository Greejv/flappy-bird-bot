"""CI check on a real Mac: does the global kill shortcut stop the bot process?

Starts a child process with the kill switch armed, then simulates the key
press system-wide (like a real keyboard would) and checks the child exited.
"""
import subprocess
import sys
import time

import Quartz

CHILD = """
import os, sys, time
sys.path.insert(0, '.')
from flappybot.macos import start_kill_switch
start_kill_switch(sys.argv[1], lambda: os._exit(7))
time.sleep(8)
os._exit(1)
"""


def key(code, down, flags=0):
    ev = Quartz.CGEventCreateKeyboardEvent(None, code, down)
    if flags:
        Quartz.CGEventSetFlags(ev, flags)
    Quartz.CGEventPost(Quartz.kCGHIDEventTap, ev)


def trial(hotkey, press):
    p = subprocess.Popen([sys.executable, "-c", CHILD, hotkey])
    time.sleep(1.5)
    t = time.perf_counter()
    press()
    try:
        rc = p.wait(timeout=5)
    except subprocess.TimeoutExpired:
        p.kill()
        rc = None
    ok = rc == 7
    print(f"{hotkey:12s} -> {'KILLED OK' if ok else 'NOT killed (rc=%s)' % rc}"
          f" in {(time.perf_counter() - t) * 1000:.0f} ms")
    return ok


def press_esc():
    key(53, True)
    time.sleep(0.15)
    key(53, False)


def press_ctrl_alt_k():
    ctrl, alt = Quartz.kCGEventFlagMaskControl, Quartz.kCGEventFlagMaskAlternate
    key(59, True, ctrl)          # left control
    key(58, True, ctrl | alt)    # left option
    key(40, True, ctrl | alt)    # k
    time.sleep(0.15)
    key(40, False, ctrl | alt)
    key(58, False, ctrl)
    key(59, False, 0)


results = [trial("esc", press_esc), trial("ctrl+alt+k", press_ctrl_alt_k)]
sys.exit(0 if all(results) else 1)
