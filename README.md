# RTSP → Segmented MKV Recorder

Records an RTSP camera stream to fixed-length MKV files using **ffmpeg**.
Automatically restarts on network drops, camera reboots, or other ffmpeg
failures.  Stops cleanly on Ctrl+C, `systemctl stop`, or after a configurable
maximum recording duration.

---

## How it works

```
Camera (RTSP) ──► ffmpeg ──► anpr_2025-06-01_08-00-00.mkv
                         └──► anpr_2025-06-01_08-10-00.mkv
                         └──► anpr_2025-06-01_08-20-00.mkv  …
```

1. **ffmpeg connects** to the RTSP URL and copies the compressed H.264/H.265
   bitstream directly into MKV containers — no re-encoding, zero quality loss,
   minimal CPU.
2. Every `--segment` seconds (default 600 = 10 min) ffmpeg closes the current
   file and opens a new one, embedding the start timestamp in the filename.
3. If ffmpeg exits unexpectedly (network glitch, camera offline, etc.) the
   Python wrapper restarts it after `--restart-delay` seconds.
4. The script stops when:
   - You press **Ctrl+C** or send `SIGTERM`, OR
   - The total elapsed time exceeds `--max-duration` seconds (default 14 400 s
     = 4 hours), OR
   - ffmpeg has been restarted more than `--max-restarts` times (optional).

---

## Files

| File | Purpose |
|------|---------|
| `rtsp_to_mkv_segments.py` | The recorder script — the only file you need to run |
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

Always run this first to avoid installing outdated package versions.

```bash
sudo apt-get update
```

### 2 — Install ffmpeg

```bash
sudo apt-get install -y ffmpeg
```

Verify the installation:

```bash
ffmpeg -version
```

You should see output beginning with `ffmpeg version 4.x.x …` or `5.x.x`.
If the command is not found, ensure `/usr/bin` is on your `PATH`.

### 3 — Install Python 3.9+

Ubuntu 20.04 ships Python 3.8; Ubuntu 22.04 ships Python 3.10.
Check what you have:

```bash
python3 --version
```

If you are on Ubuntu 20.04 and need 3.9+:

```bash
sudo apt-get install -y python3.9 python3.9-venv
```

> **Note:** The script uses only the Python standard library — no `pip install`
> step is needed.

### 4 — Copy the script to the machine

If you are on a remote Ubuntu server, copy the file with `scp`:

```bash
scp rtsp_to_mkv_segments.py ubuntu@<SERVER_IP>:/home/ubuntu/
```

Or clone your repository:

```bash
git clone <your-repo-url>
cd <repo-directory>
```

### 5 — Create the output directory

The script creates this automatically, but you can pre-create it and set
permissions explicitly:

```bash
sudo mkdir -p /data/recordings
sudo chown $USER:$USER /data/recordings
```

> Make sure the filesystem has enough free space.  A typical 1080p H.264 stream
> uses roughly **0.5 – 2 GB per hour** depending on bitrate and scene activity.
> Check free space with `df -h /data/recordings`.

### 6 — Run the recorder (foreground / test)

Use this for an initial test.  Press **Ctrl+C** to stop.

```bash
python3 rtsp_to_mkv_segments.py \
    --rtsp "rtsp://admin:password@192.168.1.10:554/stream1" \
    --out  /data/recordings \
    --segment 600 \
    --tcp
```

You should see output similar to:

```
[recorder] ──────────────────────────────────────────────────
[recorder] Output directory  : /data/recordings
[recorder] Log file          : /home/ubuntu/ffmpeg_recorder.log
[recorder] Segment length    : 600 s  (0:10:00)
[recorder] Max duration      : 14400 s  (stops around 2025-06-01 12:00:00)
[recorder] Max restarts      : unlimited
[recorder] Restart delay     : 5 s
[recorder] FFmpeg command    : ffmpeg -hide_banner -loglevel info …
[recorder] ──────────────────────────────────────────────────
[recorder] Recording started. Press Ctrl+C to stop.
[recorder] Launching ffmpeg (launch #0) …
```

After 10 minutes the first MKV segment appears in `/data/recordings/`.

---

## All command-line arguments

| Argument | Default | Description |
|----------|---------|-------------|
| `--rtsp URL` | *(required)* | Full RTSP URL, e.g. `rtsp://user:pass@ip:554/stream` |
| `--out DIR` | `./recordings` | Output directory for MKV files |
| `--segment N` | `600` | Segment length in seconds (600 = 10 min) |
| `--tcp` | off | Force RTSP over TCP (recommended for NAT / VPN) |
| `--restart-delay N` | `5` | Seconds to wait before restarting ffmpeg after a crash |
| `--max-restarts N` | `0` | Stop after N restarts; 0 = retry forever |
| `--max-duration N` | `14400` | Stop after N total seconds (0 = no limit) |
| `--log FILE` | `./ffmpeg_recorder.log` | Log file path (appended, parent dir created automatically) |
| `--extra-ffmpeg-args ARGS` | *(empty)* | Extra ffmpeg output options, e.g. `"-an"` to strip audio |

### Common `--max-duration` values

| Duration | Seconds |
|----------|---------|
| 1 hour | 3600 |
| 4 hours (default) | 14400 |
| 8 hours | 28800 |
| 24 hours | 86400 |
| No limit | 0 |

---

## Running in the background (nohup)

To keep the recorder running after you log out of an SSH session:

```bash
nohup python3 /home/ubuntu/rtsp_to_mkv_segments.py \
    --rtsp "rtsp://admin:password@192.168.1.10:554/stream1" \
    --out  /data/recordings \
    --segment 600 \
    --tcp \
    --log /data/recordings/recorder.log \
    > /dev/null 2>&1 &

echo "PID: $!"
```

Stop it later with:

```bash
kill <PID>
```

---

## Running as a systemd service (recommended for production)

Running as a systemd service means the recorder:
- Starts automatically on boot.
- Restarts automatically if the Python process itself crashes.
- Integrates with `journalctl` for log viewing.
- Can be stopped cleanly with `systemctl stop`.

### Create the service file

```bash
sudo nano /etc/systemd/system/rtsp-recorder.service
```

Paste the following, replacing the values in `< >`:

```ini
[Unit]
Description=RTSP to MKV Segmented Recorder
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=<YOUR_USER>
WorkingDirectory=/home/<YOUR_USER>

ExecStart=/usr/bin/python3 /home/<YOUR_USER>/rtsp_to_mkv_segments.py \
    --rtsp "rtsp://admin:password@192.168.1.10:554/stream1" \
    --out  /data/recordings \
    --segment 600 \
    --tcp \
    --max-duration 0 \
    --log /data/recordings/recorder.log

# Restart the Python wrapper if it exits unexpectedly.
# (The wrapper already handles ffmpeg restarts internally.)
Restart=on-failure
RestartSec=10

# Give ffmpeg up to 10 seconds to close the current segment on shutdown.
TimeoutStopSec=10

[Install]
WantedBy=multi-user.target
```

> Set `--max-duration 0` when using systemd so the service runs indefinitely
> and systemd handles the lifecycle.  Use `--max-duration 14400` for a 4-hour
> auto-stop if you prefer the script to manage its own lifetime.

### Enable and start the service

```bash
# Reload systemd so it sees the new file
sudo systemctl daemon-reload

# Start the service now
sudo systemctl start rtsp-recorder

# Enable it to start on every boot
sudo systemctl enable rtsp-recorder

# Check status
sudo systemctl status rtsp-recorder
```

### View logs

```bash
# Live tail of the recorder log file
tail -f /data/recordings/recorder.log

# Or via journalctl (systemd's journal)
journalctl -u rtsp-recorder -f
```

### Stop / restart the service

```bash
sudo systemctl stop rtsp-recorder
sudo systemctl restart rtsp-recorder
```

---

## Verifying recordings

List segments sorted by time (newest last):

```bash
ls -lhtr /data/recordings/*.mkv
```

Play a segment with ffplay (part of the ffmpeg package):

```bash
ffplay /data/recordings/anpr_2025-06-01_08-00-00.mkv
```

Inspect a segment without playing it:

```bash
ffprobe -v quiet -print_format json -show_format -show_streams \
    /data/recordings/anpr_2025-06-01_08-00-00.mkv
```

---

## Disk space management

The recorder does **not** automatically delete old files.  Add a cron job to
remove segments older than a given number of days.

Example: delete files older than 7 days, run every hour:

```bash
crontab -e
```

Add:

```cron
0 * * * * find /data/recordings -name "*.mkv" -mtime +7 -delete
```

---

## Troubleshooting

### "ffmpeg not found"

```bash
sudo apt-get install -y ffmpeg
```

### "Connection timed out" / stream not connecting

1. Confirm the camera is reachable: `ping 192.168.1.10`
2. Confirm the RTSP port is open: `nc -zv 192.168.1.10 554`
3. Test the URL directly: `ffplay "rtsp://admin:password@192.168.1.10:554/stream1"`
4. Try adding `--tcp` — some cameras only accept TCP.
5. Check that the credentials are correct (some cameras URL-encode special
   characters: `@` → `%40`, `:` → `%3A`).

### ffmpeg exits immediately with code 1

Check the log file for the error:

```bash
tail -50 /data/recordings/recorder.log
```

Common causes:
- Wrong RTSP URL or credentials.
- Camera is offline or the stream path is incorrect.
- ffmpeg build does not support the camera's codec (rare with the apt package).

### Segments are corrupt or unplayable

- Ensure `--tcp` is set — UDP packet loss on a bad network can corrupt the
  elementary stream.
- Increase `--restart-delay` to give the camera time to fully reboot before
  reconnecting.
- Check that the disk is not full: `df -h /data/recordings`.

### High CPU usage

The default `-c copy` (stream copy) uses almost no CPU.  If CPU is high:
- You may have accidentally enabled transcoding via `--extra-ffmpeg-args`.
- Another process on the system is decoding the MKV files simultaneously.

### Segments named with wrong timestamp

Verify that the Ubuntu machine's clock is correct:

```bash
timedatectl status
```

Enable automatic time synchronisation:

```bash
sudo timedatectl set-ntp true
```

---

## Security notes

- **RTSP credentials appear in the process list** (`ps aux`) and in the log
  file.  Restrict log file permissions: `chmod 600 /data/recordings/recorder.log`.
- If the RTSP URL contains special characters in the password, URL-encode them
  or wrap the argument in single quotes to prevent shell interpretation.
- Run the recorder as a dedicated low-privilege user rather than root.
