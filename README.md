# RTSP → Segmented MKV Recorder (Dual Camera)

Records two RTSP camera streams simultaneously to fixed-length MKV files using
**ffmpeg**.  Each camera writes to its own output folder.  Automatically
restarts on network drops, camera reboots, or other ffmpeg failures.  Stops
cleanly on Ctrl+C, `systemctl stop`, or after a configurable maximum recording
duration.

---

## How it works

```
ANPR Cam 1 (RTSP) ──► ffmpeg ──► data_recordings/ANPR Cam 1/anpr_2025-06-01_08-00-00.mkv
                              └──► data_recordings/ANPR Cam 1/anpr_2025-06-01_08-10-00.mkv …

ANPR Cam 2 (RTSP) ──► ffmpeg ──► data_recordings/ANPR Cam 2/anpr_2025-06-01_08-00-00.mkv
                              └──► data_recordings/ANPR Cam 2/anpr_2025-06-01_08-10-00.mkv …
```

1. **`run_recorder.sh`** launches two independent Python recorder processes in
   parallel — one for each camera.
2. Each recorder spawns its own **ffmpeg** process, which copies the compressed
   H.264/H.265 bitstream directly into MKV containers — no re-encoding, zero
   quality loss, minimal CPU.
3. Every `SEGMENT` seconds (default 600 = 10 min) ffmpeg closes the current
   file and opens a new one, embedding the start timestamp in the filename.
4. If ffmpeg exits unexpectedly (network glitch, camera offline, etc.) the
   Python wrapper restarts it after `RESTART_DELAY` seconds.
5. Press **Ctrl+C** (or send SIGTERM to the launcher) to stop both recorders
   cleanly at the same time.

---

## Output directory layout

```
data_recordings/
├── ANPR Cam 1/
│   ├── anpr_2025-06-01_08-00-00.mkv
│   ├── anpr_2025-06-01_08-10-00.mkv
│   └── …
└── ANPR Cam 2/
    ├── anpr_2025-06-01_08-00-00.mkv
    ├── anpr_2025-06-01_08-10-00.mkv
    └── …
```

Directories are created automatically on first run.

---

## Files

| File | Purpose |
|------|---------|
| `run_recorder.sh` | Configure camera URLs and shared settings, then launch both recorders |
| `rtsp_to_mkv_segments.py` | Single-stream recorder — called twice by the launcher |
| `SETUP.md` | Quick-start guide |
| `README.md` | This documentation |

---

## Requirements

| Requirement | Version |
|-------------|---------|
| Ubuntu | 20.04 LTS or later (22.04 recommended) |
| Python | 3.9 or later |
| ffmpeg | 4.x or later |

---

## Step-by-step setup on Ubuntu

### 1 — Update the package index

```bash
sudo apt-get update
```

### 2 — Install ffmpeg

```bash
sudo apt-get install -y ffmpeg
ffmpeg -version
```

### 3 — Install Python 3.9+

```bash
python3 --version   # must be 3.9 or later
```

Ubuntu 20.04 ships Python 3.8; install 3.9 if needed:

```bash
sudo apt-get install -y python3.9 python3.9-venv
```

> No `pip install` step is required — the script uses only the standard library.

### 4 — Copy the scripts to the machine

```bash
git clone <your-repo-url>
cd rtsp-stream-download
```

Or with scp:

```bash
scp rtsp_to_mkv_segments.py run_recorder.sh ubuntu@<SERVER_IP>:/home/ubuntu/
```

### 5 — Configure camera URLs

Edit `run_recorder.sh` and replace the placeholder credentials:

```bash
CAM1_URL="rtsp://username:password@40.10.18.28:554/avstream/channel=1/stream=0.sdp"
CAM2_URL="rtsp://username:password@40.10.18.29:554/avstream/channel=1/stream=0.sdp"
```

### 6 — Run the recorders (foreground / test)

```bash
bash run_recorder.sh
```

You should see output similar to:

```
[launcher] ─────────────────────────────────────────────────────────
[launcher] ANPR Cam 1 → ./data_recordings/ANPR Cam 1
[launcher] ANPR Cam 2 → ./data_recordings/ANPR Cam 2
[launcher] ─────────────────────────────────────────────────────────
[launcher] Starting both recorders. Press Ctrl+C to stop.

[launcher] ANPR Cam 1 PID : 12345  (log: ./anpr_cam1.log)
[launcher] ANPR Cam 2 PID : 12346  (log: ./anpr_cam2.log)
[recorder] Recording started. Press Ctrl+C to stop.
[recorder] Recording started. Press Ctrl+C to stop.
```

Press **Ctrl+C** to stop both cameras at the same time.

---

## Shared settings (run_recorder.sh)

| Variable | Default | Description |
|----------|---------|-------------|
| `SEGMENT` | `600` | Segment length in seconds (600 = 10 min) |
| `TCP` | *(unset)* | Uncomment `TCP="--tcp"` to force TCP transport |
| `RESTART_DELAY` | `5` | Seconds to wait before restarting ffmpeg after a crash |
| `MAX_RESTARTS` | `0` | Stop after N restarts per camera; 0 = retry forever |
| `MAX_DURATION` | `0` | Max total recording time in seconds; 0 = no limit |
| `EXTRA_ARGS` | *(unset)* | Extra ffmpeg output options, e.g. `"-an"` to strip audio |

---

## Running in the background (nohup)

```bash
nohup bash run_recorder.sh > /dev/null 2>&1 &
echo "Launcher PID: $!"
```

Both recorders run as children of the launcher process.  Stop everything with:

```bash
kill <LAUNCHER_PID>
```

---

## Running as a systemd service (recommended for production)

Create `/etc/systemd/system/rtsp-recorder.service`:

```ini
[Unit]
Description=RTSP to MKV Dual-Camera Recorder
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=<YOUR_USER>
WorkingDirectory=/home/<YOUR_USER>/rtsp-stream-download

ExecStart=/bin/bash /home/<YOUR_USER>/rtsp-stream-download/run_recorder.sh

# Restart the launcher if it exits unexpectedly.
Restart=on-failure
RestartSec=10

# Give ffmpeg time to close the current segments on shutdown.
TimeoutStopSec=15

[Install]
WantedBy=multi-user.target
```

Enable and start:

```bash
sudo systemctl daemon-reload
sudo systemctl start rtsp-recorder
sudo systemctl enable rtsp-recorder
sudo systemctl status rtsp-recorder
```

View logs:

```bash
tail -f /home/<YOUR_USER>/rtsp-stream-download/anpr_cam1.log
tail -f /home/<YOUR_USER>/rtsp-stream-download/anpr_cam2.log
# or via journalctl:
journalctl -u rtsp-recorder -f
```

---

## Verifying recordings

List segments (newest last):

```bash
ls -lhtr "data_recordings/ANPR Cam 1/"*.mkv
ls -lhtr "data_recordings/ANPR Cam 2/"*.mkv
```

Play a segment:

```bash
ffplay "data_recordings/ANPR Cam 1/anpr_2025-06-01_08-00-00.mkv"
```

Inspect without playing:

```bash
ffprobe -v quiet -print_format json -show_format -show_streams \
    "data_recordings/ANPR Cam 1/anpr_2025-06-01_08-00-00.mkv"
```

---

## Disk space management

The recorder does **not** automatically delete old files.  Add a cron job to
remove segments older than a given number of days.

Example: delete files older than 7 days from both folders, run every hour:

```bash
crontab -e
```

Add:

```cron
0 * * * * find /path/to/rtsp-stream-download/data_recordings -name "*.mkv" -mtime +7 -delete
```

---

## Troubleshooting

### "ffmpeg not found"

```bash
sudo apt-get install -y ffmpeg
```

### "Connection timed out" / stream not connecting

1. Confirm the camera is reachable: `ping 40.10.18.28`
2. Confirm the RTSP port is open: `nc -zv 40.10.18.28 554`
3. Test the URL directly: `ffplay "rtsp://username:password@40.10.18.28:554/avstream/channel=1/stream=0.sdp"`
4. Try enabling TCP in `run_recorder.sh`: uncomment `TCP="--tcp"`
5. Check that credentials are correct (URL-encode special characters if needed:
   `@` → `%40`, `:` → `%3A`).

### ffmpeg exits immediately with code 1

Check the per-camera log:

```bash
tail -50 anpr_cam1.log
tail -50 anpr_cam2.log
```

Common causes: wrong RTSP URL or credentials, camera offline, or incorrect stream path.

### Segments are corrupt or unplayable

- Enable TCP: uncomment `TCP="--tcp"` in `run_recorder.sh`.
- Increase `RESTART_DELAY` to give the camera more time to reboot.
- Check disk space: `df -h data_recordings`.

### High CPU usage

The default `-c copy` (stream copy) uses almost no CPU.  High CPU typically
means transcoding was accidentally enabled via `EXTRA_ARGS`.

### Segments named with wrong timestamp

```bash
timedatectl status
sudo timedatectl set-ntp true
```

---

## Security notes

- **RTSP credentials appear in the process list** (`ps aux`) and in the log
  files.  Restrict log file permissions:
  ```bash
  chmod 600 anpr_cam1.log anpr_cam2.log
  ```
- Run the recorder as a dedicated low-privilege user rather than root.
- If the RTSP URL contains special characters in the password, URL-encode them
  or wrap the argument in single quotes to prevent shell interpretation.
