"""Local scorer that mirrors the organisers' evo setup: associate by timestamp (max 10 ms),
SE(3) Umeyama alignment (no scale), ATE RMSE. Also reports the blind-5s and post-dropout errors.

    python tools/evaluate.py groundtruth.txt estimated_trajectory.txt [imu0/data.csv]
"""
import sys

import numpy as np


def load_tum(path):
    return np.loadtxt(path, comments="#")


def associate(t_est, t_gt, max_diff=0.01):
    j = np.clip(np.searchsorted(t_gt, t_est), 1, len(t_gt) - 1)
    j = np.where(np.abs(t_gt[j - 1] - t_est) < np.abs(t_gt[j] - t_est), j - 1, j)
    ok = np.abs(t_gt[j] - t_est) < max_diff
    return ok, j


def umeyama(src, dst):
    """R, t minimising |dst - (R src + t)| (no scale)."""
    ms, md = src.mean(0), dst.mean(0)
    C = (dst - md).T @ (src - ms) / len(src)
    U, _, Vt = np.linalg.svd(C)
    S = np.eye(3)
    if np.linalg.det(U) * np.linalg.det(Vt) < 0:
        S[2, 2] = -1
    R = U @ S @ Vt
    return R, md - R @ ms


def score(gt, est, blind_s=5.0):
    ok, j = associate(est[:, 0], gt[:, 0])
    e, g = est[ok], gt[j[ok]]
    R, t = umeyama(e[:, 1:4], g[:, 1:4])
    err = np.linalg.norm((e[:, 1:4] @ R.T + t) - g[:, 1:4], axis=1)
    te = e[:, 0]
    blind = te > est[-1, 0] - blind_s
    dt = np.diff(est[:, 0], prepend=est[0, 0])
    after_gap = np.zeros(len(est), bool)
    for k in np.flatnonzero(dt > 0.05):
        after_gap |= (est[:, 0] >= est[k, 0]) & (est[:, 0] < est[k, 0] + 1.0)
    after_gap = after_gap[ok] & ~blind
    rms = lambda m: float(np.sqrt(np.mean(err[m] ** 2))) if m.any() else float("nan")
    # trivial reference: a single point at the GT mean (what "no motion" would score)
    ref = float(np.sqrt(np.mean(np.sum((g[:, 1:4] - g[:, 1:4].mean(0)) ** 2, axis=1))))
    return {"ate": rms(np.ones(len(err), bool)), "blind": rms(blind), "gap": rms(after_gap),
            "ref_static": ref, "matched": int(ok.sum()), "rows": len(est)}


if __name__ == "__main__":
    gt, est = load_tum(sys.argv[1]), load_tum(sys.argv[2])
    if len(sys.argv) > 3:
        n_in = sum(1 for l in open(sys.argv[3]) if l.strip() and l[0].isdigit())
        print("rows in", n_in, "rows out", len(est), "OK" if n_in == len(est) else "MISMATCH")
    for k, v in score(gt, est).items():
        print(f"{k:>11}: {v:.4f}" if isinstance(v, float) else f"{k:>11}: {v}")
