#!/usr/bin/env python3
"""Path Finder - 6-DoF trajectory from a degraded IMU CSV (Samsung PRISM XR Hackathon 2026, Track 3).

Usage
    python main.py <imu0/data.csv | dataset.zip | dataset_folder> [estimated_trajectory.txt]

Input   EuRoC IMU CSV: timestamp[ns], gyro xyz [rad/s], accel xyz [m/s^2]
        (the gyro/accel column groups are auto-detected, so swapped files also work).
Output  TUM poses, exactly one per input row: timestamp[s] tx ty tz qx qy qz qw

Pipeline
    1. load      numpy C parser; detect accel columns (|a| ~ g), units, and the blind tail
                 (trailing rows that are all zero / NaN = IMU failure)
    2. clean     spikes (neighbour test, robust sigma) and stuck runs (repeated rows) -> interpolated;
                 dropouts are kept as real time gaps and integrated over their true dt
    3. attitude  gyro quaternion integration, initial tilt from gravity
    4. position  rotate accel to world, remove gravity, integrate twice with zero-phase (offline,
                 non-causal) high-pass filtering of velocity and position: bias, tilt and scale errors
                 are slow, so removing the slow part kills the quadratic drift while keeping motion
    5. blind 5 s dead reckoning from the last state: angular rate and velocity decay, position
                 relaxes to the long-term mean (the safest guess once the sensor is gone)
    6. write     chunked TUM output, timestamps converted ns -> s exactly
"""
import io
import os
import sys
import zipfile

import numpy as np

G = 9.80665

# Tuned on degraded TUM-VI room1-6, both column orders (tools/tune.py).
P = {
    "spike_k": 8.0,     # spike threshold in robust sigmas
    "hp_vel": 5.0,      # velocity high-pass window [s]
    "hp_pos": 8.0,      # position high-pass window [s]
    "hp_passes": 2,     # moving-average passes per high-pass (2 = triangular kernel)
    "tau_v": 0.05,      # blind: velocity decay time constant [s]
    "tau_w": 0.3,       # blind: angular-rate decay time constant [s]
    "blind_keep": 0.0,  # blind: fraction of the last position offset kept (0 = relax to mean)
}
CHUNK = 1024


# ----------------------------------------------------------------------------- load
def open_input(path):
    """Text stream for imu0/data.csv given the csv itself, a dataset folder or a zip."""
    if os.path.isdir(path):
        for root, _, files in os.walk(path):
            if os.path.basename(root) == "imu0" and "data.csv" in files:
                return open(os.path.join(root, "data.csv"), "r", encoding="utf-8-sig")
        sys.exit(f"no imu0/data.csv under {path}")
    if zipfile.is_zipfile(path):
        z = zipfile.ZipFile(path)
        names = [n for n in z.namelist() if n.endswith("imu0/data.csv")] or \
                [n for n in z.namelist() if n.endswith(".csv")]
        if not names:
            sys.exit(f"no csv inside {path}")
        return io.TextIOWrapper(z.open(names[0]), encoding="utf-8-sig")
    return open(path, "r", encoding="utf-8-sig")


def read_imu(path):
    """int64 ns timestamps and an (n,6) float array. Header/comment lines and either delimiter are fine."""
    skip, line = 0, ""
    with open_input(path) as f:
        for line in f:
            s = line.strip()
            if s and s[0] != "#" and (s[0].isdigit() or s[0] in "-+."):
                break
            skip += 1
    delim = "," if "," in line else None
    kw = dict(delimiter=delim, comments="#", skiprows=skip, ndmin=1)
    with open_input(path) as f:
        x = np.loadtxt(f, usecols=range(1, 7), dtype=np.float32, **kw)   # 6-decimal input: f32 is exact enough
    try:
        with open_input(path) as f:
            ts = np.loadtxt(f, usecols=0, dtype=np.int64, **kw)       # EuRoC: integer ns
    except ValueError:
        with open_input(path) as f:
            tf = np.loadtxt(f, usecols=0, **kw)                       # float timestamps
        ts = (np.round(tf * 1e9) if tf[0] < 1e12 else tf).astype(np.int64)
    if len(ts) < 2 or x.ndim != 2:
        sys.exit("input needs at least 2 IMU rows with 7 columns")
    return ts, x


def split_columns(t, x, bad):
    """(gyro, accel) views into x: accel is the triple whose median norm in the first 2 s looks like gravity."""
    win = ~bad & (t < 2.0)
    if win.sum() < 20:
        win = ~bad
    m = [float(np.median(np.linalg.norm(x[win, s], axis=1))) for s in (slice(0, 3), slice(3, 6))]
    e = [min(abs(v - G), abs(v - 1.0)) for v in m]
    first_is_acc = e[0] < e[1] and e[0] < 2.0     # otherwise EuRoC order, as slide 15 specifies
    ga, aa = (slice(3, 6), slice(0, 3)) if first_is_acc else (slice(0, 3), slice(3, 6))
    gyro, acc = x[:, ga], x[:, aa]
    ma = m[0] if first_is_acc else m[1]
    if abs(ma - 1.0) < abs(ma - G):                # accel given in g
        acc *= G
    return gyro, acc


# ----------------------------------------------------------------------------- clean
def mark_spikes(v, k):
    """Single-sample outliers: far from the mean of both neighbours (robust per-axis scale)."""
    d = np.zeros_like(v)
    d[1:-1] = v[1:-1] - 0.5 * (v[:-2] + v[2:])
    s = 1.4826 * np.median(np.abs(d[1:-1]), axis=0) + 1e-9
    return (np.abs(d) > k * s).any(axis=1)


def fill_bad(t, v, bad):
    """Linear interpolation over flagged samples, per axis (in place)."""
    if bad.any() and (~bad).sum() >= 2:
        for j in range(v.shape[1]):
            v[bad, j] = np.interp(t[bad], t[~bad], v[~bad, j])


def clean(t, gyro, acc, valid, k):
    stuck = np.zeros(len(t), bool)
    stuck[1:] = (gyro[1:] == gyro[:-1]).all(1) & (acc[1:] == acc[:-1]).all(1) & (t[1:] > t[:-1])
    bad = stuck | mark_spikes(gyro, k) | mark_spikes(acc, k) | ~valid
    fill_bad(t, gyro, bad)
    fill_bad(t, acc, bad)


# ----------------------------------------------------------------------------- attitude
def quat_from_two(u, v):
    """Unit quaternion (w,x,y,z) rotating unit vector u onto v."""
    c = np.cross(u, v)
    w = 1.0 + float(np.dot(u, v))
    if w < 1e-8:
        return np.array([0.0, 1.0, 0.0, 0.0])
    q = np.array([w, c[0], c[1], c[2]])
    return q / np.linalg.norm(q)


def integrate_gyro(t, gyro, q0, q):
    """q[i] = q[i-1] * Exp((w[i-1]+w[i])/2 * dt), body->world (w,x,y,z). Chunked to bound memory."""
    qw, qx, qy, qz = q0
    q[0] = q0
    n = len(t)
    for a in range(1, n, CHUNK):
        b = min(n, a + CHUNK)
        T = t[a - 1:b].tolist()
        W = gyro[a - 1:b].tolist()
        out = []
        for i in range(1, b - a + 1):
            h = 0.5 * (T[i] - T[i - 1])
            w0, w1 = W[i - 1], W[i]
            dx = 0.5 * (w0[0] + w1[0]) * h
            dy = 0.5 * (w0[1] + w1[1]) * h
            dz = 0.5 * (w0[2] + w1[2]) * h
            a2 = dx * dx + dy * dy + dz * dz
            if a2 > 1e-14:
                an = a2 ** 0.5
                s = np.sin(an) / an
                dw = np.cos(an)
                dx *= s; dy *= s; dz *= s
            else:
                dw = 1.0
            qw, qx, qy, qz = (qw * dw - qx * dx - qy * dy - qz * dz,
                              qw * dx + qx * dw + qy * dz - qz * dy,
                              qw * dy - qx * dz + qy * dw + qz * dx,
                              qw * dz + qx * dy - qy * dx + qz * dw)
            nq = (qw * qw + qx * qx + qy * qy + qz * qz) ** 0.5
            qw /= nq; qx /= nq; qy /= nq; qz /= nq
            out.append((qw, qx, qy, qz))
        q[a:b] = out


def rotate(q, v):
    """Rotate vectors v (n,3) by quaternions q (n,4) (w,x,y,z). Chunked to bound temporaries."""
    out = np.empty((len(q), 3))
    for a in range(0, len(q), CHUNK):
        s = slice(a, a + CHUNK)
        u = q[s, 1:]
        t = 2.0 * np.cross(u, v[s])
        out[s] = v[s] + q[s, :1] * t + np.cross(u, t)
    return out


# ----------------------------------------------------------------------------- filters
def moving_mean(t, v, win, passes=1, out=None):
    """Centered time-window mean applied `passes` times (edges use the samples available).
    Cumulative-sum form, chunked gathers: extra memory ~ one copy of v."""
    n = len(v)
    lo = np.searchsorted(t, t - 0.5 * win, side="left").astype(np.int32)
    hi = np.searchsorted(t, t + 0.5 * win, side="right").astype(np.int32)
    c = np.zeros((n + 1, v.shape[1]))
    out = np.array(v, dtype=np.float64) if out is None else out
    for _ in range(passes):
        np.cumsum(out, axis=0, out=c[1:])
        for a in range(0, n, CHUNK):
            s = slice(a, a + CHUNK)
            out[s] = (c[hi[s]] - c[lo[s]]) / (hi[s] - lo[s])[:, None]
    return out


def high_pass(t, v, win, passes):
    """v - lowpass(v), in place."""
    v -= moving_mean(t, v, win, passes)
    return v


def cumtrapz(t, f, out=None):
    """Cumulative trapezoid integral of f (n,3) over t, chunked; out may be f itself (in place)."""
    n = len(f)
    out = np.empty((n, f.shape[1])) if out is None else out
    prev = np.array(f[0], dtype=np.float64)
    out[0] = 0.0
    for a in range(1, n, CHUNK):
        b = min(n, a + CHUNK)
        seg = np.vstack([prev[None], f[a:b]])
        prev = seg[-1].copy()
        np.cumsum(0.5 * (seg[1:] + seg[:-1]) * (t[a:b] - t[a - 1:b - 1])[:, None], axis=0, out=out[a:b])
        out[a:b] += out[a - 1]
    return out


# ----------------------------------------------------------------------------- estimate
def estimate(ts, x, p=P):
    """Returns (pos (n,3), quat (n,4) w,x,y,z) - one pose per input row."""
    t = (ts - ts[0]).astype(np.float64) * 1e-9
    n = len(t)
    bad = ~np.isfinite(x).all(axis=1) | (x == 0.0).all(axis=1)   # unusable rows
    gyro, acc = split_columns(t, x, bad)
    end = n                                                       # blind tail = trailing bad rows
    while end > 1 and bad[end - 1]:
        end -= 1
    te = t[:end]
    clean(te, gyro[:end], acc[:end], ~bad[:end], p["spike_k"])

    first = te < 2.0
    g_mag = float(np.median(np.linalg.norm(acc[:end][first], axis=1))) if first.sum() > 10 else G
    a0 = acc[: max(5, int(np.searchsorted(t, 0.5)))].mean(0)
    q = np.empty((n, 4), dtype=np.float32)               # state is integrated in float64 scalars
    integrate_gyro(te, gyro[:end], quat_from_two(a0 / np.linalg.norm(a0), np.array([0.0, 0.0, 1.0])), q)

    a_w = rotate(q[:end], acc[:end])
    del acc
    a_w[:, 2] -= g_mag
    v = high_pass(te, cumtrapz(te, a_w, out=a_w), p["hp_vel"], p["hp_passes"])   # a_w buffer -> velocity
    del a_w
    pos = np.empty((n, 3))
    high_pass(te, cumtrapz(te, v, out=pos[:end]), p["hp_pos"], p["hp_passes"])
    del v
    if end < n:
        dead_reckon(t, gyro, q, pos, end, p)
    return pos, q


def dead_reckon(t, gyro, q, pos, end, p):
    """Blind tail: last angular rate and velocity, exponentially decayed; position relaxes to the mean."""
    t0 = t[end - 1]
    k = min(end - 1, int(np.searchsorted(t, t0 - 0.5)))
    w = gyro[k:end].mean(0)
    vel = (pos[end - 1] - pos[k]) / max(t0 - t[k], 1e-3)
    s = (t[end:] - t0)[:, None]
    pos[end:] = p["blind_keep"] * pos[end - 1] + vel * p["tau_v"] * (1.0 - np.exp(-s / p["tau_v"]))
    ang = w * p["tau_w"] * (1.0 - np.exp(-s / p["tau_w"]))      # rotation vector since t0 (body)
    a = np.linalg.norm(ang, axis=1, keepdims=True)
    d = np.hstack([np.cos(0.5 * a), ang * np.where(a > 1e-12, np.sin(0.5 * a) / np.maximum(a, 1e-12), 0.5)])
    qw, qx, qy, qz = q[end - 1]
    dw, dx, dy, dz = d.T
    q[end:] = np.column_stack([qw * dw - qx * dx - qy * dy - qz * dz,
                               qw * dx + qx * dw + qy * dz - qz * dy,
                               qw * dy - qx * dz + qy * dw + qz * dx,
                               qw * dz + qx * dy - qy * dx + qz * dw])


# ----------------------------------------------------------------------------- output
def write_tum(path, ts, pos, q):
    """TUM format, chunked; timestamp printed exactly from integer ns."""
    with open(path, "w", newline="\n") as f:
        f.write("# timestamp tx ty tz qx qy qz qw\n")
        for a in range(0, len(ts), CHUNK):
            b = min(a + CHUNK, len(ts))
            lines = []
            for tn, (x, y, z), (qw, qx, qy, qz) in zip(ts[a:b].tolist(), pos[a:b].tolist(), q[a:b].tolist()):
                s, ns = divmod(tn, 1_000_000_000)
                lines.append(f"{s}.{ns:09d} {x:.6f} {y:.6f} {z:.6f} {qx:.9f} {qy:.9f} {qz:.9f} {qw:.9f}\n")
            f.write("".join(lines))


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    out = sys.argv[2] if len(sys.argv) > 2 else "estimated_trajectory.txt"
    ts, x = read_imu(sys.argv[1])
    pos, q = estimate(ts, x)
    del x
    q /= np.linalg.norm(q, axis=1, keepdims=True)
    q[q[:, 0] < 0] *= -1.0                                       # canonical sign (qw >= 0)
    write_tum(out, ts, pos, q)
    print(f"{len(ts)} poses -> {out}")


if __name__ == "__main__":
    main()
