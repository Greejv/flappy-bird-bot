"""A headless clone of the game's look & physics, used to test the bot.

It uses sprites cut from a real screenshot (tests/assets) and a busy
background with the same orange-red as the flags, so vision is tested
against the hard case. The physics constants are deliberately different
from the bot's built-in guesses so the online learning is exercised.
"""
from __future__ import annotations

import os
import random

import numpy as np
from PIL import Image

ASSETS = os.path.join(os.path.dirname(__file__), "assets")


def _load(name):
    return np.array(Image.open(os.path.join(ASSETS, name)))


class Sim:
    def __init__(self, H=600, W=800, seed=0, g=2.3, vj=-0.7, lag=0.05, speed=0.42,
                 gap=0.265, spacing=0.367, flag_rate=0.5, max_step=0.22, cube_rate=0.15,
                 rainbow=True):
        self.H, self.W = H, W
        self.rng = random.Random(seed)
        self.g, self.vj, self.lag, self.speed = g, vj, lag, speed
        self.gap, self.spacing, self.flag_rate = gap, spacing, flag_rate
        self.max_step = max_step
        self.cube_rate = cube_rate
        self.rainbow = rainbow
        self._c = 0.5
        self.bg = self._background()
        self.bird_img = self._scaled(_load("bird.png"), 0.047)
        money = self._scaled(_load("money.png"), 0.04)
        self.flag_img = self._flag()
        self.cube_img = self._cube()
        tile = _load("pillar_tile.png")
        pw = int(0.078 * H)
        tile = np.array(Image.fromarray(tile).resize((pw, int(tile.shape[0] * pw / tile.shape[1]))))
        # pillars & money cycle through the rainbow in the real game
        self.tiles = [self._hue(tile, k / 12) for k in range(12)]
        self.money_imgs = [self._hue(money, k / 12) for k in range(12)]
        self.tile = self.tiles[0]
        self.money_img = self.money_imgs[0]
        self.cubes = 0
        self.saves = 0
        self.log: list = []
        self.shield = False
        self.invuln = 0.0
        self.bird_x = W / H / 2
        self.deaths = 0
        self.money = 0
        self.life_money = 0
        self.lives: list[int] = []
        self.flags = 0
        self.t = 0.0
        self.reset()

    # -- assets -----------------------------------------------------------
    def _scaled(self, rgba, height_units):
        h = int(height_units * self.H)
        w = int(rgba.shape[1] * h / rgba.shape[0])
        return np.array(Image.fromarray(rgba).resize((w, h)))

    @staticmethod
    def _hue(rgba, shift):
        im = Image.fromarray(np.ascontiguousarray(rgba[..., :3]))
        hsv = np.array(im.convert("HSV"))
        hsv[..., 0] = (hsv[..., 0].astype(int) + int(shift * 255)) % 256
        rgb = np.array(Image.fromarray(hsv, "HSV").convert("RGB"))
        return np.dstack([rgb, rgba[..., 3:]]) if rgba.shape[2] == 4 else rgb

    def _flag(self):
        h, w = int(0.055 * self.H), int(0.045 * self.H)
        img = np.zeros((h, w, 4), np.uint8)
        img[:, : max(2, w // 8)] = (110, 110, 110, 255)  # grey pole
        cloth = img[: int(h * 0.6), w // 8:]
        cloth[...] = (225, 30, 30, 255)
        cloth[::3, ::2, :3] = (175, 20, 25)
        return img

    def _cube(self):
        n = int(0.05 * self.H)
        img = np.zeros((n, n, 4), np.uint8)
        img[...] = (60, 90, 230, 255)
        img[2:-2, 2:-2, :3] = (40, 70, 210)
        img[n // 2 - 2: n // 2 + 2, 6:-6:2, :3] = 240  # "YOLO" text
        return img

    def _background(self):
        H, W = self.H, self.W
        y, x = np.mgrid[0:H, 0:W]
        bg = np.zeros((H, W, 3), np.uint8)
        bg[:] = (232, 232, 232)
        bg[(x < W * 0.2) | (x > W * 0.8)] = (25, 35, 110)
        stripe = np.abs((x - W * 0.5) * 0.6 - (y - H * 0.5)) < H * 0.06
        stripe |= np.abs((x - W * 0.5) * -0.6 - (y - H * 0.5)) < H * 0.06
        bg[stripe] = (205, 30, 40)  # nearly the same red as flags!
        face = ((x - W / 2) / (W * 0.25)) ** 2 + ((y - H * 0.55) / (H * 0.45)) ** 2 < 1
        bg[face] = (165, 147, 98)
        glasses = np.abs(((x - W / 2) / (W * 0.2)) ** 2 + ((y - H * 0.5) / (H * 0.08)) ** 2 - 1) < 0.15
        bg[glasses] = (15, 15, 15)
        hair = face & (y < H * 0.22)
        bg[hair] = (40, 30, 25)
        # static HUD: speaker, money + flag counters
        bg[int(H * .07):int(H * .11), int(W * .03):int(W * .07)] = (40, 230, 120)
        bg[int(H * .17):int(H * .2), int(W * .03):int(W * .07)] = (60, 140, 100)
        bg[int(H * .26):int(H * .29), int(W * .035):int(W * .06)] = (225, 30, 30)
        return bg

    # -- world --------------------------------------------------------------
    def reset(self):
        self.y = 0.45
        self.vy = 0.0
        self.pending: list[float] = []
        self.objects: list[dict] = []  # pillars + items
        self.next_x = self.W / self.H + 0.2
        self.alive_t = 0.0

    def _spawn(self):
        while self.next_x < self.W / self.H + 0.5:
            # neighbouring gaps differ by <= max_step (real game: ~0.2)
            c = min(0.73, max(0.27, self._c + self.rng.uniform(-self.max_step, self.max_step)))
            self._c = c
            self.objects.append({"k": "pillar", "x": self.next_x, "top": c - self.gap / 2, "bot": c + self.gap / 2})
            ix = self.next_x + self.spacing / 2 + 0.03
            ys = [self.rng.uniform(0.15, 0.85)]
            if self.rng.random() < self.flag_rate:
                ys.append(self.rng.uniform(0.15, 0.85))
            self.objects.append({"k": "money", "x": ix, "y": ys[0]})
            if len(ys) > 1 and abs(ys[1] - ys[0]) > 0.12:
                self.objects.append({"k": "flag", "x": ix, "y": ys[1]})
            if self.rng.random() < self.cube_rate:
                cy = self.rng.uniform(0.2, 0.8)
                if all(abs(cy - v) > 0.1 for v in ys):
                    self.objects.append({"k": "cube", "x": ix + 0.1, "y": cy})
            self.next_x += self.spacing

    def click(self, t_click):
        self.pending.append(t_click + self.lag)

    def step(self, dt):
        self.t += dt
        self.alive_t += dt
        self._spawn()
        for tp in [p for p in self.pending if p <= self.t]:
            self.vy = self.vj
            self.pending.remove(tp)
        self.y += self.vy * dt + 0.5 * self.g * dt * dt
        self.vy += self.g * dt
        for o in self.objects:
            o["x"] -= self.speed * dt
        self.next_x -= self.speed * dt
        self.objects = [o for o in self.objects if o["x"] > -0.3]
        # collisions (hitbox a bit smaller than the sprite)
        hb = 0.019
        bx0, bx1 = self.bird_x - hb, self.bird_x + hb
        dead = self.y - hb < 0 or self.y + hb > 1
        if dead:
            self.log.append(("edge", round(self.t, 2), round(self.y, 3)))
        self.invuln = max(0.0, self.invuln - dt)
        pw = 0.078
        size = {"flag": (0.045, 0.025), "money": (0.06, 0.02), "cube": (0.05, 0.025)}
        for o in list(self.objects):
            if o["k"] == "pillar":
                if o["x"] < bx1 and o["x"] + pw > bx0 and (self.y - hb < o["top"] or self.y + hb > o["bot"]):
                    if self.invuln > 0:
                        pass
                    elif self.shield:
                        self.log.append(("pillar-shielded", round(self.t, 2), round(self.y, 3), o["top"], o["bot"]))
                        self.shield, self.invuln = False, 0.6
                        self.saves += 1
                    else:
                        self.log.append(("pillar", round(self.t, 2), round(self.y, 3), o["top"], o["bot"]))
                        dead = True
            else:
                w, hh = size[o["k"]]
                if o["x"] < bx1 and o["x"] + w > bx0 and abs(o["y"] - self.y) < hh + hb:
                    if o["k"] == "money":
                        self.money += 1
                        self.life_money += 1
                    elif o["k"] == "cube":
                        self.cubes += 1
                        self.shield = True
                    elif self.shield or self.invuln > 0:
                        if self.shield:
                            self.saves += 1
                        self.shield = False
                    else:
                        self.log.append(("flag", round(self.t, 2), round(self.y, 3), o["y"]))
                        self.flags += 1
                    self.objects.remove(o)
        if dead:
            self.deaths += 1
            self.lives.append(self.life_money)
            self.life_money = 0
            self.shield = False
            self.reset()
        return dead

    # -- rendering ------------------------------------------------------------
    def _blit(self, f, img, cx, cy):
        H = self.H
        h, w = img.shape[:2]
        x0, y0 = int(cx * H - w / 2), int(cy * H - h / 2)
        sx0, sy0 = max(0, -x0), max(0, -y0)
        x0c, y0c = max(0, x0), max(0, y0)
        x1c, y1c = min(self.W, x0 + w), min(H, y0 + h)
        if x1c <= x0c or y1c <= y0c:
            return
        src = img[sy0:sy0 + y1c - y0c, sx0:sx0 + x1c - x0c]
        a = src[..., 3:4] / 255.0
        dst = f[y0c:y1c, x0c:x1c]
        dst[:] = (dst * (1 - a) + src[..., :3] * a).astype(np.uint8)

    def _pillar(self, f, x, top, bot):
        H, W = self.H, self.W
        pw = self.tile.shape[1]
        px = int(x * H)
        cap = int(0.035 * H)
        for y0, y1 in ((0, int(top * H)), (int(bot * H), H)):
            if y1 <= y0:
                continue
            reps = (y1 - y0) // self.tile.shape[0] + 2
            col = np.tile(self.tile, (reps, 1, 1))[: y1 - y0]
            xs0, xs1 = max(0, px), min(W, px + pw)
            if xs1 <= xs0:
                continue
            f[y0:y1, xs0:xs1] = col[:, xs0 - px: xs1 - px]
            # cap with grey border, a bit wider
            cy0 = max(y0, y1 - cap) if y0 == 0 else y0
            cy1 = cy0 + cap
            cx0, cx1 = max(0, px - 4), min(W, px + pw + 4)
            if cx1 > cx0:
                f[cy0:cy1, cx0:cx1] = (100, 100, 100)
                ix0, ix1 = max(0, px - 1), min(W, px + pw + 1)
                if ix1 > ix0:
                    f[cy0 + 3:cy1 - 3, ix0:ix1] = col[3:cap - 3, : ix1 - ix0] if ix1 - ix0 <= pw else (176, 192, 64)

    def render(self):
        k = int(self.t * 2) % 12 if self.rainbow and self.t % 14 > 7 else 0
        self.tile, self.money_img = self.tiles[k], self.money_imgs[k]
        f = self.bg.copy()
        for o in self.objects:
            if o["k"] == "pillar":
                self._pillar(f, o["x"], o["top"], o["bot"])
        for o in self.objects:
            if o["k"] == "money":
                self._blit(f, self.money_img, o["x"] + 0.03, o["y"])
            elif o["k"] == "flag":
                self._blit(f, self.flag_img, o["x"] + 0.0225, o["y"])
            elif o["k"] == "cube":
                self._blit(f, self.cube_img, o["x"] + 0.025, o["y"])
        # scrolling ticker text at the bottom + score digits (top right)
        H, W = self.H, self.W
        off = int(self.t * 0.2 * H) % 40
        for x0 in range(-off, W, 40):
            f[int(H * .935):int(H * .965), max(0, x0):max(0, x0 + 24)] = (225, 225, 225)
        for i, ch in enumerate(str(self.money)[-4:]):
            v = 120 + 14 * int(ch)
            f[int(H * .14):int(H * .18), int(W * .89) + 12 * i:int(W * .89) + 12 * i + 9] = (v, v, v)
        self._blit(f, self.bird_img, self.bird_x, self.y)
        return f
