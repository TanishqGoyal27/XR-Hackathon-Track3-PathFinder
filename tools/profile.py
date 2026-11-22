"""Peak heap (tracemalloc, what the FAQ says is measured) and runtime per second of IMU.

    python tools/profile.py <imu0/data.csv> [out.txt]
"""
import os, sys, time, tracemalloc
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "submission", "src"))
import numpy as np  # noqa: E402  (imported before tracing: interpreter/library cost is excluded per FAQ)
import main  # noqa: E402

src = sys.argv[1]
out = sys.argv[2] if len(sys.argv) > 2 else os.devnull
tracemalloc.start()
t0 = time.perf_counter()
sys.argv = ["main.py", src, out]
main.main()
dt = time.perf_counter() - t0
_, peak = tracemalloc.get_traced_memory()
tracemalloc.stop()
t0 = time.perf_counter(); main.main(); dt2 = time.perf_counter() - t0   # untraced timing
ts, _ = main.read_imu(src)
dur = (ts[-1] - ts[0]) * 1e-9
print(f"rows={len(ts)} duration={dur:.1f}s peak_heap={peak/1e6:.2f}MB runtime={dt2:.3f}s "
      f"-> {1000*dt2/dur:.2f} ms per 1 s of IMU (budget 20)")
