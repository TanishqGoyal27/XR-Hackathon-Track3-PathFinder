# Path Finder: run instructions

## Requirements
- Python 3.9 or newer
- NumPy (`pip install -r requirements.txt`)

## Run
```bash
python main.py path/to/imu0/data.csv estimated_trajectory.txt
```
The input can also be the dataset folder (searched for `imu0/data.csv`) or the zipped dataset itself:
```bash
python main.py eval_dataset.zip estimated_trajectory.txt
```
If no output path is given, it writes `estimated_trajectory.txt` in the current folder.

## Input
- EuRoC `imu0/data.csv`: `timestamp [ns], gyro x y z [rad/s], accel x y z [m/s^2]`.
- A header or comment lines are optional.
- The gyro/accel column order is auto-detected: the accel group is the one whose magnitude is about 9.81 (or 1 if given in g).

## Output
`estimated_trajectory.txt` in TUM format: `timestamp tx ty tz qx qy qz qw`, separated by spaces.
- Timestamps are in seconds, converted exactly from the input's integer nanoseconds.
- There is exactly one pose per input row, including duplicated rows and the blind rows after the IMU fails.

## Limits (measured with `tools/profile.py` in the repository)
| | Measured | Budget |
|---|---|---|
| Peak heap (tracemalloc), 144 s of IMU | 6.1 MB | 8 MB |
| Runtime | 3.8 ms per 1 s of IMU | 20 ms |
| Threads | 1 | 1 |
