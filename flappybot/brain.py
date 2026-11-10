"""Physics learning + model-predictive planner.

The bot does not need to know the game's gravity, jump strength, scroll speed
or input lag in advance: it watches the bird and learns them while playing.
Every frame it simulates ~1000 possible tap sequences over the next second
and picks the one that survives, grabs the most money and dodges flags.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass

import numpy as np

from .vision import Box, Pillar, Scene, Vision


@dataclass
class Physics:
    g: float = 2.6        # gravity, units/s^2 (down is +)
    vj: float = -0.75     # velocity right after a flap, units/s
    lag: float = 0.06     # seconds from click to visible effect
    speed: float = 0.45   # scroll speed, units/s
    calibrated: bool = False


class PhysicsLearner:
    def __init__(self):
        self.p = Physics()
        self.samples: deque[tuple[float, float]] = deque(maxlen=400)
        self.taps: deque[float] = deque(maxlen=60)
        self.speeds: deque[float] = deque(maxlen=40)
        self._last_fit = 0.0
        self._hist: deque = deque()

    def add_bird(self, t: float, y: float):
        if self.samples:
            t0, y0 = self.samples[-1]
            # teleport (new round) or long gap -> old trajectory is unrelated
            if abs(y - y0) > 0.12 + 3.0 * (t - t0) or t - t0 > 0.5:
                self.samples.clear()
        self.samples.append((t, y))

    def add_tap(self, t: float):
        self.taps.append(t)

    def add_pillars(self, t: float, pillars: list[Pillar], width: float):
        """Scroll speed: compare pillar edges with a frame ~0.2 s older."""
        edges = []  # (kind, x): kind 0 = left edge, 1 = right edge
        for p in pillars:
            if p.x0 > 0.01:
                edges.append((0, p.x0))
            if p.x1 < width - 0.01:
                edges.append((1, p.x1))
        self._hist.append((t, edges))
        old = None
        for th, eh in self._hist:
            if t - th >= 0.2:
                old = (th, eh)
        if old is not None and edges and old[1]:
            dt = t - old[0]
            for k, e in edges:
                ds = [o - e for ko, o in old[1] if ko == k and 0 < o - e < 0.3]
                if ds:
                    v = min(ds) / dt
                    if 0.02 < v < 2.5:
                        self.speeds.append(v)
            if len(self.speeds) >= 5:
                self.p.speed = float(np.median(self.speeds))
        while self._hist and t - self._hist[0][0] > 0.6:
            self._hist.popleft()

    # -- gravity / flap / lag -------------------------------------------
    def maybe_fit(self, now: float):
        """Fit one *continuous* trajectory through the last few seconds:
        between flaps the bird follows y = y_i + vj*d + g/2*d^2 and position
        is continuous across flaps. For a fixed lag this is linear in
        (y0, vj, g), so we grid-search the lag and solve least squares.
        Continuity makes the lag identifiable (the kink must sit exactly
        where the trajectory bends)."""
        if now - self._last_fit < 0.5 or len(self.taps) < 3 or len(self.samples) < 30:
            return
        self._last_fit = now
        S = np.array(self.samples)
        S = S[S[:, 0] >= now - 4.0]
        ts, ys = S[:, 0], S[:, 1]
        taps = np.array(self.taps)
        best = None
        for lag in np.arange(0.0, 0.25, 0.004):
            eff = taps + lag
            eff = eff[(eff >= ts[0]) & (eff <= ts[-1])]
            if len(eff) < 3:
                continue
            m = ts >= eff[0]
            t, y = ts[m], ys[m]
            if len(t) < 25:
                continue
            k = np.searchsorted(eff, t, side="right") - 1
            d = np.diff(eff)
            c1 = np.concatenate([[0], np.cumsum(d)])
            c2 = np.concatenate([[0], np.cumsum(d * d)])
            r = t - eff[k]
            D1 = c1[k] + r
            D2 = c2[k] + r * r
            A = np.vstack([np.ones_like(t), D1, 0.5 * D2]).T
            coef, *_ = np.linalg.lstsq(A, y, rcond=None)
            err = float(np.mean((A @ coef - y) ** 2))
            if best is None or err < best[0]:
                best = (err, lag, coef[1], coef[2], len(t))
        if best is None:
            return
        err, lag, vj, g, n = best
        if getattr(self, "debug", False):
            print(f"fit t={now:.1f} err={err:.2e} lag={lag:.3f} vj={vj:.2f} g={g:.2f} n={n}")
        if not (0.2 < g < 20 and -5 < vj < -0.05) or err > 3e-5:
            return
        a = 0.3 if self.p.calibrated else 1.0
        self.p.g = (1 - a) * self.p.g + a * g
        self.p.vj = (1 - a) * self.p.vj + a * vj
        self.p.lag = (1 - a) * self.p.lag + a * lag
        self.p.calibrated = True

    def bird_velocity(self, t_now: float) -> float:
        """Current vertical velocity estimate from recent samples."""
        p = self.p
        last_eff = None
        for tp in reversed(self.taps):
            if tp + p.lag <= t_now:
                last_eff = tp + p.lag
                break
        pts = [(t, y) for t, y in list(self.samples)[-8:] if last_eff is None or t >= last_eff]
        if len(pts) >= 3:
            t = np.array([q[0] for q in pts]) - t_now
            y = np.array([q[1] for q in pts]) - 0.5 * p.g * t * t
            A = np.vstack([np.ones_like(t), t]).T
            (a, b), *_ = np.linalg.lstsq(A, y, rcond=None)
            return float(b)
        if last_eff is not None:
            return p.vj + p.g * (t_now - last_eff)
        return 0.0


class Planner:
    """Evaluates thousands of candidate "flight plans" every frame.

    A plan is the policy *hold height h1 until ts1, then h2 until ts2, then
    h3*: flap whenever the bird drops below the held height. That family
    covers hovering, climbing/diving to a gap, slipping under or over a flag
    and swooping through money. Each frame it tests
      * a fixed grid of 2-phase plans,
      * ~1500 random 3-phase plans,
      * variations of last frame's best plan (warm start),
    simulates each with the learned physics and picks the cheapest.
    """

    def __init__(self, horizon: float = 1.7, dt: float = 1 / 30, min_gap: float = 0.1,
                 n_random: int = 1500, seed: int = 0):
        self.dt = dt
        self.T = T = int(horizon / dt)
        self.min_gap = max(1, int(round(min_gap / dt)))
        self.n_random = n_random
        self.terminal_w = 0.0  # tested 5.0: no improvement (flags 14 vs 10 / 12 min)
        self.rng = np.random.default_rng(seed)
        hs = np.linspace(0.06, 0.94, 23)
        # switch times (seconds) -> steps
        ts = np.unique(np.round(np.array([0, .1, .2, .3, .4, .53, .67, .83, 1.03, 1.27]) / dt).astype(int))
        ts = np.append(ts[ts < T], T)
        H1, H2, TS = np.meshgrid(hs, hs, ts, indexing="ij")
        keep = ~((TS == T) & (H2 != H1))  # ts == T makes h2 irrelevant
        keep &= ~((TS == 0) & (H1 != H2))
        H1, H2, TS = H1[keep], H2[keep], TS[keep]
        # base grid as 3-phase plans with ts2 = T; plus "never flap"
        self.base = np.stack([np.append(H1, 2.0), np.append(TS, T), np.append(H2, 2.0),
                              np.full(len(H1) + 1, T), np.append(H2, 2.0)], axis=1).astype(float)
        self.steps = np.arange(T)
        self.base_hold = self._hold(self.base)
        self.prev = None  # (plan row, frame time) of last frame's best plan

    def _hold(self, plans):
        h1, ts1, h2, ts2, h3 = (plans[:, i:i + 1] for i in range(5))
        k = self.steps[None, :]
        return np.where(k < ts1, h1, np.where(k < ts2, h2, h3))

    def _extra_plans(self, t_frame):
        T = self.T
        n = self.n_random
        r = self.rng
        ts1 = r.integers(0, T // 2, n)
        ts2 = ts1 + r.integers(max(1, int(0.1 / self.dt)), T, n)
        rnd = np.stack([r.uniform(0.05, 0.95, n), ts1, r.uniform(0.05, 0.95, n),
                        np.minimum(ts2, T), r.uniform(0.05, 0.95, n)], axis=1)
        out = [rnd]
        if self.prev is not None and t_frame is not None:
            row, t_old = self.prev
            shift = (t_frame - t_old) / self.dt
            w = row.copy()
            w[1] = max(0.0, w[1] - shift)
            w[3] = max(0.0, w[3] - shift)
            m = 200
            var = np.tile(w, (m, 1))
            var[1:, [0, 2, 4]] += r.normal(0, 0.03, (m - 1, 3))
            var[1:, [1, 3]] += np.round(r.normal(0, 0.04 / self.dt, (m - 1, 2)))
            var[:, [1, 3]] = np.clip(var[:, [1, 3]], 0, T)
            var[:, 3] = np.maximum(var[:, 3], var[:, 1])
            out.append(var)
        return np.vstack(out)

    def decide(self, y, vy, phys: Physics, bird_x: tuple[float, float], bird_h: float,
               scene: Scene, pending: list[float], offset: float,
               money_w=1.0, flag_w=10.0, cube_w=2.0, t_frame: float | None = None,
               frame_dt: float = 1 / 60) -> tuple[bool, dict]:
        """Return (tap_now, debug). ``pending`` = times (relative to the frame)
        at which already-sent taps take effect. ``offset`` = time between the
        frame capture and now. Taps in the simulation are placed at the time
        they take effect; a tap sent now lands at ``shift``."""
        dt, T = self.dt, self.T
        extra = self._extra_plans(t_frame)
        plans = np.vstack([self.base, extra])
        hold = np.vstack([self.base_hold, self._hold(extra)])
        P = len(plans)
        shift = max(0, int(round((offset + phys.lag) / dt)))
        forced = np.zeros(T, bool)
        for pt in pending:
            k = int(round(pt / dt))
            if 0 <= k < T:
                forced[k] = True
        Y = np.empty((P, T), np.float32)
        yy = np.full(P, float(y), np.float32)
        vv = np.full(P, float(vy), np.float32)
        since = np.full(P, 10**6 if not pending else 0)
        tap_at_shift = np.zeros(P, bool)
        g, vj = phys.g, phys.vj
        # the bot can only click when a new frame arrives -> flaps are only
        # possible every `every` steps (aligned with the next click at `shift`)
        every = max(1, int(round(frame_dt / dt)))
        for k in range(T):
            if k >= shift and (k - shift) % every == 0:
                # flap if we are (about to be) below the held height and falling
                want = (yy > hold[:, k]) & (vv > -0.2 * abs(vj)) & (since >= self.min_gap)
                if forced[k]:
                    want = np.ones(P, bool)
            else:
                want = np.full(P, bool(forced[k]))
            if k == shift:
                tap_at_shift = want & ~forced[k]
            vv = np.where(want, vj, vv)
            since = np.where(want, 0, since + 1)
            yy = yy + vv * dt + 0.5 * g * dt * dt
            vv = vv + g * dt
            Y[:, k] = yy
        t = (np.arange(T) + 1) * dt
        hh = bird_h / 2
        bx0, bx1 = bird_x
        cost = np.zeros(P)
        dead_at = np.full(P, T)
        out = (Y + hh > 0.995) | (Y - hh < 0.0)
        dead_at = np.minimum(dead_at, np.where(out.any(1), out.argmax(1), T))
        target = np.full(T, 0.5)
        margin = 0.022
        for pl in sorted(scene.pillars, key=lambda p: -p.x0):
            x0 = pl.x0 - phys.speed * t
            x1 = pl.x1 - phys.speed * t
            over = (x1 > bx0 - 0.005) & (x0 < bx1 + 0.005)
            near = (x1 > bx0 - 0.02) & (x0 < bx1 + 0.3)
            target = np.where(near, (pl.gap_top + pl.gap_bot) / 2, target)
            if not over.any():
                continue
            hit = over & ((Y - hh < pl.gap_top + margin) | (Y + hh > pl.gap_bot - margin))
            dead_at = np.minimum(dead_at, np.where(hit.any(1), hit.argmax(1), T))
            d = np.minimum(Y - hh - pl.gap_top, pl.gap_bot - Y - hh)
            cost += 150.0 * (np.clip(0.06 - d, 0, None) ** 2 * over).sum(1) * dt
        for items, w in ((scene.money, -money_w), (scene.cubes, -cube_w)):
            for bx in items:
                pad = -0.004
                x0 = bx.x0 - phys.speed * t - pad
                x1 = bx.x1 - phys.speed * t + pad
                over = (x1 > bx0) & (x0 < bx1)
                if not over.any():
                    continue
                touch = over & (Y + hh > bx.y0 - pad) & (Y - hh < bx.y1 + pad)
                when = np.where(touch.any(1), touch.argmax(1), T)
                hit = when < dead_at
                cost += w * hit * (1.0 - 0.3 * when / T)
        # flags: graded cost. Real overlap = full penalty; merely passing
        # close (inside the safety zone) = small penalty that grows as the
        # gap shrinks. So near-misses are preferred over plowing through.
        fh = hh + 0.004   # sprite outline is a bit bigger than the neon fill
        zone = 0.03
        for bx in scene.flags:
            x0 = bx.x0 - phys.speed * t - 0.008
            x1 = bx.x1 - phys.speed * t + 0.008
            over = (x1 > bx0) & (x0 < bx1)
            if not over.any():
                continue
            clear = np.maximum(bx.y0 - (Y + fh), (Y - fh) - bx.y1)  # >0 = clear of it
            clear = np.where(over[None, :], clear, 1.0)
            cmin = clear.min(1)
            first = np.where((clear < 0).any(1), (clear < 0).argmax(1), T)
            hit = first < dead_at
            near = np.clip(1.0 - cmin / zone, 0.0, 1.0)
            cost += flag_w * np.where(hit, 1.0 - 0.3 * first / T, 0.25 * near)
        cost += 0.3 * np.mean((Y - target) ** 2, axis=1)
        # keep options open for what is not on screen yet: end the plan near
        # the next known gap centre (or the screen middle)
        cost += self.terminal_w * (Y[:, -1] - target[-1]) ** 2
        dead = dead_at < T
        cost += dead * (100.0 + 100.0 * (T - dead_at) / T)
        best = int(np.argmin(cost))
        self._last = (Y, dead_at, cost)
        if t_frame is not None:
            self.prev = (plans[best].copy(), t_frame)
        return bool(tap_at_shift[best]), {"cost": float(cost[best]), "dead": bool(dead[best]),
                                          "hold": float(hold[best, min(shift, T - 1)])}


class Bot:
    """Glue: feed it frames, it tells you when to click."""

    def __init__(self, min_tap_interval: float = 0.09, money_weight=1.0, flag_weight=10.0, cube_weight=2.0):
        self.vision = Vision()
        self.learn = PhysicsLearner()
        self.planner = Planner()
        self.min_tap_interval = min_tap_interval
        self.money_weight = money_weight
        self.flag_weight = flag_weight
        self.cube_weight = cube_weight
        self.last_tap = -1e9
        self.last_seen = None
        self._last_frame = None
        self._frame_dts: deque = deque(maxlen=30)
        self.scene: Scene | None = None
        self.debug: dict = {}

    def step(self, img_rgb: np.ndarray, t_frame: float, t_now: float) -> bool:
        scene = self.vision.analyse(img_rgb)
        self.scene = scene
        if self._last_frame is not None and 0 < t_frame - self._last_frame < 0.5:
            self._frame_dts.append(t_frame - self._last_frame)
        self._last_frame = t_frame
        self.learn.add_pillars(t_frame, scene.pillars, scene.width)
        if scene.bird is None:
            return False
        self.last_seen = t_frame
        self.learn.add_bird(t_frame, scene.bird.cy)
        self.learn.maybe_fit(t_now)
        p = self.learn.p
        vy = self.learn.bird_velocity(t_frame)
        bw, bh = self.vision.stable_bird_size()
        bx = self.vision.bird_x
        pending = [tp + p.lag - t_frame for tp in self.learn.taps if tp + p.lag > t_frame]
        tap, dbg = self.planner.decide(
            scene.bird.cy, vy, p, (bx - bw / 2, bx + bw / 2), bh, scene, pending,
            offset=t_now - t_frame, money_w=self.money_weight, flag_w=self.flag_weight,
            cube_w=self.cube_weight, t_frame=t_frame,
            frame_dt=float(np.median(self._frame_dts)) if self._frame_dts else 1 / 30)
        self.debug = dbg | {"vy": vy}
        if tap and t_now - self.last_tap >= self.min_tap_interval:
            self.last_tap = t_now
            self.learn.add_tap(t_now)
            return True
        return False
