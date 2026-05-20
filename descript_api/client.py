import os
import logging
from typing import Any, Optional

import requests
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from .exceptions import (
    DescriptAPIError,
    DescriptAuthError,
    DescriptRateLimitError,
)

log = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://api.descript.com"
DEFAULT_TIMEOUT = 60


class DescriptClient:
    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout: int = DEFAULT_TIMEOUT,
    ):
        key = api_key or os.environ.get("DESCRIPT_API_KEY")
        if not key:
            raise DescriptAuthError(
                401, "DESCRIPT_API_KEY not set (env var or constructor arg)"
            )
        self.api_key = key
        self.base_url = (
            base_url or os.environ.get("DESCRIPT_API_BASE_URL") or DEFAULT_BASE_URL
        ).rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Authorization": f"Bearer {self.api_key}",
                "Accept": "application/json",
                "User-Agent": "buildx-api/0.1 (+descript-integration)",
            }
        )

    @retry(
        retry=retry_if_exception_type(
            (DescriptRateLimitError, requests.ConnectionError, requests.Timeout)
        ),
        wait=wait_exponential(multiplier=2, min=2, max=30),
        stop=stop_after_attempt(5),
        reraise=True,
    )
    def request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[dict] = None,
        json: Optional[dict] = None,
        data: Optional[Any] = None,
        files: Optional[dict] = None,
        extra_headers: Optional[dict] = None,
    ) -> Any:
        url = f"{self.base_url}{path}"
        headers = dict(self.session.headers)
        if extra_headers:
            headers.update(extra_headers)
        resp = self.session.request(
            method,
            url,
            params=params,
            json=json,
            data=data,
            files=files,
            headers=headers,
            timeout=self.timeout,
        )
        return self._handle(resp)

    @staticmethod
    def _handle(resp: requests.Response) -> Any:
        if resp.status_code == 401 or resp.status_code == 403:
            raise DescriptAuthError(resp.status_code, "Auth failed", _safe_body(resp))
        if resp.status_code == 429:
            raise DescriptRateLimitError(429, "Rate limited", _safe_body(resp))
        if resp.status_code >= 400:
            raise DescriptAPIError(
                resp.status_code, resp.reason or "Error", _safe_body(resp)
            )
        if not resp.content:
            return None
        ctype = resp.headers.get("Content-Type", "")
        if "application/json" in ctype:
            return resp.json()
        return resp.content

    def get(self, path: str, **kw):
        return self.request("GET", path, **kw)

    def post(self, path: str, **kw):
        return self.request("POST", path, **kw)

    def put(self, path: str, **kw):
        return self.request("PUT", path, **kw)

    def delete(self, path: str, **kw):
        return self.request("DELETE", path, **kw)


def _safe_body(resp: requests.Response):
    try:
        return resp.json()
    except Exception:
        return resp.text[:500] if resp.text else None
