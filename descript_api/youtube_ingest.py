"""
Pull latest videos from a list of YouTube channels using yt-dlp, then
sort them into two buckets:

    long_form/  -> duration > LONG_FORM_MIN_SECONDS (default 120s)
    shorts/     -> duration <= SHORTS_MAX_SECONDS  (default 60s)

Videos in the gap (60s < d <= 120s) are skipped. Already-downloaded video
ids are tracked in a state file so reruns are incremental.
"""

import json
import logging
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

log = logging.getLogger(__name__)

SHORTS_MAX_SECONDS = 60
LONG_FORM_MIN_SECONDS = 120


@dataclass
class VideoEntry:
    video_id: str
    title: str
    duration: Optional[int]   # seconds; None if unknown
    url: str
    is_short: bool

    @property
    def bucket(self) -> Optional[str]:
        if self.duration is None:
            # Fall back to URL hint
            return "shorts" if self.is_short else None
        if self.is_short or self.duration <= SHORTS_MAX_SECONDS:
            return "shorts"
        if self.duration > LONG_FORM_MIN_SECONDS:
            return "long_form"
        return None


def read_channels(path: Path) -> list[str]:
    if not path.exists():
        return []
    out = []
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        out.append(line)
    return out


def _run_ytdlp_json(args: list[str]) -> list[dict]:
    """Run yt-dlp with -J / --dump-json and parse stdout as JSON lines."""
    log.debug("yt-dlp %s", " ".join(args))
    result = subprocess.run(
        ["yt-dlp", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        log.warning("yt-dlp exited %s: %s", result.returncode, result.stderr.strip())
    entries = []
    for line in result.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return entries


def list_recent_videos(channel: str, limit: int = 10) -> list[VideoEntry]:
    """List the channel's most recent videos as VideoEntry objects."""
    raw = _run_ytdlp_json(
        [
            "--flat-playlist",
            "--dump-json",
            "--playlist-end",
            str(limit),
            channel,
        ]
    )
    out: list[VideoEntry] = []
    for e in raw:
        vid = e.get("id")
        if not vid:
            continue
        url = e.get("url") or f"https://www.youtube.com/watch?v={vid}"
        is_short = "/shorts/" in url
        out.append(
            VideoEntry(
                video_id=vid,
                title=e.get("title", ""),
                duration=e.get("duration"),
                url=url,
                is_short=is_short,
            )
        )
    return out


def _load_seen(state_path: Path) -> set[str]:
    if not state_path.exists():
        return set()
    try:
        return set(json.loads(state_path.read_text()))
    except json.JSONDecodeError:
        return set()


def _save_seen(state_path: Path, seen: Iterable[str]) -> None:
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(sorted(seen), indent=2))


def download_video(entry: VideoEntry, out_dir: Path) -> Optional[Path]:
    """Download a single video's audio (m4a) into out_dir. Returns the file path."""
    out_dir.mkdir(parents=True, exist_ok=True)
    # We only need audio for transcription; m4a keeps size small.
    output_tmpl = str(out_dir / "%(id)s.%(ext)s")
    cmd = [
        "yt-dlp",
        "-f",
        "bestaudio[ext=m4a]/bestaudio",
        "-o",
        output_tmpl,
        "--no-progress",
        "--no-warnings",
        "--quiet",
        entry.url,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        log.error("yt-dlp download failed for %s: %s", entry.video_id, result.stderr.strip())
        return None
    # Find the produced file by id prefix
    for p in out_dir.iterdir():
        if p.stem == entry.video_id:
            return p
    return None


def ingest_channels(
    channels: list[str],
    data_root: Path,
    state_path: Path,
    per_channel_limit: int = 10,
) -> dict:
    """
    For each channel, list recent videos, filter into shorts/long_form,
    skip already-seen ids, download new ones, and update state.
    Returns a small summary dict.
    """
    seen = _load_seen(state_path)
    long_dir = data_root / "long_form"
    shorts_dir = data_root / "shorts"

    downloaded = {"long_form": [], "shorts": []}
    skipped_gap = 0
    skipped_seen = 0

    for ch in channels:
        log.info("Listing channel: %s", ch)
        try:
            videos = list_recent_videos(ch, limit=per_channel_limit)
        except Exception as e:  # noqa: BLE001
            log.error("Failed to list %s: %s", ch, e)
            continue

        for v in videos:
            if v.video_id in seen:
                skipped_seen += 1
                continue
            bucket = v.bucket
            if bucket is None:
                skipped_gap += 1
                log.info("Skipping %s (duration=%s, no bucket)", v.video_id, v.duration)
                seen.add(v.video_id)
                continue
            target = long_dir if bucket == "long_form" else shorts_dir
            log.info("Downloading %s [%s] %ss -> %s", v.video_id, bucket, v.duration, target)
            path = download_video(v, target)
            if path is not None:
                downloaded[bucket].append(str(path))
            seen.add(v.video_id)

    _save_seen(state_path, seen)
    summary = {
        "downloaded_long_form": len(downloaded["long_form"]),
        "downloaded_shorts": len(downloaded["shorts"]),
        "skipped_already_seen": skipped_seen,
        "skipped_duration_gap": skipped_gap,
        "long_form_paths": downloaded["long_form"],
        "shorts_paths": downloaded["shorts"],
    }
    log.info("Ingest summary: %s", {k: v for k, v in summary.items() if not k.endswith("_paths")})
    return summary
