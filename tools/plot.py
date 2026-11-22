"""Figures + ablation table for README/slides.  python tools/plot.py  -> results/*.png, results/results.md"""
import glob
import io
import contextlib
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "submission", "src"))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import main  # noqa: E402
from evaluate import load_tum, score, associate, umeyama  # noqa: E402

OUT = os.path.join(ROOT, "results")
os.makedirs(OUT, exist_ok=True)

VARIANTS = {
    "Naive double integration": dict(main.P, hp_vel=1e6, hp_pos=1e6, blind_keep=1.0, tau_v=1.0, spike_k=1e9),
    "+ zero-phase high-pass": dict(main.P, blind_keep=1.0, tau_v=1.0, spike_k=1e9),
    "+ cleaning + blind relax (ours)": dict(main.P),
}


def run(seq, p):
    ts, x = main.read_imu(os.path.join(ROOT, "data_test", seq, "mav0", "imu0", "data.csv"))
    pos, q = main.estimate(ts, x, p)
    return np.column_stack([ts * 1e-9, pos, q[:, 1:], q[:, :1]])


seqs = sorted(os.path.basename(d) for d in glob.glob(os.path.join(ROOT, "data_test", "*_[AB]")))
table = {}
for name, p in VARIANTS.items():
    rows = [score(load_tum(os.path.join(ROOT, "data_raw", s[:-2], "groundtruth.txt")), run(s, p)) for s in seqs]
    table[name] = rows
ref = [r["ref_static"] for r in table[next(iter(table))]]

with open(os.path.join(OUT, "results.md"), "w") as f:
    f.write("| Method | ATE RMSE [m] | Blind 5 s [m] | After dropouts [m] |\n|---|---|---|---|\n")
    f.write(f"| Static point (no motion) | {np.mean(ref):.2f} | - | - |\n")
    for name, rows in table.items():
        m = {k: np.mean([r[k] for r in rows]) for k in ("ate", "blind", "gap")}
        f.write(f"| {name} | {m['ate']:.2f} | {m['blind']:.2f} | {m['gap']:.2f} |\n")
    f.write("\nPer sequence (ours):\n\n| Sequence | ATE [m] | Blind [m] | Static ref [m] |\n|---|---|---|---|\n")
    for s, r in zip(seqs, table["+ cleaning + blind relax (ours)"]):
        f.write(f"| {s} | {r['ate']:.3f} | {r['blind']:.3f} | {r['ref_static']:.3f} |\n")
print(open(os.path.join(OUT, "results.md")).read())

# trajectory + error figure for one sequence
seq = "room2_A"
gt = load_tum(os.path.join(ROOT, "data_raw", seq[:-2], "groundtruth.txt"))
fig, ax = plt.subplots(1, 2, figsize=(13, 5.2))
for name, p, c in [("Ours", main.P, "#1f6feb")]:
    est = run(seq, p)
    ok, j = associate(est[:, 0], gt[:, 0])
    R, t = umeyama(est[ok, 1:4], gt[j[ok], 1:4])
    e = est[ok, 1:4] @ R.T + t
    err = np.linalg.norm(e - gt[j[ok], 1:4], axis=1)
    blind = est[ok, 0] > est[-1, 0] - 5
    ax[0].plot(e[~blind, 0], e[~blind, 1], c=c, lw=0.8, label=name)
    ax[0].plot(e[blind, 0], e[blind, 1], c=c, lw=2.5, ls=":")
    ax[1].plot(est[ok, 0] - est[0, 0], err, c=c, lw=0.8, label=f"{name} (ATE {np.sqrt(np.mean(err**2)):.2f} m)")
g = gt[j[ok], 1:4]
ax[0].plot(g[:, 0], g[:, 1], c="k", lw=0.8, alpha=0.6, label="Ground truth")
ax[0].set_title(f"Top view, TUM-VI {seq[:-2]} degraded (dotted = blind 5 s)")
ax[0].set_xlabel("x [m]"); ax[0].set_ylabel("y [m]"); ax[0].axis("equal"); ax[0].legend()
T = est[-1, 0] - est[0, 0]
ax[1].axvspan(T - 5, T, color="r", alpha=0.12, label="IMU failure (blind)")
ax[1].set_title("Position error over time (degradation grows with time)")
ax[1].set_xlabel("time [s]"); ax[1].set_ylabel("error [m]"); ax[1].legend()
fig.tight_layout()
fig.savefig(os.path.join(OUT, "trajectory.png"), dpi=130)

# ablation bar chart
fig, ax = plt.subplots(figsize=(7, 4))
names = ["Static point"] + list(table)
vals = [np.mean(ref)] + [np.mean([r["ate"] for r in rows]) for rows in table.values()]
bars = ax.bar(range(len(vals)), vals, color=["#8b949e", "#d1242f", "#d29922", "#1f6feb"])
ax.set_yscale("log")
ax.set_xticks(range(len(vals)), [n.replace(" (ours)", "\n(ours)").replace("+ ", "+ ") for n in names], fontsize=8)
for b, v in zip(bars, vals):
    ax.text(b.get_x() + b.get_width() / 2, v * 1.08, f"{v:.2f} m", ha="center", fontsize=9)
ax.set_ylabel("mean ATE RMSE [m] (log)")
ax.set_title("12 degraded TUM-VI runs (rooms 1-6, both column orders)")
fig.tight_layout()
fig.savefig(os.path.join(OUT, "ablation.png"), dpi=130)
print("figures ->", OUT)
