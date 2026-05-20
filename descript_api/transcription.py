"""
Transcription operations against the Descript API.

NOTE: Exact endpoint paths and payload shapes must be confirmed against the
current Descript API reference. The methods below are organized around the
typical flow (upload -> kick off transcription -> poll -> fetch result) so
filling in the correct paths is a localized change.
"""

import time
from dataclasses import dataclass
from typing import Optional

from .client import DescriptClient
from .exceptions import DescriptAPIError


@dataclass
class TranscriptionJob:
    job_id: str
    status: str
    transcript: Optional[dict] = None


class TranscriptionAPI:
    def __init__(self, client: DescriptClient):
        self.client = client

    # TODO: confirm path against Descript API docs
    UPLOAD_PATH = "/v1/uploads"
    TRANSCRIBE_PATH = "/v1/transcriptions"
    JOB_PATH = "/v1/transcriptions/{job_id}"

    def upload_media(self, file_path: str) -> str:
        """Upload a local media file, return an upload/asset id."""
        with open(file_path, "rb") as fh:
            files = {"file": (file_path.split("/")[-1], fh)}
            resp = self.client.post(self.UPLOAD_PATH, files=files)
        if not isinstance(resp, dict) or "id" not in resp:
            raise DescriptAPIError(0, f"Unexpected upload response: {resp!r}")
        return resp["id"]

    def start_transcription(self, asset_id: str, language: str = "en") -> str:
        resp = self.client.post(
            self.TRANSCRIBE_PATH,
            json={"asset_id": asset_id, "language": language},
        )
        if not isinstance(resp, dict) or "id" not in resp:
            raise DescriptAPIError(0, f"Unexpected start response: {resp!r}")
        return resp["id"]

    def get_job(self, job_id: str) -> TranscriptionJob:
        resp = self.client.get(self.JOB_PATH.format(job_id=job_id))
        return TranscriptionJob(
            job_id=resp["id"],
            status=resp.get("status", "unknown"),
            transcript=resp.get("transcript"),
        )

    def wait_for_completion(
        self,
        job_id: str,
        poll_interval: int = 10,
        timeout_seconds: int = 60 * 30,
    ) -> TranscriptionJob:
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            job = self.get_job(job_id)
            if job.status in ("completed", "succeeded", "done"):
                return job
            if job.status in ("failed", "error", "canceled"):
                raise DescriptAPIError(0, f"Transcription job {job_id} ended: {job.status}")
            time.sleep(poll_interval)
        raise DescriptAPIError(0, f"Transcription job {job_id} timed out")

    def transcribe_file(self, file_path: str, language: str = "en") -> dict:
        asset_id = self.upload_media(file_path)
        job_id = self.start_transcription(asset_id, language=language)
        job = self.wait_for_completion(job_id)
        return job.transcript or {}
