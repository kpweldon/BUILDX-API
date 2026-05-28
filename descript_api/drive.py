"""
Google Drive uploads using an OAuth refresh token (the only auth flow that
works against a personal Gmail account, because consumer Drive doesn't grant
service accounts any storage quota).

Credentials shape (JSON) — produced by scripts/setup_drive_auth.py:

    {
        "client_id": "...",
        "client_secret": "...",
        "refresh_token": "...",
        "token_uri": "https://oauth2.googleapis.com/token"
    }

In CI, paste that JSON blob into the GOOGLE_OAUTH_CREDS secret.
"""

import json
import logging
import mimetypes
import os
from pathlib import Path
from typing import Optional

from google.auth.transport.requests import Request as GoogleRequest
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

log = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/drive.file"]


def load_creds_from_env() -> Optional[Credentials]:
    raw = os.environ.get("GOOGLE_OAUTH_CREDS")
    if not raw:
        return None
    data = json.loads(raw)
    creds = Credentials(
        token=None,
        refresh_token=data["refresh_token"],
        client_id=data["client_id"],
        client_secret=data["client_secret"],
        token_uri=data.get("token_uri", "https://oauth2.googleapis.com/token"),
        scopes=SCOPES,
    )
    creds.refresh(GoogleRequest())
    return creds


class DriveUploader:
    def __init__(self, root_folder_id: str, creds: Credentials):
        self.root_folder_id = root_folder_id
        self.service = build("drive", "v3", credentials=creds, cache_discovery=False)
        self._folder_cache: dict[tuple[str, str], str] = {}

    def ensure_subfolder(self, parent_id: str, name: str) -> str:
        key = (parent_id, name)
        if key in self._folder_cache:
            return self._folder_cache[key]
        q = (
            f"name = '{name}' and "
            f"'{parent_id}' in parents and "
            "mimeType = 'application/vnd.google-apps.folder' and "
            "trashed = false"
        )
        resp = self.service.files().list(q=q, fields="files(id, name)").execute()
        files = resp.get("files", [])
        if files:
            fid = files[0]["id"]
        else:
            meta = {
                "name": name,
                "mimeType": "application/vnd.google-apps.folder",
                "parents": [parent_id],
            }
            fid = self.service.files().create(body=meta, fields="id").execute()["id"]
        self._folder_cache[key] = fid
        return fid

    def upload_file(self, local_path: Path, parent_id: str) -> str:
        mime, _ = mimetypes.guess_type(str(local_path))
        media = MediaFileUpload(str(local_path), mimetype=mime or "application/octet-stream", resumable=True)
        meta = {"name": local_path.name, "parents": [parent_id]}
        # Skip if a file with the same name already exists in the target folder.
        q = (
            f"name = '{local_path.name}' and "
            f"'{parent_id}' in parents and trashed = false"
        )
        existing = self.service.files().list(q=q, fields="files(id, name)").execute().get("files", [])
        if existing:
            log.info("Drive: %s already present, skipping", local_path.name)
            return existing[0]["id"]
        log.info("Drive: uploading %s (%d bytes)", local_path.name, local_path.stat().st_size)
        created = (
            self.service.files()
            .create(body=meta, media_body=media, fields="id")
            .execute()
        )
        return created["id"]

    def upload_bucket(self, local_dir: Path, bucket_name: str) -> int:
        if not local_dir.exists():
            return 0
        bucket_id = self.ensure_subfolder(self.root_folder_id, bucket_name)
        count = 0
        for f in sorted(local_dir.iterdir()):
            if not f.is_file():
                continue
            try:
                self.upload_file(f, bucket_id)
                count += 1
            except Exception as e:  # noqa: BLE001
                log.error("Drive upload failed for %s: %s", f.name, e)
        return count


def maybe_get_uploader() -> Optional[DriveUploader]:
    folder_id = os.environ.get("DRIVE_FOLDER_ID")
    if not folder_id:
        return None
    creds = load_creds_from_env()
    if creds is None:
        log.warning("DRIVE_FOLDER_ID set but GOOGLE_OAUTH_CREDS missing; skipping Drive upload")
        return None
    return DriveUploader(folder_id, creds)
