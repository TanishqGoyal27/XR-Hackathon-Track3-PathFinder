"""Run main.estimate on every degraded test set and print the local scores.

    python tools/tune.py [key=value ...]     # override main.P entries for experiments
"""
import glob
import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "submission", "src"))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import main  # noqa: E402
from evaluate import load_tum, score  # noqa: E402


def run(p, verbose=True):
    rows = []
    for d in sorted(glob.glob(os.path.join(ROOT, "data_test", "*_[AB]"))):
        name = os.path.basename(d)
        gt = load_tum(os.path.join(ROOT, "data_raw", name[:-2], "groundtruth.txt"))
        ts, x = main.read_imu(os.path.join(d, "mav0", "imu0", "data.csv"))
        pos, q = main.estimate(ts, x, p)
        est = np.column_stack([ts * 1e-9, pos, q[:, 1:], q[:, :1]])
        s = score(gt, est)
        rows.append(s)
        if verbose:
            print(f"{name:9s} ate={s['ate']:.3f} blind={s['blind']:.3f} gap={s['gap']:.3f} "
                  f"static_ref={s['ref_static']:.3f}")
    m = {k: float(np.mean([r[k] for r in rows])) for k in ("ate", "blind", "gap", "ref_static")}
    print("MEAN      " + " ".join(f"{k}={v:.3f}" for k, v in m.items()))
    return m


if __name__ == "__main__":
    p = dict(main.P)
    for a in sys.argv[1:]:
        k, v = a.split("=")
        p[k] = type(p[k])(float(v)) if not isinstance(p[k], int) else int(float(v))
    run(p)
