"""pytest: vision accuracy + full games against the simulator."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flappybot.vision import Vision  # noqa: E402
from tests.run_sim import run  # noqa: E402
from tests.simulator import Sim  # noqa: E402


def test_vision_finds_bird_and_pillars():
    from flappybot.brain import Bot

    sim = Sim(seed=3)
    bot = Bot()
    for _ in range(150):
        frame = sim.render()
        if bot.step(frame, sim.t, sim.t + 0.015):
            sim.click(sim.t + 0.015)
        sim.step(1 / 30)
    scene = bot.vision.analyse(sim.render())
    assert scene.bird is not None
    assert abs(scene.bird.cy - sim.y) < 0.02
    truth = [o for o in sim.objects if o["k"] == "pillar" and 0.02 < o["x"] < 1.2]
    assert truth
    for o in truth:
        match = [p for p in scene.pillars if abs(p.x0 - o["x"]) < 0.02]
        assert match, f"pillar at {o['x']:.2f} not found"
        assert abs(match[0].gap_top - o["top"]) < 0.02
        assert abs(match[0].gap_bot - o["bot"]) < 0.02


def test_red_background_is_not_a_flag():
    # the sim background has big orange-red stripes, same colour as flags
    sim = Sim(seed=4, flag_rate=0.0)
    v = Vision()
    false_flags = 0
    for _ in range(120):
        sim.step(1 / 30)
        scene = v.analyse(sim.render())
        false_flags += len(scene.flags)
    assert false_flags <= 3


def test_plays_well():
    # rainbow colours on, no shields (so every mistake counts)
    r = run(seconds=60, seed=11, cube_rate=0.0)
    print({k: v for k, v in r.items() if k != "log"})
    assert r["deaths"] <= 1
    assert r["money"] >= 25
    assert r["flags"] <= 3
    assert abs(r["g"] - 2.3) < 0.15 and abs(r["vj"] + 0.7) < 0.06


def test_detects_rainbow_items_and_shield():
    sim = Sim(seed=5)
    v = Vision()
    seen = {"money": 0, "flag": 0, "cube": 0}
    total = dict(seen)
    for _ in range(600):
        sim.step(1 / 30)
        scene = v.analyse(sim.render())
        if sim.t < 2:
            continue
        for kind, found in (("money", scene.money), ("flag", scene.flags), ("cube", scene.cubes)):
            for o in sim.objects:
                if o["k"] == kind and 0.7 < o["x"] < 1.15:
                    total[kind] += 1
                    seen[kind] += any(abs(b.cy - o["y"]) < 0.04 and b.x0 - 0.08 < o["x"] < b.x1 + 0.02
                                      for b in found)
    print(seen, total)
    for k in seen:
        if total[k]:
            assert seen[k] / total[k] > 0.9, k
