"""Pull only imu0/data.csv + state_groundtruth_estimate0/data.csv for EuRoC sequences out of the
12.7 GB ETH Research Collection zip, using HTTP range requests (the outer zip is stored, so the
inner per-sequence zip is fetched in one request). Writes the same layout as fetch_tumvi.py.

    python tools/fetch_euroc.py data_raw TMP_DIR MH_04_difficult ...
Each sequence zip (0.7-1.5 GB) is downloaded once and deleted after the two CSVs are extracted.
"""
import io
import os
import sys
import time
import urllib.error
import urllib.request
import zipfile
import zlib

URLS = {
    "MH": "https://www.research-collection.ethz.ch/server/api/core/bitstreams/7b2419c1-62b5-4714-b7f8-485e5fe3e5fe/content",
    "V1": "https://www.research-collection.ethz.ch/server/api/core/bitstreams/02ecda9a-298f-498b-970c-b7c44334d880/content",
    "V2": "https://www.research-collection.ethz.ch/server/api/core/bitstreams/ea12bc01-3677-4b4c-853d-87c7870b8c44/content",
}
FOLDER = {"MH": "machine_hall", "V1": "vicon_room1", "V2": "vicon_room2"}


def get(url, a, b):
    """Range GET with back-off: the Research Collection answers bursts with HTTP 429."""
    for k in range(10):
        req = urllib.request.Request(url, headers={"Range": f"bytes={a}-{b}", "User-Agent": "Mozilla/5.0"})
        try:
            with urllib.request.urlopen(req, timeout=300) as r:
                return r.read(), r.headers
        except urllib.error.HTTPError as e:
            if e.code != 429:
                raise
            wait = int(e.headers.get("Retry-After") or 0) or 15 * 2 ** k
            print(f"  429, waiting {wait}s", flush=True)
            time.sleep(min(wait, 600))
    raise RuntimeError("rate limited too long")


class HttpFile(io.RawIOBase):
    """Read-only seekable file over HTTP range requests, with a 1 MB block cache."""
    BLOCK = 1 << 20

    def __init__(self, url, base=0, size=None):
        """base/size: expose only a window of the remote file (a stored member of an outer zip)."""
        self.url, self.pos, self.cache, self.base = url, 0, {}, base
        if size is None:
            size = int(get(url, 0, 0)[1]["Content-Range"].split("/")[1])
        self.size = size

    def seekable(self):
        return True

    def readable(self):
        return True

    def tell(self):
        return self.pos

    def seek(self, off, whence=0):
        self.pos = {0: off, 1: self.pos + off, 2: self.size + off}[whence]
        return self.pos

    def _block(self, i):
        if i not in self.cache:
            a = self.base + i * self.BLOCK
            b = self.base + min(self.size, i * self.BLOCK + self.BLOCK) - 1
            self.cache[i] = get(self.url, a, b)[0]
            if len(self.cache) > 64:
                self.cache.pop(next(iter(self.cache)))
        return self.cache[i]

    def readinto(self, buf):
        n = min(len(buf), self.size - self.pos)
        out = 0
        while out < n:
            i, o = divmod(self.pos, self.BLOCK)
            chunk = self._block(i)[o:o + n - out]
            buf[out:out + len(chunk)] = chunk
            out += len(chunk)
            self.pos += len(chunk)
        return out


def fetch(seq, out_dir, tmp_dir):
    group = seq[:2]
    raw = HttpFile(URLS[group])
    outer = zipfile.ZipFile(io.BufferedReader(raw, 1 << 20))
    info = outer.getinfo(f"{FOLDER[group]}/{seq}/{seq}.zip")
    raw.seek(info.header_offset)
    hdr = raw.read(30)                                     # local file header -> data offset
    start = info.header_offset + 30 + int.from_bytes(hdr[26:28], "little") + int.from_bytes(hdr[28:30], "little")
    # the inner zip is deflated inside the outer one: stream it in ONE request, inflating to a temp file
    tmp = os.path.join(tmp_dir, seq + ".zip")
    req = urllib.request.Request(URLS[group], headers={"Range": f"bytes={start}-{start + info.compress_size - 1}",
                                                       "User-Agent": "Mozilla/5.0"})
    dec = zlib.decompressobj(-15)
    done = 0
    with urllib.request.urlopen(req, timeout=600) as r, open(tmp, "wb") as f:
        while True:
            chunk = r.read(1 << 22)
            if not chunk:
                break
            f.write(dec.decompress(chunk))
            done += len(chunk)
            print(f"  {done >> 20}/{info.compress_size >> 20} MB", end=chr(13), flush=True)
        f.write(dec.flush())
    inner = zipfile.ZipFile(tmp)
    imu = inner.read("mav0/imu0/data.csv")
    gt = inner.read("mav0/state_groundtruth_estimate0/data.csv").decode()
    d = os.path.join(out_dir, seq)
    os.makedirs(os.path.join(d, "mav0", "imu0"), exist_ok=True)
    with open(os.path.join(d, "mav0", "imu0", "data.csv"), "wb") as f:
        f.write(imu.replace(b"\r\n", b"\n"))
    with open(os.path.join(d, "groundtruth.txt"), "w") as f:  # TUM: t x y z qx qy qz qw
        for line in gt.splitlines():
            if line and not line.startswith("#"):
                c = line.split(",")
                f.write(f"{int(c[0]) * 1e-9:.9f} {c[1]} {c[2]} {c[3]} {c[5]} {c[6]} {c[7]} {c[4]}\n")
    inner.close()
    os.remove(tmp)
    print(seq, "ok")


if __name__ == "__main__":
    for s in sys.argv[3:]:
        fetch(s, sys.argv[1], sys.argv[2])
