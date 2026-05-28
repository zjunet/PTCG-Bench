"""
Record a battle replay JSONL as a video by automating the frontend replay viewer.

Usage:
    # Single replay
    uv run scripts/record_replay.py seed_2.jsonl
    uv run scripts/record_replay.py seed_2.jsonl --output recordings/seed_2.mp4
    uv run scripts/record_replay.py seed_2.jsonl --speed 4
    uv run scripts/record_replay.py seed_2.jsonl --zoom 0.8
    uv run scripts/record_replay.py seed_2.jsonl --no-crop-replay-board
    uv run scripts/record_replay.py seed_2.jsonl --no-start-servers  # if servers already running

    # Batch: record all replays from an eval run
    uv run scripts/record_replay.py --from-run bench_data/runs/2026-04-20_...
    uv run scripts/record_replay.py --from-run bench_data/runs/2026-04-20_... --agent skillevolving:deepseek-chat

Output format is WebM (Playwright default); converted to MP4 automatically if ffmpeg is available.
"""

import argparse
import asyncio
import json
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path


def port_open(port: int) -> bool:
    for family, addr in ((socket.AF_INET, "127.0.0.1"), (socket.AF_INET6, "::1")):
        try:
            with socket.socket(family, socket.SOCK_STREAM) as s:
                s.settimeout(0.2)
                if s.connect_ex((addr, port)) == 0:
                    return True
        except OSError:
            pass
    return False


def wait_for_port(port: int, proc: subprocess.Popen, name: str, timeout: int = 30) -> bool:
    for _ in range(timeout * 2):
        if port_open(port):
            return True
        rc = proc.poll()
        if rc is not None:
            # Process already exited — safe to do a blocking read now (pipe is closed)
            stderr = proc.stderr.read().decode(errors="replace") if proc.stderr else ""
            print(f"[{name}] process exited unexpectedly (rc={rc})")
            if stderr.strip():
                print(f"[{name}] stderr:\n{stderr.strip()}")
            return False
        time.sleep(0.5)
    # Timed out but process is still alive — do NOT block on stderr read
    print(f"[{name}] timed out after {timeout}s waiting for port {port} (process is still running)")
    return False


def start_server(cmd: list[str], cwd: Path, name: str) -> subprocess.Popen:
    proc = subprocess.Popen(
        cmd,
        cwd=cwd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,  # capture stderr so we can show it on failure
    )
    print(f"[{name}] started (pid={proc.pid}): {' '.join(cmd)}")
    return proc


def even_down(value: int) -> int:
    return max(2, value - (value % 2))


async def add_styles(page, *style_blocks: str | None) -> None:
    styles = [style.strip() for style in style_blocks if style and style.strip()]
    if not styles:
        return
    await page.add_style_tag(content="\n".join(styles))
    await page.wait_for_timeout(300)


def compute_crop_filter(
    crop_box: dict[str, float], width: int, height: int, zoom: float
) -> str | None:
    if zoom <= 0:
        return None

    x = int(round(crop_box["x"] * zoom))
    y = int(round(crop_box["y"] * zoom))
    w = int(round(crop_box["width"] * zoom))
    h = int(round(crop_box["height"] * zoom))

    x = max(0, min(x, width - 2))
    y = max(0, min(y, height - 2))
    w = min(w, width - x)
    h = min(h, height - y)

    w = even_down(w)
    h = even_down(h)
    x = even_down(x)
    y = even_down(y)

    if x + w > width:
        x = max(0, width - w)
    if y + h > height:
        y = max(0, height - h)

    if w < 2 or h < 2:
        return None

    return f"crop={w}:{h}:{x}:{y}"


async def record(
    filename: str,
    output_path: Path,
    speed: float,
    width: int,
    height: int,
    zoom: float,
    crop_replay_board: bool,
    trim_padding_s: float,
    frontend_url: str,
    timeout_s: int,
) -> None:
    from playwright.async_api import async_playwright

    basename = Path(filename).name
    tmp_dir = output_path.parent / ".video_tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    crop_filter: str | None = None
    trim_start_s = 0.0

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={"width": width, "height": height},
            record_video_dir=str(tmp_dir),
            record_video_size={"width": width, "height": height},
        )
        page = await context.new_page()
        recording_started_at = time.monotonic()

        # ── Navigate to app ────────────────────────────────────────────────────
        print(f"  Opening {frontend_url} ...")
        await page.goto(frontend_url, wait_until="networkidle")
        await page.wait_for_timeout(500)

        await add_styles(
            page,
            f"html, body {{ zoom: {zoom}; }}" if zoom != 1.0 else None,
            """
            .grid.grid-cols-12.gap-3.flex-1.min-h-0 > div:last-child {
                display: none !important;
            }
            .grid.grid-cols-12.gap-3.flex-1.min-h-0 > div:first-child {
                grid-column: 1 / -1 !important;
            }
            """,
        )

        # ── Enter replay mode ──────────────────────────────────────────────────
        print("  Entering Replays view ...")
        replays_btn = page.get_by_text("Replays").first
        await replays_btn.wait_for(state="visible", timeout=10_000)
        await replays_btn.click()

        # Wait for the file list to finish loading (header appears after API call)
        print("  Waiting for Replay Library to load ...")
        try:
            await page.get_by_text("Replay Library").wait_for(state="visible", timeout=15_000)
        except Exception:
            raise RuntimeError("Replay Library did not appear")

        # ── Select the replay file ─────────────────────────────────────────────
        print(f"  Selecting '{basename}' ...")
        file_btn = page.get_by_text(basename, exact=True).first
        try:
            await file_btn.wait_for(state="visible", timeout=10_000)
        except Exception:
            raise RuntimeError(f"File '{basename}' not found in list")
        await file_btn.click()

        # Wait for replay to finish loading
        print("  Loading frames ...")
        await page.wait_for_timeout(2000)

        # ── Set playback speed ─────────────────────────────────────────────────
        # Speed buttons render as "0.25×", "0.5×", "1×", "2×", "4×"
        valid_speeds = {0.25, 0.5, 1.0, 2.0, 4.0}
        chosen = min(valid_speeds, key=lambda s: abs(s - speed))
        speed_label = f"{chosen:g}×"
        print(f"  Setting speed {speed_label} ...")
        try:
            speed_btn = page.get_by_text(speed_label, exact=True).first
            await speed_btn.wait_for(state="visible", timeout=5_000)
            await speed_btn.click()
            await page.wait_for_timeout(300)
        except Exception:
            print(f"  (could not set speed {speed_label}, using default)")

        # ── Start playback ─────────────────────────────────────────────────────
        print("  Starting playback ...")
        play_btn = page.locator('button[title="Play"]')
        await play_btn.wait_for(state="visible", timeout=10_000)
        await play_btn.click()
        trim_start_s = max(0.0, time.monotonic() - recording_started_at - trim_padding_s)

        await add_styles(
            page,
            """
            nav.fixed.top-0.inset-x-0.z-50.h-11 {
                display: none !important;
            }
            """,
            """
            button[title="Play"],
            button[title="Pause"] {
                display: none !important;
            }
            .sticky.bottom-0 {
                display: none !important;
            }
            """,
        )

        crop_box = None
        if crop_replay_board:
            crop_box = await page.evaluate(
                """
                () => {
                    const board = document.querySelector('[data-testid="replay-board"]');
                    if (!(board instanceof HTMLElement)) return null;
                    const rect = board.getBoundingClientRect();
                    return {
                        x: Math.max(0, rect.left),
                        y: Math.max(0, rect.top),
                        width: Math.max(0, rect.width),
                        height: Math.max(0, rect.height),
                    };
                }
                """
            )
        if crop_box is not None:
            crop_filter = compute_crop_filter(crop_box, width, height, zoom)
            if crop_filter:
                print(f"  Cropping output with filter: {crop_filter}")

        # ── Wait for replay to reach the final frame ──────────────────────────
        print(f"  Waiting for replay to finish (timeout={timeout_s}s) ...")
        await page.wait_for_function(
            """
            () => {
                const slider = document.querySelector('input[type="range"]');
                if (!(slider instanceof HTMLInputElement)) return false;
                const current = Number(slider.value);
                const maximum = Number(slider.max);
                return Number.isFinite(current) && Number.isFinite(maximum) && current >= maximum;
            }
            """,
            timeout=timeout_s * 1000,
        )

        # Brief pause so last frame is visible in video
        await page.wait_for_timeout(2000)

        # ── Capture video path before closing ─────────────────────────────────
        video_path = await page.video.path()
        print("  Closing browser ...")
        await context.close()
        await browser.close()

    # ── Move / convert video ───────────────────────────────────────────────────
    if not video_path or not Path(video_path).exists():
        print("ERROR: no video file was produced", file=sys.stderr)
        sys.exit(1)

    webm_out = output_path.with_suffix(".webm")
    shutil.move(video_path, webm_out)
    print(f"  WebM saved: {webm_out}")

    # Convert to MP4 if ffmpeg is available
    if shutil.which("ffmpeg"):
        mp4_out = output_path.with_suffix(".mp4")
        ffmpeg_cmd = [
            "ffmpeg",
            "-y",
        ]
        if trim_start_s > 0:
            ffmpeg_cmd.extend(["-ss", f"{trim_start_s:.3f}"])
        ffmpeg_cmd.extend(
            [
                "-i",
                str(webm_out),
            ]
        )
        if crop_filter:
            ffmpeg_cmd.extend(["-vf", crop_filter])
        ffmpeg_cmd.extend(
            [
                "-c:v",
                "libx264",
                "-crf",
                "20",
                "-preset",
                "fast",
                "-movflags",
                "+faststart",
                str(mp4_out),
            ]
        )
        result = subprocess.run(ffmpeg_cmd, capture_output=True)
        if result.returncode == 0:
            webm_out.unlink()
            print(f"  MP4 saved:  {mp4_out}")
        else:
            print(f"  ffmpeg failed — keeping WebM: {webm_out}")
            print(result.stderr.decode()[-500:], file=sys.stderr)
    else:
        print("  (ffmpeg not found — output is WebM; install ffmpeg to auto-convert)")

    # Clean up empty tmp dir
    try:
        tmp_dir.rmdir()
    except OSError:
        pass


# ---------------------------------------------------------------------------
# Batch mode: record all replays from an eval run directory
# ---------------------------------------------------------------------------


def _scan_run_replays(
    run_dir: Path, agent_filter: str | None = None
) -> list[tuple[Path, Path, str, str]]:
    """Scan ``run_dir/reflection_batches/`` for ``replay.jsonl`` files.

    Returns a list of ``(replay_path, output_mp4_path, agent_id, result)``
    tuples.  *result* comes from ``summary.json`` (``"win"`` / ``"loss"``
    / ``"draw"`` / ``"unknown"``).
    """
    batches_dir = run_dir / "reflection_batches"
    if not batches_dir.is_dir():
        return []

    entries: list[tuple[Path, Path, str, str]] = []
    for agent_dir in sorted(batches_dir.iterdir()):
        if not agent_dir.is_dir():
            continue
        if agent_filter and agent_dir.name != agent_filter:
            continue
        agent_id = agent_dir.name
        for batch_dir in sorted(agent_dir.iterdir()):
            if not batch_dir.is_dir():
                continue
            for battle_dir in sorted(batch_dir.iterdir()):
                if not battle_dir.is_dir():
                    continue
                replay_path = battle_dir / "replay.jsonl"
                if not replay_path.exists():
                    continue
                # Read result from summary.json
                summary_path = battle_dir / "summary.json"
                result = "unknown"
                if summary_path.exists():
                    try:
                        summary = json.loads(summary_path.read_text())
                        result = summary.get("result", "unknown")
                    except (json.JSONDecodeError, OSError):
                        pass
                # Output mirrors the source structure under run_dir/videos/
                video_dir = run_dir / "videos" / agent_id / batch_dir.name
                video_dir.mkdir(parents=True, exist_ok=True)
                output_path = video_dir / f"{battle_dir.name}.mp4"
                entries.append((replay_path, output_path, agent_id, result))

    return entries


def _start_servers(root: Path) -> list[subprocess.Popen]:
    """Start backend + frontend if not already running. Returns procs to clean up."""
    procs: list[subprocess.Popen] = []

    if not port_open(8000):
        print("[backend] Starting FastAPI ...")
        procs.append(
            start_server(
                ["uv", "run", "uvicorn", "main:app", "--port", "8000"],
                cwd=root / "backend",
                name="backend",
            )
        )
        if not wait_for_port(8000, procs[-1], "backend", timeout=30):
            raise RuntimeError("Backend did not start in time")
        print("[backend] ready")
    else:
        print("[backend] already running on :8000")

    if not port_open(5173):
        print("[frontend] Starting Vite dev server ...")
        procs.append(
            start_server(
                ["npm", "run", "dev"],
                cwd=root / "frontend",
                name="frontend",
            )
        )
        if not wait_for_port(5173, procs[-1], "frontend", timeout=40):
            raise RuntimeError("Frontend did not start in time")
        print("[frontend] ready")
    else:
        print("[frontend] already running on :5173")

    return procs


def batch_record(args: argparse.Namespace) -> None:
    """Batch-record all replays found in ``args.from_run``."""
    from tqdm import tqdm

    run_dir = Path(args.from_run).resolve()
    if not run_dir.is_dir():
        print(f"Error: {run_dir} is not a directory", file=sys.stderr)
        sys.exit(1)

    replays = _scan_run_replays(run_dir, agent_filter=args.agent)
    if not replays:
        print("No replay.jsonl files found in reflection_batches/")
        sys.exit(0)

    # Filter out already-recorded videos (resume support)
    pending = [(rp, op, aid, res) for rp, op, aid, res in replays if not op.exists()]
    skipped = len(replays) - len(pending)
    if skipped:
        print(f"Skipping {skipped} already-recorded video(s)")

    print(f"\nFound {len(pending)} replay(s) to record in {run_dir.name}")

    # Copy all replay JSONL files into backend/battle_log/ at once
    root = Path(__file__).parent.parent
    battle_log_dir = root / "backend" / "battle_log"
    battle_log_dir.mkdir(parents=True, exist_ok=True)

    # Track what we copied so we can clean up
    copied_names: list[str] = []
    for replay_path, _output_path, _agent_id, _result in pending:
        dest_name = replay_path.parent.name + ".jsonl"
        shutil.copy2(replay_path, battle_log_dir / dest_name)
        copied_names.append(dest_name)

    ensure_playwright_browsers()

    procs: list[subprocess.Popen] = []
    try:
        procs = _start_servers(root)

        succeeded: list[tuple[Path, str, str]] = []  # (output_path, agent_id, result)
        failed: list[tuple[Path, str]] = []  # (replay_path, error_msg)

        for replay_path, output_path, agent_id, result in tqdm(
            pending, desc="Recording", unit="video"
        ):
            dest_name = replay_path.parent.name + ".jsonl"
            try:
                asyncio.run(
                    record(
                        filename=dest_name,
                        output_path=output_path,
                        speed=args.speed,
                        width=args.width,
                        height=args.height,
                        zoom=args.zoom,
                        crop_replay_board=args.crop_replay_board,
                        trim_padding_s=args.trim_padding,
                        frontend_url=args.url,
                        timeout_s=args.timeout,
                    )
                )
                succeeded.append((output_path, agent_id, result))
            except Exception as exc:
                tqdm.write(f"  FAILED {dest_name}: {exc}")
                failed.append((replay_path, str(exc)))
                # Clean up partial output
                output_path.unlink(missing_ok=True)
                output_path.with_suffix(".webm").unlink(missing_ok=True)

        # ── Summary ──────────────────────────────────────────────────────────
        print()
        print("=" * 60)
        print(f"{'BATCH RECORDING SUMMARY':^60}")
        print("=" * 60)
        print(f"  Succeeded: {len(succeeded)}")
        print(f"  Failed:    {len(failed)}")

        if succeeded:
            # Aggregate win/loss/draw per agent
            stats: dict[str, dict[str, int]] = {}
            for _path, aid, res in succeeded:
                stats.setdefault(aid, {"win": 0, "loss": 0, "draw": 0, "unknown": 0})
                stats[aid][res] = stats[aid].get(res, 0) + 1

            for aid, counts in stats.items():
                wins = counts.get("win", 0)
                losses = counts.get("loss", 0)
                draws = counts.get("draw", 0)
                print(f"  {aid}: {wins}W {losses}L {draws}D")

        if failed:
            print("\n  Failed recordings:")
            for rp, msg in failed:
                print(f"    {rp.parent.name}: {msg}")

        print()
        print(f"  Output: {run_dir / 'videos'}")

    finally:
        # Clean up: remove copied files from battle_log/
        for name in copied_names:
            (battle_log_dir / name).unlink(missing_ok=True)
        for proc in procs:
            proc.terminate()
            proc.wait()


def ensure_playwright_browsers() -> None:
    """Install Chromium browser if not already present."""
    result = subprocess.run(
        [sys.executable, "-m", "playwright", "install", "chromium"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print("Warning: playwright install may have failed:", result.stderr[:300])


def main() -> None:
    parser = argparse.ArgumentParser(description="Record a battle replay as video")
    parser.add_argument("filename", nargs="?", help="Replay filename, e.g. seed_2.jsonl")
    parser.add_argument("--output", "-o", help="Output path (default: recordings/<stem>)")
    parser.add_argument(
        "--from-run",
        type=Path,
        default=None,
        metavar="RUN_DIR",
        help="Batch record all replays from an eval run directory",
    )
    parser.add_argument(
        "--agent",
        default=None,
        help="Filter by agent ID in batch mode (e.g. skillevolving:deepseek-chat)",
    )
    parser.add_argument(
        "--speed",
        "-s",
        type=float,
        default=2.0,
        help="Playback speed: 0.25 / 0.5 / 1 / 2 / 4 (default: 2)",
    )
    parser.add_argument("--width", type=int, default=1920, help="Viewport width (default: 1920)")
    parser.add_argument("--height", type=int, default=1400, help="Viewport height (default: 1400)")
    parser.add_argument(
        "--zoom",
        type=float,
        default=1.0,
        help="Page zoom factor applied before recording (default: 1.0)",
    )
    parser.add_argument(
        "--crop-replay-board",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Crop the output video to the ReplayBoard area only (default: enabled)",
    )
    parser.add_argument(
        "--trim-padding",
        type=float,
        default=0.4,
        help="Seconds of padding to keep before playback starts when trimming (default: 0.4)",
    )
    parser.add_argument("--url", default="http://localhost:5173", help="Frontend URL")
    parser.add_argument("--timeout", type=int, default=300, help="Max playback wait (seconds)")
    parser.add_argument(
        "--no-start-servers",
        action="store_true",
        help="Skip auto-starting backend/frontend servers",
    )
    args = parser.parse_args()

    # ── Batch mode ────────────────────────────────────────────────────────────
    if args.from_run:
        if args.filename:
            parser.error("Cannot use both FILENAME and --from-run")
        batch_record(args)
        return

    # ── Single-file mode ──────────────────────────────────────────────────────
    if not args.filename:
        parser.error("FILENAME is required (or use --from-run for batch mode)")

    root = Path(__file__).parent.parent
    basename = Path(args.filename).name
    stem = Path(basename).stem

    if args.output:
        output_path = Path(args.output).expanduser().resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
    else:
        rec_dir = root / "recordings"
        rec_dir.mkdir(exist_ok=True)
        output_path = rec_dir / stem

    # Ensure Playwright Chromium is installed
    ensure_playwright_browsers()

    procs: list[subprocess.Popen] = []
    try:
        if not args.no_start_servers:
            procs = _start_servers(root)

        print(f"\nRecording: {basename} → {output_path.with_suffix('.mp4')}")
        asyncio.run(
            record(
                filename=basename,
                output_path=output_path,
                speed=args.speed,
                width=args.width,
                height=args.height,
                zoom=args.zoom,
                crop_replay_board=args.crop_replay_board,
                trim_padding_s=args.trim_padding,
                frontend_url=args.url,
                timeout_s=args.timeout,
            )
        )
        print("\nDone.")

    finally:
        for proc in procs:
            proc.terminate()
            proc.wait()


if __name__ == "__main__":
    main()
