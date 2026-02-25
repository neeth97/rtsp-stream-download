#!/usr/bin/env bash
# =============================================================================
# run_recorder.sh — Launches two simultaneous RTSP recorders (ANPR Cam 1 & 2).
# Usage: bash run_recorder.sh
# =============================================================================

# -----------------------------------------------------------------------------
# CAMERA 1 — ANPR Cam 1
# -----------------------------------------------------------------------------
CAM1_URL="rtsp://username:password@40.10.18.28:554/avstream/channel=1/stream=0.sdp"
CAM1_OUT="./data_recordings/ANPR Cam 1"
CAM1_LOG="./anpr_cam1.log"

# -----------------------------------------------------------------------------
# CAMERA 2 — ANPR Cam 2
# -----------------------------------------------------------------------------
CAM2_URL="rtsp://username:password@40.10.18.29:554/avstream/channel=1/stream=0.sdp"
CAM2_OUT="./data_recordings/ANPR Cam 2"
CAM2_LOG="./anpr_cam2.log"

# -----------------------------------------------------------------------------
# SHARED SETTINGS — apply to both cameras
# Uncomment and edit any line below to override the default value
# -----------------------------------------------------------------------------

# Length of each recorded segment in seconds (600 = 10 minutes)
SEGMENT=600

# Force RTSP transport over TCP (recommended for NAT, VPN, or unreliable links)
# Set to "--tcp" to enable, or leave commented out to use UDP
# TCP="--tcp"

# Seconds to wait before restarting ffmpeg after an unexpected exit
RESTART_DELAY=5

# Stop permanently after ffmpeg has been restarted N times (0 = retry forever)
MAX_RESTARTS=0

# Maximum total recording time in seconds (0 = no limit)
MAX_DURATION=0

# Extra ffmpeg output-level arguments (e.g. "-an" to strip audio)
# EXTRA_ARGS="-an"

# =============================================================================
# DO NOT EDIT BELOW THIS LINE
# =============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY="$SCRIPT_DIR/rtsp_to_mkv_segments.py"

# Build the argument list for one camera.
# $1 = RTSP URL  $2 = output directory  $3 = log file
_build_cmd() {
    local -a cmd=(python3 "$PY" --rtsp "$1" --out "$2" --log "$3")
    [ -n "${SEGMENT:-}"       ] && cmd+=(--segment          "$SEGMENT")
    [ -n "${TCP:-}"           ] && cmd+=("$TCP")
    [ -n "${RESTART_DELAY:-}" ] && cmd+=(--restart-delay    "$RESTART_DELAY")
    [ -n "${MAX_RESTARTS:-}"  ] && cmd+=(--max-restarts     "$MAX_RESTARTS")
    [ -n "${MAX_DURATION:-}"  ] && cmd+=(--max-duration     "$MAX_DURATION")
    [ -n "${EXTRA_ARGS:-}"    ] && cmd+=(--extra-ffmpeg-args "$EXTRA_ARGS")
    # Print each element NUL-separated so the caller can reconstruct the array
    printf '%s\0' "${cmd[@]}"
}

# Reconstruct arrays from NUL-separated output of _build_cmd
mapfile -d '' CMD1 < <(_build_cmd "$CAM1_URL" "$CAM1_OUT" "$CAM1_LOG")
mapfile -d '' CMD2 < <(_build_cmd "$CAM2_URL" "$CAM2_OUT" "$CAM2_LOG")

echo "[launcher] ─────────────────────────────────────────────────────────"
echo "[launcher] ANPR Cam 1 → ${CAM1_OUT}"
echo "[launcher]   cmd: ${CMD1[*]}"
echo "[launcher] ANPR Cam 2 → ${CAM2_OUT}"
echo "[launcher]   cmd: ${CMD2[*]}"
echo "[launcher] ─────────────────────────────────────────────────────────"
echo "[launcher] Starting both recorders. Press Ctrl+C to stop."
echo ""

# Launch both recorders in the background
"${CMD1[@]}" &
PID1=$!
"${CMD2[@]}" &
PID2=$!

echo "[launcher] ANPR Cam 1 PID : $PID1  (log: $CAM1_LOG)"
echo "[launcher] ANPR Cam 2 PID : $PID2  (log: $CAM2_LOG)"

# Forward SIGINT / SIGTERM to both child processes so Ctrl+C stops them cleanly
_cleanup() {
    echo ""
    echo "[launcher] Signal received — stopping both recorders …"
    kill "$PID1" "$PID2" 2>/dev/null
}
trap _cleanup INT TERM

# Wait for both recorders to finish
wait "$PID1" "$PID2"
echo "[launcher] Both recorders have exited."
