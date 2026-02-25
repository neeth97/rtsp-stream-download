# Setup & Run Guide

## Requirements

- Python 3.9+
- ffmpeg 4.x+

---

## 1. Clone the repository

```bash
git clone https://github.com/neeth97/rtsp-stream-download.git
cd rtsp-stream-download
```

## 2. Install ffmpeg

**macOS**
```bash
brew install ffmpeg
```

**Ubuntu / Debian**
```bash
sudo apt-get update
sudo apt-get install -y ffmpeg
```

Verify:
```bash
ffmpeg -version
```

## 3. Verify Python version

```bash
python3 --version
```

Must be 3.9 or later. No additional packages are required — the script uses only the standard library.

---

## 4. Configure camera URLs

Open `run_recorder.sh` and set the RTSP credentials for each camera:

```bash
CAM1_URL="rtsp://username:password@40.10.18.28:554/avstream/channel=1/stream=0.sdp"
CAM2_URL="rtsp://username:password@40.10.18.29:554/avstream/channel=1/stream=0.sdp"
```

Replace `username` and `password` with the actual camera credentials.

---

## 5. Run both recorders simultaneously

```bash
bash run_recorder.sh
```

This launches **two recorders in parallel** — one per camera. Recordings are saved to:

```
data_recordings/
├── ANPR Cam 1/
│   ├── anpr_2025-06-01_08-00-00.mkv
│   └── anpr_2025-06-01_08-10-00.mkv
└── ANPR Cam 2/
    ├── anpr_2025-06-01_08-00-00.mkv
    └── anpr_2025-06-01_08-10-00.mkv
```

Press **Ctrl+C** to stop both recorders cleanly.

---

## 6. Run a single camera manually (optional)

```bash
python3 rtsp_to_mkv_segments.py \
    --rtsp "rtsp://username:password@40.10.18.28:554/avstream/channel=1/stream=0.sdp" \
    --out "./data_recordings/ANPR Cam 1" \
    --log "./anpr_cam1.log" \
    --tcp
```

---

## Common options (shared settings in run_recorder.sh)

| Variable | Default | Description |
|----------|---------|-------------|
| `SEGMENT` | `600` | Segment length in seconds |
| `TCP` | *(unset)* | Uncomment `TCP="--tcp"` to force TCP transport |
| `RESTART_DELAY` | `5` | Seconds to wait before restarting after a crash |
| `MAX_RESTARTS` | `0` | Max restarts per recorder; 0 = retry forever |
| `MAX_DURATION` | `0` | Max recording time in seconds; 0 = no limit |
| `EXTRA_ARGS` | *(unset)* | Extra ffmpeg args, e.g. `"-an"` to strip audio |

---

## Run in the background (nohup)

```bash
nohup bash run_recorder.sh > /dev/null 2>&1 &
echo "Launcher PID: $!"
```

Stop both recorders:
```bash
kill <PID>
```

---

## Verify recordings

```bash
ls -lhtr "data_recordings/ANPR Cam 1/"*.mkv
ls -lhtr "data_recordings/ANPR Cam 2/"*.mkv
```

Play a segment:
```bash
ffplay "data_recordings/ANPR Cam 1/anpr_<timestamp>.mkv"
```

## Check logs

```bash
tail -f anpr_cam1.log
tail -f anpr_cam2.log
```
