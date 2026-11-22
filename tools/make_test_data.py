"""Make degraded test sets with the organisers' degrade_imu.py (unmodified).
A = file fed as-is (EuRoC order: gyro first; the script then treats gyro as accel when adding noise)
B = columns swapped to accel-first before degrading, swapped back after (noise lands on the right sensor)
Both outputs are in EuRoC column order, like the evaluation file."""
import os, subprocess, sys
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEG = os.path.join(ROOT, "degrade_imu.py")


def run(src, dst, extra):
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    subprocess.run([sys.executable, DEG, src, dst, "--meta", dst + ".meta.json", *extra], check=True,
                   stdout=subprocess.DEVNULL)


def main(raw_dir, out_dir, seqs, extra=()):
    for s in seqs:
        src = os.path.join(raw_dir, s, "mav0", "imu0", "data.csv")
        run(src, os.path.join(out_dir, s + "_A", "mav0", "imu0", "data.csv"), extra)
        df = pd.read_csv(src)
        cols = list(df.columns)
        swapped = os.path.join(out_dir, s + "_B", "tmp_swapped.csv")
        os.makedirs(os.path.dirname(swapped), exist_ok=True)
        df[[cols[0]] + cols[4:7] + cols[1:4]].to_csv(swapped, index=False)
        dst = os.path.join(out_dir, s + "_B", "mav0", "imu0", "data.csv")
        run(swapped, dst, extra)
        d2 = pd.read_csv(dst)
        c2 = list(d2.columns)
        d2[[c2[0]] + c2[4:7] + c2[1:4]].to_csv(dst, index=False)
        os.remove(swapped)
        print(s, "done")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3:])
