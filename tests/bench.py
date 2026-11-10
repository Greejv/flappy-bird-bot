"""Parallel benchmark: python -m tests.bench --seconds 120 --seeds 1-6"""
import argparse
import os
import sys
from concurrent.futures import ProcessPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tests.run_sim import run  # noqa: E402


def one(args):
    seed, secs = args
    return seed, run(secs, seed)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--seconds", type=float, default=120)
    ap.add_argument("--seeds", default="1-6")
    a = ap.parse_args()
    lo, hi = map(int, a.seeds.split("-"))
    tot = {"deaths": 0, "money": 0, "flags": 0}
    with ProcessPoolExecutor(max_workers=hi - lo + 1) as ex:
        for seed, r in ex.map(one, [(s, a.seconds) for s in range(lo, hi + 1)]):
            print(seed, r, flush=True)
            for k in tot:
                tot[k] += r[k]
    print("TOTAL", tot, f"per-minute money={tot['money'] / ((hi - lo + 1) * a.seconds / 60):.1f}")
