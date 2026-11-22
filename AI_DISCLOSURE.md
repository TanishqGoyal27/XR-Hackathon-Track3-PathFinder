# AI Disclosure

**Tool used:** an AI coding assistant (large language model).

**What it helped with**
- Reading and summarising the organisers' Track 3 material (slides, FAQ, `degrade_imu.py`).
- Coding assistance: implementation, debugging and testing.
- Tuning parameters against our local scorer, and drafting the README and slides text.

**What we did ourselves**
- Chose the approach and reviewed and ran every part of the pipeline.
- Checked the results against ground truth with our scorer (`tools/evaluate.py`).
- Recorded the demo video and gave the presentation.

**What the AI was not used for:** No model, network or AI service runs inside the submission. `main.py` is plain NumPy signal processing and runs fully offline.
