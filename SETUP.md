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

## 4. Run the recorder

Recordings are saved automatically to `data_recordings/` in the same directory as the script.

```bash
python3 rtsp_to_mkv_segments.py \
    --rtsp "rtsp://user:password@<CAMERA_IP>:554/stream1" \
    --tcp
```

Press **Ctrl+C** to stop.

---

## Common options

| Flag | Default | Description |
|------|---------|-------------|
| `--rtsp URL` | *(required)* | Full RTSP URL including credentials |
| `--out DIR` | `data_recordings/` | Override the output directory |
| `--segment N` | `600` | Segment length in seconds |
| `--tcp` | off | Force RTSP over TCP (recommended) |
| `--max-duration N` | `14400` | Stop after N seconds; `0` = no limit |
| `--log FILE` | `ffmpeg_recorder.log` | Log file path |

### Examples

Record in 30-minute segments with no time limit:
```bash
python3 rtsp_to_mkv_segments.py \
    --rtsp "rtsp://admin:secret@192.168.1.10:554/stream1" \
    --segment 1800 \
    --max-duration 0 \
    --tcp
```

Strip audio, save to a custom directory:
```bash
python3 rtsp_to_mkv_segments.py \
    --rtsp "rtsp://admin:secret@192.168.1.10:554/stream1" \
    --out /mnt/nas/recordings \
    --extra-ffmpeg-args "-an" \
    --tcp
```

---

## Run in the background (nohup)

```bash
nohup python3 rtsp_to_mkv_segments.py \
    --rtsp "rtsp://admin:secret@192.168.1.10:554/stream1" \
    --tcp \
    --max-duration 0 \
    > /dev/null 2>&1 &

echo "PID: $!"
```

Stop it:
```bash
kill <PID>
```

---

## Verify recordings

```bash
ls -lhtr data_recordings/*.mkv
```

Play a segment:
```bash
ffplay data_recordings/anpr_<timestamp>.mkv
```
