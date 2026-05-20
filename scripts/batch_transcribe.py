"""
Batch transcribe every media file in an input directory and write JSON
transcripts to an output directory. Designed to be run by cron / GitHub Actions.

Usage:
    python scripts/batch_transcribe.py --input ./data --output ./out
"""

import argparse
import json
import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from descript_api import DescriptClient, DescriptAPIError
from descript_api.transcription import TranscriptionAPI

MEDIA_EXTS = {".mp3", ".mp4", ".wav", ".m4a", ".mov", ".flac", ".aac"}

log = logging.getLogger("batch_transcribe")


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--input", default="./data", help="Directory of media files")
    p.add_argument(
        "--output",
        default=os.environ.get("OUTPUT_DIR", "./out"),
        help="Where to write transcript JSON",
    )
    p.add_argument("--language", default="en")
    return p.parse_args()


def main() -> int:
    load_dotenv()
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    args = parse_args()

    in_dir = Path(args.input)
    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)

    if not in_dir.exists():
        log.warning("Input dir %s does not exist; nothing to do", in_dir)
        return 0

    files = sorted(
        f for f in in_dir.iterdir() if f.is_file() and f.suffix.lower() in MEDIA_EXTS
    )
    if not files:
        log.info("No media files found in %s", in_dir)
        return 0

    client = DescriptClient()
    api = TranscriptionAPI(client)

    failures = 0
    for f in files:
        out_path = out_dir / f"{f.stem}.json"
        if out_path.exists():
            log.info("Skipping %s (transcript already exists)", f.name)
            continue
        log.info("Transcribing %s", f.name)
        try:
            transcript = api.transcribe_file(str(f), language=args.language)
            out_path.write_text(json.dumps(transcript, indent=2))
            log.info("Wrote %s", out_path)
        except DescriptAPIError as e:
            failures += 1
            log.error("Failed on %s: %s", f.name, e)

    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
