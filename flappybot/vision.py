"""Turns a screenshot of the game into a list of objects.

All coordinates returned are in "game units": 1.0 == the height of the game
area, so the logic is independent of window size and Retina scaling.

Colours were measured from a real screenshot of the game:
  * bird (green spider) .... neon green  ~ (0, 240, 112) with black outline
  * money stack ............ teal green  ~ (48..80, 128..160, 96) + white band
  * red flag ............... orange red  ~ (192, 64, 0)
  * pillars ................ leopard print, lime ~ (176, 192, 64) / olive
                             ~ (144, 144, 16) with black spots
The background is an arbitrary photo (it can contain the same red as the
flags, e.g. a Union Jack), so money/flags are additionally filtered with a
background model: only pixels that are *moving* count.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from scipy import ndimage


@dataclass
class Box:
    x0: float
    x1: float
    y0: float
    y1: float

    @property
    def cx(self) -> float:
        return (self.x0 + self.x1) / 2

    @property
    def cy(self) -> float:
        return (self.y0 + self.y1) / 2


@dataclass
class Pillar:
    x0: float
    x1: float
    gap_top: float
    gap_bot: float


@dataclass
class Scene:
    width: float  # game width in units (height == 1)
    bird: Box | None = None
    pillars: list[Pillar] = field(default_factory=list)
    money: list[Box] = field(default_factory=list)
    flags: list[Box] = field(default_factory=list)
    cubes: list[Box] = field(default_factory=list)  # blue YOLO shield


def _channels(f: np.ndarray):
    return f[..., 0], f[..., 1], f[..., 2]


def bird_mask(f):
    r, g, b = _channels(f)
    return (g > 185) & (r < 120) & (b > 40) & (b < 200) & (g - b > 55) & (g - r > 90)


def money_mask(f):
    r, g, b = _channels(f)
    return (g > r + 35) & (g > b + 12) & (g > 85) & (g < 215) & (r < 140) & ~bird_mask(f)


def pale_mask(f):
    r, g, b = _channels(f)
    return (r > 160) & (g > 195) & (b > 160) & (g >= r)


def red_mask(f):
    r, g, b = _channels(f)
    return (r > 115) & (r > 2 * g) & (r > 2 * b + 20)


def leopard_mask(f):
    r, g, b = _channels(f)
    return (g > 95) & (b * 10 < g * 6) & (r * 10 > g * 7) & (r * 10 < g * 13)


class BackgroundModel:
    """Learns the static background: a pixel that stays unchanged for
    ``stable_frames`` consecutive frames is background. Everything that
    differs from it is foreground (moving sprites).

    Both tests use the full colour difference |dR|+|dG|+|dB| (a packed
    single channel lets different colours collide)."""

    def __init__(self, stable_frames: int = 8, still_tol: int = 30, fg_tol: int = 60):
        self.stable_frames = stable_frames
        self.still_tol = still_tol
        self.fg_tol = fg_tol
        self.bg = None
        self.prev = None
        self.count = None

    def update(self, f: np.ndarray) -> np.ndarray:
        if self.bg is None or self.bg.shape != f.shape:
            self.bg = f.copy()
            self.prev = f.copy()
            self.count = np.zeros(f.shape[:2], np.uint8)
            return np.ones(f.shape[:2], bool)
        d = np.abs(f - self.prev)
        still = (d[..., 0] + d[..., 1] + d[..., 2]) < self.still_tol
        self.count += still
        self.count[~still] = 0
        np.minimum(self.count, 200, out=self.count)
        learn = self.count >= self.stable_frames
        np.copyto(self.bg, f, where=learn[..., None])
        self.prev = f
        d = np.abs(f - self.bg)
        return (d[..., 0] + d[..., 1] + d[..., 2]) > self.fg_tol


class Vision:
    """Colour-independent detector.

    Pillars and money cycle through rainbow colours, so they are found by
    MOTION (difference from the learned background photo) and SHAPE:
      * pillar  = tall moving column attached to the top and/or bottom edge
      * money   = wide moving blob with a white/pale paper band (any hue)
      * flag    = squarish moving blob that is mostly pure red
      * cube    = squarish moving blob that is mostly blue (YOLO shield)
    Only the bird (neon green spider) is found by colour.
    """

    HUD_BOTTOM = 0.91   # scrolling ticker text below this (fraction of height)

    def __init__(self, target_height: int = 300):
        self.target_height = target_height
        self.bgm = BackgroundModel()
        self.bird_x: float | None = None
        self.bird_y: float | None = None
        self.bird_size: list[tuple[float, float]] = []

    def downscale(self, img: np.ndarray) -> np.ndarray:
        step = max(1, int(round(img.shape[0] / self.target_height)))
        return img[::step, ::step, :3].astype(np.int16)

    def analyse(self, img_rgb: np.ndarray) -> Scene:
        f = self.downscale(img_rgb)
        h, w = f.shape[:2]
        u = 1.0 / h
        fg = self.bgm.update(f)
        scene = Scene(width=w * u)
        scene.bird = self._find_bird(f, u)
        play = fg.copy()
        play[int(self.HUD_BOTTOM * h):] = False
        scene.pillars, solid = self._find_pillars(play, u)
        blobs = play & ~solid
        if scene.bird is not None:
            b = scene.bird
            pad = 0.01
            blobs[max(0, int((b.y0 - pad) / u)): int((b.y1 + pad) / u) + 1,
                  max(0, int((b.x0 - pad) / u)): int((b.x1 + pad) / u) + 1] = False
        self._classify_blobs(f, blobs, u, scene)
        return scene

    # ------------------------------------------------------------------
    def _find_bird(self, f, u) -> Box | None:
        h, w = f.shape[:2]
        m = bird_mask(f)
        m[: int(0.15 * h), : int(0.12 * w)] = False   # speaker icon
        m[: int(0.15 * h), int(0.88 * w):] = False    # close button
        lab, n = ndimage.label(m)
        if n == 0:
            return None
        idx = np.arange(1, n + 1)
        areas = ndimage.sum(m, lab, idx)
        coms = ndimage.center_of_mass(m, lab, idx)
        min_area = (0.012 * h) ** 2
        best, best_score = None, -1e9
        for a, (cy, cx) in zip(areas, coms):
            if a < min_area:
                continue
            x, y = cx * u, cy * u
            if self.bird_x is not None:
                if abs(x - self.bird_x) > 0.08:
                    continue
                score = a * u * u * 1e3 - (abs(y - self.bird_y) * 20 if self.bird_y is not None else 0)
            else:
                if not (0.25 * w < cx < 0.75 * w):
                    continue
                score = a * u * u * 1e3
            if score > best_score:
                best, best_score = (cy, cx), score
        if best is None:
            return None
        cy, cx = best
        r = int(0.05 / u)
        y0, y1 = max(0, int(cy) - r), min(h, int(cy) + r)
        x0, x1 = max(0, int(cx) - r), min(w, int(cx) + r)
        ys, xs = np.nonzero(m[y0:y1, x0:x1])
        box = Box((x0 + xs.min()) * u, (x0 + xs.max() + 1) * u, (y0 + ys.min()) * u, (y0 + ys.max() + 1) * u)
        self.bird_x = box.cx if self.bird_x is None else 0.9 * self.bird_x + 0.1 * box.cx
        self.bird_y = box.cy
        self.bird_size.append((box.x1 - box.x0, box.y1 - box.y0))
        self.bird_size = self.bird_size[-60:]
        return box

    def stable_bird_size(self) -> tuple[float, float]:
        if not self.bird_size:
            return 0.045, 0.045
        a = np.array(self.bird_size)
        return float(np.median(a[:, 0])), float(np.median(a[:, 1]))

    # ------------------------------------------------------------------
    def _find_pillars(self, play, u):
        h, w = play.shape
        hb = int(self.HUD_BOTTOM * h)
        solid_mask = np.zeros_like(play)
        col = ndimage.uniform_filter1d(play[:hb].mean(axis=0), 3)
        lab, n = ndimage.label(col > 0.3)
        pillars = []
        win = max(3, int(0.03 * h))
        for sl in ndimage.find_objects(lab):
            x0, x1 = sl[0].start, sl[0].stop
            wid = (x1 - x0) * u
            clipped = x0 == 0 or x1 == w
            if wid > 0.13 or (wid < 0.045 and not clipped) or wid < 0.012:
                continue
            rows = ndimage.uniform_filter1d(play[:, x0:x1].mean(axis=1), win)
            solid = rows > 0.35
            solid[hb:] = True  # ticker area: assume pillar continues
            # top part = run from row 0, bottom part = run ending at the ticker
            top = 0
            while top < hb and solid[top]:
                top += 1
            bot = hb
            while bot > top and solid[bot - 1]:
                bot -= 1
            if top < 0.04 * h and bot > hb - 0.04 * h:
                continue  # not attached to any edge -> not a pillar
            gap = (bot - top) * u
            if gap < 0.1 or gap > 0.8:
                continue
            pillars.append(Pillar(x0 * u, x1 * u, top * u, bot * u))
            solid_mask[:top, max(0, x0 - 2): x1 + 2] = True
            solid_mask[bot:, max(0, x0 - 2): x1 + 2] = True
        return pillars, solid_mask

    # ------------------------------------------------------------------
    def _classify_blobs(self, f, m, u, scene: Scene):
        m = ndimage.binary_closing(m, iterations=2)
        lab, n = ndimage.label(m)
        r, g, b = f[..., 0], f[..., 1], f[..., 2]
        mx = np.maximum(np.maximum(r, g), b)
        mn = np.minimum(np.minimum(r, g), b)
        red = (r > 130) & (g * 2 < r) & (b * 2 < r)
        blue = (b > 120) & (b > r + 45) & (b > g + 25)
        pale = (mn > 165) & (mx - mn < 70)
        colorful = (mx > 90) & ((mx - mn) * 100 > 35 * mx)
        for i, sl in enumerate(ndimage.find_objects(lab), start=1):
            ys, xs = sl
            edge = int(0.06 / u)
            if xs.start <= edge or xs.stop >= m.shape[1] - edge:
                continue  # at the screen edge (pillar slivers); far from the bird anyway
            bw, bh = (xs.stop - xs.start) * u, (ys.stop - ys.start) * u
            if not (0.003 <= bw < 0.14 and 0.02 < bh < 0.14):
                continue
            comp = lab[sl] == i
            k = comp.sum()
            fr = lambda mask: float(mask[sl][comp].sum()) / k  # noqa: E731
            box = Box(xs.start * u, xs.stop * u, ys.start * u, ys.stop * u)
            aspect = bw / bh
            if aspect >= 1.2 and fr(pale) >= 0.03 and fr(colorful) >= 0.25:
                scene.money.append(box)
            elif fr(red) >= 0.2 and aspect < 1.5:
                scene.flags.append(box)
            elif fr(blue) >= 0.3 and 0.6 < aspect < 1.6:
                scene.cubes.append(box)
            elif bw > 0.02 or bh > 0.03:
                # flag over a red background: only its pole "moves", so look
                # at the colour AROUND the blob too
                e = int(0.03 / u)
                ey0, ey1 = max(0, ys.start - e // 2), ys.stop + e // 2
                ex0, ex1 = max(0, xs.start - e // 3), xs.stop + e
                if red[ey0:ey1, ex0:ex1].mean() >= 0.3 and aspect < 1.5:
                    scene.flags.append(Box(ex0 * u, ex1 * u, ey0 * u, ey1 * u))
