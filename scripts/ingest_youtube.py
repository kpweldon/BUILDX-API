"""
Pull recent videos from channels listed in config/channels.txt,
sort into data/long_form (>2min) and data/shorts (<=60s), and (optionally)
transcribe each via the Descript API.

Usage:
    python scripts/ingest_youtube.py                  # ingest + transcribe
    python scripts/ingest_youtube.py --no-transcribe  # download only
"""

import argparse
import json
import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from descript_api import DescriptClient, DescriptAPIError
from descript_api.drive import maybe_get_uploader
from descript_api.transcription import TranscriptionAPI
from descript_api.youtube_ingest import ingest_channels, read_channels

log = logging.getLogger("ingest_youtube")


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--channels-file", default="config/channels.txt")
    p.add_argument("--data-root", default="./data")
    p.add_argument("--out-root", default=os.environ.get("OUTPUT_DIR", "./out"))
    p.add_argument("--state-file", default="./data/.state/seen.json")
    p.add_argument("--per-channel-limit", type=int, default=10)
    p.add_argument("--no-transcribe", action="store_true")
    p.add_argument("--language", default="en")
    return p.parse_args()


def transcribe_bucket(api: TranscriptionAPI, bucket_dir: Path, out_dir: Path, language: str) -> int:
    if not bucket_dir.exists():
        return 0
    out_dir.mkdir(parents=True, exist_ok=True)
    failures = 0
    for media in sorted(bucket_dir.iterdir()):
        if not media.is_file():
            continue
        out_path = out_dir / f"{media.stem}.json"
        if out_path.exists():
            continue
        log.info("Transcribing %s -> %s", media.name, out_path)
        try:
            transcript = api.transcribe_file(str(media), language=language)
            out_path.write_text(json.dumps(transcript, indent=2))
        except DescriptAPIError as e:
            failures += 1
            log.error("Transcription failed for %s: %s", media.name, e)
    return failures


def main() -> int:
    load_dotenv()
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    args = parse_args()

    channels = read_channels(Path(args.channels_file))
    if not channels:
        log.warning("No channels listed in %s. Add channel URLs/handles and rerun.", args.channels_file)
        return 0

    data_root = Path(args.data_root)
    summary = ingest_channels(
        channels=channels,
        data_root=data_root,
        state_path=Path(args.state_file),
        per_channel_limit=args.per_channel_limit,
    )
    log.info(
        "Ingest done: %d long-form, %d shorts (skipped %d seen, %d in duration gap)",
        summary["downloaded_long_form"],
        summary["downloaded_shorts"],
        summary["skipped_already_seen"],
        summary["skipped_duration_gap"],
    )

    if args.no_transcribe:
        _maybe_upload_to_drive(data_root, Path(args.out_root))
        return 0

    client = DescriptClient()
    api = TranscriptionAPI(client)
    out_root = Path(args.out_root)
    failures = 0
    failures += transcribe_bucket(api, data_root / "long_form", out_root / "long_form", args.language)
    failures += transcribe_bucket(api, data_root / "shorts", out_root / "shorts", args.language)

    _maybe_upload_to_drive(data_root, out_root)
    return 1 if failures else 0


def _maybe_upload_to_drive(data_root: Path, out_root: Path) -> None:
    uploader = maybe_get_uploader()
    if uploader is None:
        log.info("Drive upload skipped (DRIVE_FOLDER_ID / GOOGLE_OAUTH_CREDS not set)")
        return
    # Upload videos and transcripts into mirrored Drive subfolders.
    log.info("Uploading media + transcripts to Google Drive")
    uploader.upload_bucket(data_root / "long_form", "long_form")
    uploader.upload_bucket(data_root / "shorts", "shorts")
    uploader.upload_bucket(out_root / "long_form", "long_form")
    uploader.upload_bucket(out_root / "shorts", "shorts")


if __name__ == "__main__":
    sys.exit(main())
