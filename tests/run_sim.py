"""Run the bot against the simulator and print a score report.

    python -m tests.run_sim --seconds 120 --save-frames
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flappybot.brain import Bot  # noqa: E402
from tests.simulator import Sim  # noqa: E402


def run(seconds=60.0, seed=0, fps=30, proc=0.015, verbose=False, save=None, **simkw):
    simkw.setdefault('cube_rate', float(os.environ.get('CUBE_RATE', 0.15)))
    sim = Sim(seed=seed, **simkw)
    bot = Bot()
    dt = 1 / 120
    frame_every = int(round(1 / fps / dt))
    step = 0
    while sim.t < seconds:
        if step % frame_every == 0:
            frame = sim.render()
            t_frame = sim.t
            if bot.step(frame, t_frame, t_frame + proc):
                sim.click(t_frame + proc)
            if save and step % (frame_every * 15) == 0:
                from PIL import Image
                Image.fromarray(frame).save(os.path.join(save, f"f{step:06d}.png"))
        if sim.step(dt) and verbose:
            print(f"  died at t={sim.t:.1f}  phys={bot.learn.p}")
        step += 1
    p = bot.learn.p
    lives = sim.lives + [sim.life_money]
    return {"deaths": sim.deaths, "money": sim.money, "flags": sim.flags, "best_life": max(lives), "cubes": sim.cubes, "saves": sim.saves, "log": sim.log,
            "g": round(p.g, 2), "vj": round(p.vj, 2), "lag": round(p.lag, 3), "speed": round(p.speed, 3)}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--seconds", type=float, default=60)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--save-frames")
    a = ap.parse_args()
    if a.save_frames:
        os.makedirs(a.save_frames, exist_ok=True)
    print(run(a.seconds, a.seed, verbose=True, save=a.save_frames))
