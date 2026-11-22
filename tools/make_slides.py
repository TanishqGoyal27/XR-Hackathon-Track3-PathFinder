"""Fill the organisers' submission template -> presentation/Track3_PathFinder.pptx"""
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import FancyBboxPatch  # noqa: E402
from pptx import Presentation  # noqa: E402
from pptx.util import Emu, Pt  # noqa: E402
from pptx.dml.color import RGBColor  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RES = os.path.join(ROOT, "results")
OUT = os.path.join(ROOT, "presentation")
os.makedirs(OUT, exist_ok=True)

# ---- architecture diagram
steps = [("Load", "NumPy C parser, float32\nauto-detect accel cols\nfind blind tail (zeros)"),
         ("Clean", "spikes: neighbour test\nstuck runs: repeats\ndropouts: keep real dt"),
         ("Attitude", "gyro quaternion\nintegration (midpoint)\ntilt from gravity"),
         ("Position", "R·a − g, integrate x2\nzero-phase high-pass\non v (5 s) and p (8 s)"),
         ("Blind 5 s", "ω, v decay (τ)\nposition relaxes\nto long-term mean"),
         ("Write", "TUM, chunked\nexact ns → s\n1 pose per row")]
fig, ax = plt.subplots(figsize=(12, 3.2))
ax.set_xlim(0, 12); ax.set_ylim(0, 3.2); ax.axis("off")
for i, (h, b) in enumerate(steps):
    x = 0.15 + i * 2.0
    ax.add_patch(FancyBboxPatch((x, 0.35), 1.7, 2.5, boxstyle="round,pad=0.04", fc="#eef4ff", ec="#1f6feb", lw=1.5))
    ax.text(x + 0.85, 2.45, h, ha="center", va="center", fontsize=13, weight="bold", color="#0b3d91")
    ax.text(x + 0.85, 1.35, b, ha="center", va="center", fontsize=9.5)
    if i < len(steps) - 1:
        ax.annotate("", xy=(x + 2.0, 1.6), xytext=(x + 1.78, 1.6), arrowprops=dict(arrowstyle="->", lw=1.6))
fig.tight_layout()
fig.savefig(os.path.join(RES, "pipeline.png"), dpi=160)

# ---- slides
pr = Presentation(os.path.join(ROOT, "Submission_Final_forGithub.pptx"))
S = list(pr.slides)
TOP, LEFT, W = Emu(900000), Emu(365760), Emu(8412480)


def set_text(shape, text):
    tf = shape.text_frame
    runs = [r for p in tf.paragraphs for r in p.runs]
    if runs:
        runs[0].text = text
        for r in runs[1:]:
            r.text = ""
    else:
        tf.text = text


def bullets(slide, items, left=LEFT, top=TOP, width=W, height=Emu(4000000), size=13):
    tb = slide.shapes.add_textbox(left, top, width, height)
    tf = tb.text_frame
    tf.word_wrap = True
    for i, it in enumerate(items):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        sub = it.startswith("  ")
        p.text = ("– " if sub else "• ") + it.strip()
        p.level = 1 if sub else 0
        p.space_after = Pt(4)
        for r in p.runs:
            r.font.size = Pt(size - 2 if sub else size)
            r.font.color.rgb = RGBColor(0xA8, 0xBC, 0xD0) if sub else RGBColor(0xE6, 0xED, 0xF3)
    return tb


def image(slide, path, left, top, width=None, height=None):
    slide.shapes.add_picture(path, left, top, width=width, height=height)


# 1 title
for sh in S[0].shapes:
    if not sh.has_text_frame:
        continue
    t = sh.text_frame.text
    if t.startswith("Track No"):
        set_text(sh, "Track 03")
    elif t.startswith("XR Hackathon"):
        set_text(sh, "Path Finder")
        bullets(S[0], ["6-DoF trajectory estimation under IMU degradation"], left=Emu(502920), top=Emu(3400000),
                width=Emu(6000000), height=Emu(300000), size=14)
    elif t.startswith("Team Name"):
        ps = sh.text_frame.paragraphs
        ps[0].runs[0].text = "day_dreamers"
        ps[1].runs[0].text = "Thapar Institute of Engineering and Technology"
    elif t.startswith("Members"):
        set_text(sh, "Members: Tanishq Goyal, Saanjal Jain, Ridhi, Chakshu Arora")
        sh.left, sh.top, sh.width = Emu(502920), Emu(3850000), Emu(7800000)  # below the long college name

# 2 problem
bullets(S[1], [
    "An aircraft flies through waypoints with no GPS. Its only sensor is an IMU (gyro + accelerometer)",
    "Enemy jamming degrades the IMU more and more over time:",
    "  white noise, bias random walk, scale-factor drift, spikes, stuck values",
    "  missing rows (dropouts), duplicated rows",
    "  final 5 s: the IMU dies completely (all-zero rows)",
    "Goal: a 6-DoF pose (position + orientation) for every IMU row, then dead-reckon through the 5 blind seconds",
    "Why it's hard: position = accel integrated twice, so a 0.05 m/s² bias becomes 500 m of error after 140 s",
    "Budgets: ≤ 8 MB peak heap · ≤ 20 ms per 1 s of IMU · single thread · Python only · offline",
])

# 3 solution
bullets(S[2], [
    "Physics pipeline, no learning: plain NumPy, one file (src/main.py), about 300 lines",
    "Key idea: the task is OFFLINE, so we can filter without lag (zero-phase, non-causal)",
    "  slow errors (bias, tilt, scale) only produce slow drift after double integration",
    "  centred high-pass on velocity (5 s) and position (8 s) removes the drift and keeps the motion",
    "Robust input handling: auto-detects gyro/accel column order, units, blind tail, dropouts and duplicates",
    "Signal cleaning: spike and stuck-value detection with robust statistics, then interpolation",
    "Blind 5 s: decaying angular rate and velocity; position relaxes to the mean",
    "  2–5× better than constant-velocity extrapolation on our tests",
    "Result: naive integration 147 m ATE → ours 0.62 m (12 degraded runs)",
], width=Emu(8412480))

# 4 architecture
image(S[3], os.path.join(RES, "pipeline.png"), LEFT, Emu(1050000), width=W)
bullets(S[3], ["Memory: float32 input, everything processed in 1024-row chunks, in-place integration (≈200 B per row)",
               "Speed: vectorised NumPy plus one scalar quaternion loop, about 4 ms per 1 s of IMU"],
        top=Emu(3750000), height=Emu(900000), size=12)

# 5 final output
image(S[4], os.path.join(RES, "trajectory.png"), LEFT, Emu(870000), width=Emu(5600000))
bullets(S[4], [
    "Output: estimated_trajectory.txt (TUM)",
    "  one pose per input row",
    "  exact ns → s timestamps",
    "Local scores (ATE RMSE, SE(3) aligned):",
    "  mean of 12 runs: 0.62 m",
    "  static baseline: 1.08 m",
    "  naive integration: 147 m",
    "  blind 5 s: 0.65 m",
    "Peak heap 6.1 MB (≤ 8)",
    "3.8 ms per 1 s of IMU (≤ 20)",
], left=Emu(6050000), top=Emu(900000), width=Emu(2900000), size=12)

for sh in S[4].shapes:
    if sh.has_text_frame and sh.text_frame.text.startswith("Track Final Output"):
        set_text(sh, "TRACK FINAL OUTPUT")

# 6 differentiation
image(S[5], os.path.join(RES, "ablation.png"), Emu(5000000), Emu(900000), width=Emu(3950000))
bullets(S[5], [
    "Exploits 'offline': zero-phase filtering, no lag",
    "Every component justified by an ablation",
    "  what didn't help was removed: Mahony tilt correction, batch bias calibration",
    "Robust to the format traps we found in the organiser kit",
    "  degrade_imu.py assumes accel-first, but EuRoC is gyro-first: auto-detected",
    "Lean: 3.8 ms/s and 6 MB, well inside the budgets (40% of the score)",
    "Exactly one pose per row, verified automatically",
], width=Emu(4550000), size=12)

# 7 demo & setup
for sh in S[6].shapes:
    if sh.name == "Text Box 36":
        sh._element.getparent().remove(sh._element)
bullets(S[6], [
    "pip install numpy",
    "python submission/src/main.py <imu0/data.csv | dataset.zip | folder> estimated_trajectory.txt",
    "Reproduce our numbers:",
    "  python tools/fetch_tumvi.py data_raw room1 … room6  (IMU + GT only, via HTTP range requests)",
    "  python tools/make_test_data.py data_raw data_test room1 … room6  (official degrade_imu.py)",
    "  python tools/tune.py · python tools/plot.py · python tools/profile.py <csv>",
    "Score with evo: evo_ape tum groundtruth.txt estimated_trajectory.txt -a",
    "Demo video: VIDEO_LINK",
    "GitHub: REPO_LINK",
], size=12)

# 8 brownie
for sh in S[7].shapes:
    if sh.name == "Text Box 36":
        sh._element.getparent().remove(sh._element)
bullets(S[7], [
    "Found an inconsistency in the kit: degrade_imu.py treats columns 1–3 as accel, but EuRoC stores gyro there",
    "  we test on both variants (A: as-is, B: swapped), and our column detection handles both",
    "Data-efficient tooling: pulled only the IMU + ground-truth CSVs out of 1.7 GB TUM-VI archives with HTTP range requests",
    "Honest engineering: we tried a Mahony filter and a least-squares bias calibration; they didn't help, so we removed them",
    "Known limitation: slow, large-scale displacement can't be recovered from an IMU alone",
    "  the high-pass filter treats it as drift, so the path comes out smaller and centred",
    "Next step with more time: a tiny learned velocity prior (TLIO-style) within the 8 MB budget",
], size=12)

pr.save(os.path.join(OUT, "Track3_PathFinder.pptx"))
print("saved", os.path.join(OUT, "Track3_PathFinder.pptx"))
