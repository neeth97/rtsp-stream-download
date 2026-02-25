#!/usr/bin/env bash
# =============================================================================
# run_recorder.sh — Edit this file to configure and launch the RTSP recorder.
# Usage: bash run_recorder.sh
# =============================================================================

# -----------------------------------------------------------------------------
# REQUIRED — Replace with your camera's RTSP URL
# -----------------------------------------------------------------------------
RTSP_URL="rtsp://username:password@IP:554/cam/realmonitor?channel=1&subtype=0"

# -----------------------------------------------------------------------------
# OPTIONAL — Uncomment and edit any line below to override the default value
# -----------------------------------------------------------------------------

# Output directory for MKV segment files
# Default: data_recordings/ next to the script
# OUT_DIR="./data_recordings"

# Length of each recorded segment in seconds (600 = 10 minutes)
SEGMENT=600

# Force RTSP transport over TCP (recommended for NAT, VPN, or unreliable links)
# Set to "--tcp" to enable, or leave commented out to use UDP
# TCP="--tcp"

# Seconds to wait before restarting ffmpeg after an unexpected exit
RESTART_DELAY=5

# Stop permanently after ffmpeg has been restarted N times (0 = retry forever)
MAX_RESTARTS=0

# Maximum total recording time in seconds (0 = no limit, 14400 = 4 hours)
MAX_DURATION=2000

# Log file path
# Default: ffmpeg_recorder.log next to the script
# LOG_FILE="./ffmpeg_recorder.log"

# Extra ffmpeg output-level arguments (e.g. "-an" to strip audio)
# EXTRA_ARGS="-an"

# =============================================================================
# DO NOT EDIT BELOW THIS LINE
# =============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

CMD=(python3 "$SCRIPT_DIR/rtsp_to_mkv_segments.py" --rtsp "$RTSP_URL")

[ -n "${OUT_DIR:-}"       ] && CMD+=(--out            "$OUT_DIR")
[ -n "${SEGMENT:-}"       ] && CMD+=(--segment         "$SEGMENT")
[ -n "${TCP:-}"           ] && CMD+=("$TCP")
[ -n "${RESTART_DELAY:-}" ] && CMD+=(--restart-delay   "$RESTART_DELAY")
[ -n "${MAX_RESTARTS:-}"  ] && CMD+=(--max-restarts     "$MAX_RESTARTS")
[ -n "${MAX_DURATION:-}"  ] && CMD+=(--max-duration     "$MAX_DURATION")
[ -n "${LOG_FILE:-}"      ] && CMD+=(--log              "$LOG_FILE")
[ -n "${EXTRA_ARGS:-}"    ] && CMD+=(--extra-ffmpeg-args "$EXTRA_ARGS")

echo "Running: ${CMD[*]}"
echo ""
exec "${CMD[@]}"
