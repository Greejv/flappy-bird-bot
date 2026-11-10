"""Entry point: python -m flappybot  (or double-click 'Start Bot.command')."""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

import numpy as np

from .brain import Bot

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG = os.path.join(os.path.expanduser("~"), ".flappybot.json")
DEBUG_DIR = os.path.join(HERE, "debug")

BANNER = r"""
  ___ _                        ___      _
 | __| |__ _ _ __ _ __ _  _   | _ ) ___| |_
 | _|| / _` | '_ \ '_ \ || |  | _ \/ _ \  _|
 |_| |_\__,_| .__/ .__/\_, |  |___/\___/\__|
            |_|  |_|   |__/
"""


def say(msg=""):
    print(msg, flush=True)


def load_cfg() -> dict:
    try:
        with open(CONFIG) as f:
            return json.load(f)
    except Exception:
        return {}


def save_cfg(cfg: dict):
    with open(CONFIG, "w") as f:
        json.dump(cfg, f, indent=2)


def countdown_point(label: str, seconds: int = 4) -> tuple[float, float]:
    from .macos import mouse_pos

    say(f"\n  -> Move your mouse to the {label} of the game (don't click).")
    for i in range(seconds, 0, -1):
        print(f"     capturing in {i}...  ", end="\r", flush=True)
        time.sleep(1)
    p = mouse_pos()
    say(f"     got {label}: x={p[0]:.0f}  y={p[1]:.0f}          ")
    return p


def select_region() -> dict:
    say("\n=== Select the game area ===")
    say("Open the game so it is fully visible (best: browser window maximised).")
    input("Press ENTER when ready... ")
    while True:
        x0, y0 = countdown_point("TOP-LEFT corner")
        x1, y1 = countdown_point("BOTTOM-RIGHT corner")
        w, h = int(x1 - x0), int(y1 - y0)
        if w > 150 and h > 150:
            return {"left": int(x0), "top": int(y0), "width": w, "height": h}
        say(f"That area is too small ({w}x{h}). Let's try again.")


def check_permissions():
    from .macos import (has_accessibility, has_screen_recording,
                        request_accessibility, request_screen_recording)

    while True:
        sr, ax = has_screen_recording(), has_accessibility()
        if sr and ax:
            return
        say("\n=== macOS permissions needed (one time) ===")
        if not sr:
            say(" * Screen Recording: lets the bot SEE the game.")
            request_screen_recording()
        if not ax:
            say(" * Accessibility: lets the bot CLICK.")
            request_accessibility()
        say("System Settings > Privacy & Security is opening. Turn ON 'Terminal'")
        say("in the list(s) above (use + if it's missing). macOS may ask you to")
        say("quit & reopen Terminal: do that, then double-click 'Start Bot.command' again.")
        input("Press ENTER after enabling to re-check (Ctrl+C to quit)... ")


def annotate(img: np.ndarray, bot: Bot, path: str):
    from PIL import Image, ImageDraw

    im = Image.fromarray(np.ascontiguousarray(img))
    d = ImageDraw.Draw(im)
    s = img.shape[0]
    sc = bot.scene
    if sc is None:
        im.save(path)
        return
    for p in sc.pillars:
        d.rectangle([p.x0 * s, 0, p.x1 * s, p.gap_top * s], outline=(255, 0, 255), width=2)
        d.rectangle([p.x0 * s, p.gap_bot * s, p.x1 * s, s - 1], outline=(255, 0, 255), width=2)
    for b in sc.money:
        d.rectangle([b.x0 * s, b.y0 * s, b.x1 * s, b.y1 * s], outline=(0, 255, 0), width=2)
    for b in sc.flags:
        d.rectangle([b.x0 * s, b.y0 * s, b.x1 * s, b.y1 * s], outline=(255, 0, 0), width=2)
    for b in sc.cubes:
        d.rectangle([b.x0 * s, b.y0 * s, b.x1 * s, b.y1 * s], outline=(255, 255, 0), width=2)
    if sc.bird:
        b = sc.bird
        d.rectangle([b.x0 * s, b.y0 * s, b.x1 * s, b.y1 * s], outline=(0, 128, 255), width=3)
    im.save(path)


def describe(bot: Bot) -> str:
    sc = bot.scene
    return (f"bird={'YES' if sc and sc.bird else 'no'}  pillars={len(sc.pillars) if sc else 0}  "
            f"money={len(sc.money) if sc else 0}  flags={len(sc.flags) if sc else 0}  "
            f"shield={len(sc.cubes) if sc else 0}")


def main(argv=None):
    ap = argparse.ArgumentParser(description="Auto-player for the flappy money game")
    ap.add_argument("--reselect", action="store_true", help="choose the game area again")
    ap.add_argument("--test", action="store_true", help="capture once, save debug image, exit")
    ap.add_argument("--debug", action="store_true", help="save annotated frames to ./debug")
    ap.add_argument("--flag-weight", type=float, default=10.0, help="how hard to avoid flags")
    ap.add_argument("--money-weight", type=float, default=1.0, help="how hard to chase money")
    ap.add_argument("--shield-weight", type=float, default=2.0, help="how hard to chase the blue YOLO shield")
    a = ap.parse_args(argv)

    say(BANNER)
    if sys.platform != "darwin":
        say("This bot drives a Mac (screen capture + clicks). Run it on macOS.")
        return 1
    check_permissions()
    from .macos import Screen, click, mouse_pos

    cfg = load_cfg()
    region = cfg.get("region")
    if region and not a.reselect:
        r = region
        ans = input(f"Use saved game area {r['width']}x{r['height']} at ({r['left']},{r['top']})? [Y/n] ")
        if ans.strip().lower().startswith("n"):
            region = None
    if not region or a.reselect:
        region = select_region()
        cfg["region"] = region
        save_cfg(cfg)

    screen = Screen()
    bot = Bot(money_weight=a.money_weight, flag_weight=a.flag_weight, cube_weight=a.shield_weight)
    img = screen.grab(region)
    os.makedirs(DEBUG_DIR, exist_ok=True)
    bot.step(img, time.perf_counter(), time.perf_counter())
    annotate(img, bot, os.path.join(DEBUG_DIR, "check.png"))
    say(f"\nFirst look at the game: {describe(bot)}")
    say(f"(saved what the bot sees to {os.path.join(DEBUG_DIR, 'check.png')})")
    if img.std() < 3:
        say("!! The capture is blank. Screen Recording permission is probably missing for Terminal.")
    if a.test:
        return 0

    cx = region["left"] + region["width"] * cfg.get("click_x", 0.5)
    cy = region["top"] + region["height"] * cfg.get("click_y", 0.6)

    def inside(p):
        return (region["left"] <= p[0] <= region["left"] + region["width"]
                and region["top"] <= p[1] <= region["top"] + region["height"])

    say("\n=== Running ===")
    say(" * Move the mouse INTO the game to start / resume.")
    say(" * Move the mouse OUT of the game to pause.")
    say(" * Press Ctrl+C in this window to quit.\n")

    taps = 0
    frames = 0
    last_status = time.perf_counter()
    paused = True
    last_debug = 0.0
    try:
        while True:
            t0 = time.perf_counter()
            img = screen.grab(region)
            t1 = time.perf_counter()
            t_frame = (t0 + t1) / 2
            now_paused = not inside(mouse_pos())
            if now_paused != paused:
                paused = now_paused
                say("\n[paused - mouse is outside the game]" if paused else "\n[playing]")
            tap = bot.step(img, t_frame, time.perf_counter())
            if tap and not paused:
                click(cx, cy)
                taps += 1
            elif tap:
                bot.learn.taps.pop()  # didn't really tap
            frames += 1
            if a.debug and t1 - last_debug > 0.25:
                last_debug = t1
                annotate(img, bot, os.path.join(DEBUG_DIR, f"frame_{int(t1 * 1000)}.png"))
            if t1 - last_status > 0.5:
                fps = frames / (t1 - last_status)
                frames, last_status = 0, t1
                p = bot.learn.p
                seen = bot.scene is not None and bot.scene.bird is not None
                state = "PAUSED " if paused else ("PLAYING" if seen else "waiting for bird")
                print(f"\r{state:16s} fps={fps:4.0f} taps={taps:5d}  {describe(bot)}  "
                      f"g={p.g:.2f} jump={p.vj:.2f} lag={p.lag * 1000:.0f}ms speed={p.speed:.2f}"
                      f"{'' if p.calibrated else ' (learning)'}   ", end="", flush=True)
    except KeyboardInterrupt:
        say("\n\nBye! Total taps: %d" % taps)
    return 0


if __name__ == "__main__":
    sys.exit(main())
