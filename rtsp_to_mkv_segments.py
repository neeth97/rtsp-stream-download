#!/usr/bin/env python3
"""
rtsp_to_mkv_segments.py
=======================
Records an RTSP camera stream to time-stamped, fixed-length MKV segment files
using ffmpeg.

Key behaviours
--------------
* Splits the recording into equal-duration segments (default 10 minutes each).
* Each segment filename embeds the wall-clock start time so files sort
  chronologically and can be located by timestamp at a glance.
* If ffmpeg crashes or the camera reboots, the script automatically restarts
  ffmpeg after a configurable delay — no manual intervention needed.
* Stops cleanly on Ctrl+C (SIGINT) or systemd SIGTERM, finalising the current
  segment before exiting.
* Enforces an optional maximum total recording duration (default 4 hours) so
  the script does not run indefinitely when left unattended.

Dependencies
------------
* Python 3.9+
* ffmpeg  (sudo apt-get install -y ffmpeg)

Typical usage
-------------
    python3 rtsp_to_mkv_segments.py \\
        --rtsp "rtsp://admin:secret@192.168.1.10:554/stream1" \\
        --out  /data/recordings \\
        --segment 600 \\
        --tcp \\
        --max-duration 14400

See README.md for full setup and deployment instructions.
"""

import argparse
import os
import signal
import subprocess
import sys
import time
from datetime import datetime, timedelta


# ---------------------------------------------------------------------------
# ffmpeg command builder
# ---------------------------------------------------------------------------

def build_ffmpeg_cmd(
    rtsp_url: str,
    out_dir: str,
    segment_seconds: int,
    tcp: bool,
    extra: list[str],
) -> list[str]:
    """
    Construct the ffmpeg argument list for segmented RTSP recording.

    Parameters
    ----------
    rtsp_url:
        Full RTSP URL, optionally including credentials.
        Example: rtsp://admin:password@192.168.1.10:554/stream1
    out_dir:
        Directory where .mkv segment files will be written.
    segment_seconds:
        How many seconds of video each output file should contain.
    tcp:
        If True, tell ffmpeg to tunnel the RTP packets inside TCP instead of
        using UDP.  TCP is more reliable on NAT-heavy or lossy networks (e.g.
        4G modems, VPNs) but adds a small amount of latency.
    extra:
        Additional raw ffmpeg output-level arguments the caller wants to inject
        (e.g. ["-an"] to strip audio, or ["-vf", "scale=1280:720"]).
        These are inserted BEFORE the output filename so ffmpeg interprets them
        as output options — placing them after the filename would make ffmpeg
        treat them as a second output, which is almost never intended.

    Returns
    -------
    List of strings suitable for subprocess.Popen(cmd, ...).

    Output filename pattern
    -----------------------
    Files are named  anpr_YYYY-MM-DD_HH-MM-SS.mkv  where the timestamp
    reflects the wall-clock time at which each segment started.  ffmpeg's
    built-in strftime substitution (enabled by -strftime 1) handles this
    automatically — no Python-side renaming is required.
    """

    # The % tokens in this pattern are expanded by ffmpeg (not by Python's os
    # module) because -strftime 1 is passed below.
    out_pattern = os.path.join(out_dir, "anpr_%Y-%m-%d_%H-%M-%S.mkv")

    cmd = [
        "ffmpeg",

        # Suppress the multi-line version/build banner ffmpeg normally writes
        # to stderr on startup.  This keeps the log file readable.
        "-hide_banner",

        # Log level 'info' shows connection events, codec details, and segment
        # boundary messages without being excessively verbose.
        # Change to 'warning' for a quieter log or 'debug' for deep tracing.
        "-loglevel", "info",

        # Do NOT read from stdin.  Without this flag, ffmpeg opens /dev/stdin
        # and can block (or accidentally consume input) when running as a
        # background service or inside a terminal multiplexer.
        "-nostdin",
    ]

    if tcp:
        # Force the RTP/RTSP session to run over a single TCP connection.
        # Without this flag, ffmpeg uses UDP by default, which works well on
        # a local LAN but often fails when there is a NAT router, firewall, or
        # any middlebox between the recorder and the camera.
        cmd += ["-rtsp_transport", "tcp"]

    cmd += [
        # stimeout (socket timeout): maximum time in microseconds to wait for
        # the initial RTSP/TCP connection to be established.
        # 5 000 000 µs = 5 seconds.  If the camera does not respond within
        # this window, ffmpeg exits with a non-zero code and the script
        # restarts it after --restart-delay seconds.
        "-stimeout", "5000000",

        # ── Input ──────────────────────────────────────────────────────────
        "-i", rtsp_url,

        # ── Output options ─────────────────────────────────────────────────

        # Map ALL streams from input #0 to the output.
        # Some cameras send both a video stream and an audio stream; "-map 0"
        # ensures neither is silently discarded.  If you want video-only, add
        # --extra-ffmpeg-args "-an" to drop audio at mux time.
        "-map", "0",

        # Stream copy: pass the compressed bitstream from the camera straight
        # into the MKV container without decoding or re-encoding.
        # Benefits:
        #   • No CPU load from transcoding.
        #   • Original quality is preserved bit-for-bit.
        #   • Works even when the GPU/hardware decoder is unavailable.
        # Trade-off:
        #   • Cannot apply video filters (scaling, cropping) at this stage.
        "-c", "copy",

        # Use the 'segment' muxer to split the output into multiple files.
        "-f", "segment",

        # Close the current file and open a new one every N seconds.
        "-segment_time", str(segment_seconds),

        # Reset presentation timestamps to zero at the start of every segment.
        # Without this, the first frame of segment #5 (for example) would
        # carry a PTS of ~3000 s, causing some players to display a misleading
        # position indicator or refuse to seek to the beginning.
        "-reset_timestamps", "1",

        # Allow % strftime tokens in the output filename pattern so each file
        # gets the timestamp of when that segment started recording.
        "-strftime", "1",
    ]

    # Caller-supplied extra output-level options (e.g. "-an", "-vf scale=…").
    # These MUST come before the output filename; see docstring for explanation.
    cmd += extra

    # The output filename pattern is always the very last positional argument.
    cmd.append(out_pattern)

    return cmd


# ---------------------------------------------------------------------------
# Directory utility
# ---------------------------------------------------------------------------

def ensure_dir(path: str) -> None:
    """
    Create *path* and any missing intermediate directories.

    Uses exist_ok=True so calling this on an already-existing path is a no-op.
    Silently does nothing when *path* is an empty string (which happens when
    os.path.dirname() is called on a bare filename like "recorder.log").
    """
    if path:
        os.makedirs(path, exist_ok=True)


# ---------------------------------------------------------------------------
# Process-group termination helper
# ---------------------------------------------------------------------------

def _kill_process_group(proc: subprocess.Popen, logf) -> None:
    """
    Gracefully terminate the process group that *proc* leads, then force-kill
    it if it does not exit within 3 seconds.

    Why process groups?
    -------------------
    We launch ffmpeg with preexec_fn=os.setsid, which places it in a new
    session and makes it the process-group leader of a brand-new group whose
    PGID equals proc.pid.  If ffmpeg later spawns child processes (e.g. for
    complex filter graphs), those children inherit the same PGID.

    Sending SIGTERM only to proc.pid would orphan those children.  Using
    os.killpg(pgid, sig) delivers the signal to every process in the group,
    ensuring a complete clean-up.

    We call os.getpgid(proc.pid) rather than using proc.pid directly so that
    a ProcessLookupError (process already dead) is caught before we attempt
    the kill, avoiding an unhandled exception in the shutdown path.
    """
    # Retrieve the process-group ID; raises ProcessLookupError if gone already.
    try:
        pgid = os.getpgid(proc.pid)
    except ProcessLookupError:
        # ffmpeg already exited on its own — nothing to clean up.
        return

    # ── Step 1: polite request to stop ──────────────────────────────────────
    # SIGTERM lets ffmpeg finalise (flush buffers, write the moov atom in the
    # last segment) before it exits.  This is important for MKV integrity.
    try:
        os.killpg(pgid, signal.SIGTERM)
        logf.write(f"--- Sent SIGTERM to process group {pgid} ---\n")
    except ProcessLookupError:
        return  # Already gone, nothing more to do

    # ── Step 2: wait up to 3 seconds for a graceful exit ────────────────────
    deadline = time.monotonic() + 3.0
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            # Process exited cleanly after SIGTERM — we are done.
            return
        time.sleep(0.2)

    # ── Step 3: force kill if still running ─────────────────────────────────
    # SIGKILL cannot be caught or ignored; the kernel terminates immediately.
    try:
        os.killpg(pgid, signal.SIGKILL)
        logf.write(f"--- Sent SIGKILL to process group {pgid} (did not exit after SIGTERM) ---\n")
    except ProcessLookupError:
        pass  # Exited between our check and the kill — that is fine.


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def main() -> None:
    # ── Argument parsing ─────────────────────────────────────────────────────
    p = argparse.ArgumentParser(
        description=(
            "Record an RTSP camera stream to fixed-length MKV segments using "
            "ffmpeg.  Automatically restarts on failure and stops cleanly on "
            "SIGINT / SIGTERM or after --max-duration seconds."
        ),
        # Print default values next to every argument in --help output.
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    p.add_argument(
        "--rtsp",
        required=True,
        metavar="URL",
        help=(
            "RTSP source URL.  Embed credentials directly if the camera "
            "requires authentication: rtsp://user:password@ip:port/path"
        ),
    )
    p.add_argument(
        "--out",
        default="./recordings",
        metavar="DIR",
        help="Directory where MKV segment files will be written.",
    )
    p.add_argument(
        "--segment",
        type=int,
        default=600,
        metavar="SECONDS",
        help=(
            "Duration of each MKV segment in seconds.  "
            "600 = 10 minutes (default), 3600 = 1 hour."
        ),
    )
    p.add_argument(
        "--tcp",
        action="store_true",
        help=(
            "Force RTSP transport over TCP instead of UDP.  "
            "Recommended when the camera is behind NAT or on an unreliable link."
        ),
    )
    p.add_argument(
        "--restart-delay",
        type=int,
        default=5,
        metavar="SECONDS",
        help=(
            "How long to wait before relaunching ffmpeg after an unexpected "
            "exit.  Increase this if the camera needs time to reboot."
        ),
    )
    p.add_argument(
        "--max-restarts",
        type=int,
        default=0,
        metavar="N",
        help=(
            "Stop permanently after ffmpeg has been restarted N times.  "
            "0 = retry indefinitely (default)."
        ),
    )
    p.add_argument(
        "--max-duration",
        type=int,
        default=14400,
        metavar="SECONDS",
        help=(
            "Maximum total recording time across all ffmpeg restarts, in "
            "seconds.  The script stops (and kills ffmpeg) once this wall-clock "
            "duration has elapsed since the script was launched.  "
            "0 = no limit.  Default is 14400 s (4 hours)."
        ),
    )
    p.add_argument(
        "--log",
        default="./ffmpeg_recorder.log",
        metavar="FILE",
        help=(
            "Path to the log file where ffmpeg's stdout/stderr output is "
            "appended.  The parent directory is created automatically if needed."
        ),
    )
    p.add_argument(
        "--extra-ffmpeg-args",
        default="",
        metavar="ARGS",
        help=(
            "Additional ffmpeg output-level arguments as a single quoted "
            "string, e.g. \"-an\" to strip audio or \"-vf scale=1280:720\" "
            "to downscale.  These are inserted before the output filename."
        ),
    )

    args = p.parse_args()

    # ── Validate arguments ───────────────────────────────────────────────────

    if args.segment <= 0:
        p.error("--segment must be a positive integer.")

    if args.restart_delay < 0:
        p.error("--restart-delay must be >= 0.")

    if args.max_restarts < 0:
        p.error("--max-restarts must be >= 0.")

    if args.max_duration < 0:
        p.error("--max-duration must be >= 0.")

    # ── Directory / file setup ───────────────────────────────────────────────

    # Create the recordings directory (and any missing parents) before ffmpeg
    # tries to open the first output file.
    ensure_dir(args.out)

    # Create the log file's parent directory.
    # os.path.abspath resolves relative paths so os.path.dirname is never "".
    abs_log = os.path.abspath(args.log)
    ensure_dir(os.path.dirname(abs_log))

    # ── Parse extra ffmpeg args ──────────────────────────────────────────────

    # Split the user's string on whitespace into a proper list.
    # An empty or whitespace-only string yields an empty list (no extra args).
    extra: list[str] = (
        args.extra_ffmpeg_args.strip().split()
        if args.extra_ffmpeg_args.strip()
        else []
    )

    # Build the complete ffmpeg command once; it never changes between restarts.
    cmd = build_ffmpeg_cmd(args.rtsp, args.out, args.segment, args.tcp, extra)

    # ── Signal handling ──────────────────────────────────────────────────────

    # `stop` acts as a cross-thread flag.  Python signal handlers execute on
    # the main thread between bytecodes, so reading/writing a plain bool is
    # atomic enough for our purposes — no threading.Event or lock is needed.
    stop = False

    def handle_sig(sig, frame):
        """Set the stop flag and print a notice when SIGINT/SIGTERM arrives."""
        nonlocal stop
        stop = True
        # Use a simple print; avoid complex operations inside a signal handler.
        print(f"\n[recorder] Received signal {sig}. Stopping after current ffmpeg exits …")

    signal.signal(signal.SIGINT, handle_sig)   # Ctrl+C in a terminal
    signal.signal(signal.SIGTERM, handle_sig)  # systemd / kill <pid>

    # ── Startup banner ───────────────────────────────────────────────────────

    # Record the monotonic start time BEFORE any I/O so the duration
    # measurement is not skewed by slow disk or network operations.
    session_start = time.monotonic()

    abs_out = os.path.abspath(args.out)
    max_duration = args.max_duration  # local alias for brevity

    print("[recorder] ──────────────────────────────────────────────────")
    print(f"[recorder] Output directory  : {abs_out}")
    print(f"[recorder] Log file          : {abs_log}")
    print(f"[recorder] Segment length    : {args.segment} s  "
          f"({timedelta(seconds=args.segment)})")

    if max_duration:
        deadline_dt = datetime.now() + timedelta(seconds=max_duration)
        print(f"[recorder] Max duration      : {max_duration} s  "
              f"(stops around {deadline_dt.strftime('%Y-%m-%d %H:%M:%S')})")
    else:
        print("[recorder] Max duration      : unlimited")

    print(f"[recorder] Max restarts      : "
          f"{'unlimited' if not args.max_restarts else args.max_restarts}")
    print(f"[recorder] Restart delay     : {args.restart_delay} s")
    print(f"[recorder] FFmpeg command    : {' '.join(cmd)}")
    print("[recorder] ──────────────────────────────────────────────────")
    print("[recorder] Recording started. Press Ctrl+C to stop.")

    restarts = 0  # counts how many times ffmpeg has been (re-)launched

    # ── Main loop ────────────────────────────────────────────────────────────

    # Open the log file in append mode with line buffering (buffering=1).
    # Line buffering means each line is flushed to disk immediately after the
    # newline character, so log entries are visible in real time and are not
    # lost if the process is killed unexpectedly.
    with open(abs_log, "a", buffering=1) as logf:
        logf.write(
            f"\n=== Recorder session started at {datetime.now().isoformat()} ===\n"
        )
        logf.write("CMD: " + " ".join(cmd) + "\n")

        while not stop:

            # ── Duration guard (pre-launch) ──────────────────────────────────
            # Check the elapsed time before launching a new ffmpeg process so
            # we do not start a fresh recording in the final moments of the
            # allowed window.
            elapsed = time.monotonic() - session_start
            if max_duration and elapsed >= max_duration:
                print(
                    f"[recorder] Max duration reached "
                    f"({elapsed:.0f} s ≥ {max_duration} s). Not launching ffmpeg."
                )
                logf.write(
                    f"--- Max duration reached ({elapsed:.0f} s) before launch "
                    f"at {datetime.now().isoformat()} ---\n"
                )
                break

            # ── Launch ffmpeg ────────────────────────────────────────────────
            launch_time = datetime.now().isoformat()
            logf.write(
                f"\n--- Launching ffmpeg (launch #{restarts}) at {launch_time} ---\n"
            )
            print(f"[recorder] Launching ffmpeg (launch #{restarts}) …")

            try:
                proc = subprocess.Popen(
                    cmd,
                    # Redirect both stdout and stderr to the log file so all
                    # ffmpeg output (progress lines, error messages, codec info)
                    # is captured in one place.
                    stdout=logf,
                    stderr=logf,
                    # Place ffmpeg in its own session/process-group so we can
                    # send signals to the entire group (ffmpeg + any children)
                    # via os.killpg rather than only to the top-level PID.
                    preexec_fn=os.setsid,
                )
            except FileNotFoundError:
                # The 'ffmpeg' binary is not on PATH at all.
                print(
                    "[recorder] ERROR: 'ffmpeg' not found on PATH.\n"
                    "           Install it:  sudo apt-get install -y ffmpeg"
                )
                sys.exit(1)
            except PermissionError as exc:
                # The ffmpeg binary exists but is not executable.
                print(
                    f"[recorder] ERROR: Cannot execute ffmpeg ({exc}).\n"
                    f"           Check file permissions:  ls -la $(which ffmpeg)"
                )
                sys.exit(1)

            # ── Inner poll loop ──────────────────────────────────────────────
            # We poll every second rather than calling proc.wait() so that:
            #   (a) the stop flag set by a signal handler is noticed quickly,
            #   (b) we can enforce the max-duration deadline while ffmpeg runs.
            while proc.poll() is None and not stop:
                time.sleep(1)

                # Re-check the duration deadline mid-run.
                # This ensures we stop ffmpeg even when the process is in the
                # middle of recording a long segment.
                elapsed = time.monotonic() - session_start
                if max_duration and elapsed >= max_duration:
                    print(
                        f"[recorder] Max duration reached while recording "
                        f"({elapsed:.0f} s ≥ {max_duration} s). Stopping …"
                    )
                    logf.write(
                        f"--- Max duration reached ({elapsed:.0f} s) mid-run "
                        f"at {datetime.now().isoformat()} ---\n"
                    )
                    stop = True  # exit the inner loop → fall through to kill

            # ── Handle graceful shutdown ─────────────────────────────────────
            if stop:
                # The stop flag was set by a signal or the duration deadline.
                # Kill ffmpeg cleanly so the last segment is properly closed.
                _kill_process_group(proc, logf)
                logf.write(
                    f"--- Session stopped at {datetime.now().isoformat()} ---\n"
                )
                # Do NOT restart; exit the outer while loop.
                break

            # ── Handle unexpected ffmpeg exit ────────────────────────────────
            rc = proc.returncode
            logf.write(
                f"--- ffmpeg exited with code {rc} at {datetime.now().isoformat()} ---\n"
            )
            print(f"[recorder] ffmpeg exited with code {rc}. See log: {abs_log}")

            # Exit code 0 typically means ffmpeg received a clean EOF on the
            # input (e.g. the camera closed the RTSP session) or was sent
            # SIGTERM by an external process.  We log it clearly but still
            # restart because continuous recording is the goal.
            if rc == 0:
                print("[recorder] Note: ffmpeg exited cleanly (code 0); restarting anyway.")

            # ── Restart accounting ───────────────────────────────────────────
            restarts += 1
            if args.max_restarts and restarts >= args.max_restarts:
                print(
                    f"[recorder] Reached max-restarts limit ({args.max_restarts}). Exiting."
                )
                logf.write(
                    f"--- Max restarts ({args.max_restarts}) reached. "
                    f"Stopping at {datetime.now().isoformat()} ---\n"
                )
                break

            # ── Interruptible restart delay ──────────────────────────────────
            # Sleep in 1-second ticks so a SIGINT/SIGTERM during the wait
            # causes the script to exit immediately rather than after the full
            # restart-delay window.
            print(f"[recorder] Restarting in {args.restart_delay} s …")
            for _ in range(args.restart_delay):
                if stop:
                    break
                time.sleep(1)

        # end while not stop

        logf.write(
            f"=== Recorder session ended at {datetime.now().isoformat()} ===\n"
        )

    # ── Session summary ──────────────────────────────────────────────────────
    total_seconds = int(time.monotonic() - session_start)
    print(
        f"[recorder] Done. Total run time: {timedelta(seconds=total_seconds)}  "
        f"| ffmpeg launches: {restarts + 1}"
    )


# ---------------------------------------------------------------------------
# Script entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    main()
