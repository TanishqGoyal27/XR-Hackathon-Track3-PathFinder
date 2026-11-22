"""Pull only dso/imu.txt + dso/gt_imu.csv out of a TUM-VI room tarball using HTTP range requests,
and write them as EuRoC-format imu0/data.csv + groundtruth (TUM format) for local testing."""
import re, sys, urllib.request, os

URL = "https://cdn2.vision.in.tum.de/tumvi/exported/euroc/512_16/dataset-{}_512_16.tar"


def rng(url, a, b):
    req = urllib.request.Request(url, headers={"Range": f"bytes={a}-{b}"})
    return urllib.request.urlopen(req, timeout=300).read()


def members(buf):
    for m in re.finditer(rb"ustar", buf):
        o = m.start() - 257
        h = buf[o:o + 512]
        try:
            sz = int(h[124:136].strip(b"\0 ") or b"0", 8)
        except ValueError:
            continue
        yield o, h[:100].rstrip(b"\0").decode(errors="ignore"), sz


def fetch(seq, out_dir):
    url = URL.format(seq)
    size = int(urllib.request.urlopen(urllib.request.Request(url, method="HEAD"), timeout=60).headers["Content-Length"])
    want = {"dso/imu.txt": None, "dso/gt_imu.csv": None}
    for tail in (40 << 20, 120 << 20):
        buf = rng(url, size - tail, size - 1)
        for o, name, sz in members(buf):
            for k in want:
                if name.endswith(k) and o + 512 + sz <= len(buf):
                    want[k] = buf[o + 512:o + 512 + sz]
        if all(v is not None for v in want.values()):
            break
    else:
        sys.exit(f"{seq}: members not found in tail")
    d = os.path.join(out_dir, seq)
    os.makedirs(os.path.join(d, "mav0", "imu0"), exist_ok=True)
    with open(os.path.join(d, "mav0", "imu0", "data.csv"), "w") as f:
        f.write("#timestamp [ns],w_RS_S_x [rad s^-1],w_RS_S_y [rad s^-1],w_RS_S_z [rad s^-1],"
                "a_RS_S_x [m s^-2],a_RS_S_y [m s^-2],a_RS_S_z [m s^-2]\n")
        for line in want["dso/imu.txt"].decode().splitlines():
            if line and not line.startswith("#"):
                f.write(",".join(line.split()) + "\n")
    with open(os.path.join(d, "groundtruth.txt"), "w") as f:  # TUM: t x y z qx qy qz qw
        for line in want["dso/gt_imu.csv"].decode().splitlines():
            if line and not line.startswith("#"):
                t, x, y, z, qw, qx, qy, qz = line.split(",")
                f.write(f"{int(t) * 1e-9:.9f} {x} {y} {z} {qx} {qy} {qz} {qw}\n")
    print(seq, "ok")


if __name__ == "__main__":
    for s in sys.argv[2:]:
        fetch(s, sys.argv[1])
