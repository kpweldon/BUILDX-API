"""
ONE-TIME local helper to mint a Google Drive OAuth refresh token.

Prerequisites (done in your Google Cloud Console, ~5 min):
  1. https://console.cloud.google.com -> create a project (or use existing)
  2. APIs & Services -> Library -> enable "Google Drive API"
  3. APIs & Services -> OAuth consent screen
       - User Type: External
       - Add yourself (kevinw.buildx@gmail.com) as a Test user
       - Scopes: add "https://www.googleapis.com/auth/drive.file"
  4. APIs & Services -> Credentials -> Create credentials -> OAuth client ID
       - Application type: Desktop app
       - Download the JSON, save it as client_secret.json next to this script

Then run, locally (NOT in CI, since it opens a browser):
    pip install -r requirements.txt
    python scripts/setup_drive_auth.py

A browser tab opens, you grant access, the script prints a JSON blob.
Copy that blob and paste it as the value of the GOOGLE_OAUTH_CREDS secret
in GitHub: Settings -> Secrets and variables -> Actions -> New secret.

Also create a folder in your Google Drive (e.g. "BUILDX YouTube") and
copy its ID from the URL:
    https://drive.google.com/drive/folders/<THIS_IS_THE_ID>
Set that as the DRIVE_FOLDER_ID GitHub secret.
"""

import json
import sys
from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/drive.file"]


def main() -> int:
    here = Path(__file__).resolve().parent
    candidates = [
        here / "client_secret.json",
        here.parent / "client_secret.json",
        Path.cwd() / "client_secret.json",
    ]
    secret_path = next((p for p in candidates if p.exists()), None)
    if secret_path is None:
        print(
            "client_secret.json not found. Download it from Google Cloud Console "
            "(OAuth client ID -> Desktop app) and put it in the repo root or scripts/."
        )
        return 1

    flow = InstalledAppFlow.from_client_secrets_file(str(secret_path), SCOPES)
    creds = flow.run_local_server(port=0, prompt="consent", access_type="offline")

    if not creds.refresh_token:
        print(
            "No refresh_token returned. Re-run after removing this app from your "
            "Google Account permissions, OR ensure prompt=consent in the OAuth flow."
        )
        return 1

    blob = {
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
        "refresh_token": creds.refresh_token,
        "token_uri": creds.token_uri,
    }
    print("\n=== COPY EVERYTHING BELOW INTO THE GOOGLE_OAUTH_CREDS GitHub secret ===\n")
    print(json.dumps(blob, indent=2))
    print("\n=== END ===\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
