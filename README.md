# BUILDX-API — Descript integration

Python scaffolding for talking to the Descript API, plus a nightly GitHub
Actions workflow that batch-transcribes media files.

## Setup

1. **Get a Descript API key**
   - Descript dashboard → workspace/account settings → API / Developers → generate token.

2. **Local dev**
   ```bash
   python -m venv .venv && source .venv/bin/activate
   pip install -r requirements.txt
   cp .env.example .env       # then edit .env with your key
   ```

3. **GitHub Actions secret**
   - Repo → Settings → Secrets and variables → Actions → New secret:
     - `DESCRIPT_API_KEY` (required)
     - Optional repo variable `DESCRIPT_API_BASE_URL` if you need to override.

4. **Run a one-off batch locally**
   ```bash
   mkdir -p data && cp ~/Recordings/*.mp3 data/
   python scripts/batch_transcribe.py --input ./data --output ./out
   ```

## Repo layout

```
descript_api/        Python client + per-feature modules
  client.py          Auth, retries, request plumbing
  transcription.py   Upload / start / poll / fetch transcript
  exceptions.py
scripts/
  batch_transcribe.py  CLI entrypoint used by the nightly workflow
.github/workflows/
  nightly-transcribe.yml   Cron job (07:00 UTC daily)
```

## What this scaffold gives you

- Authenticated HTTP client with retry/backoff for 429s and network blips
- Pluggable per-feature modules (transcription today; add overdub, exports later)
- A CLI script suitable for cron / GitHub Actions
- A nightly workflow that uploads transcripts as a workflow artifact

## What still needs confirming against Descript's docs

Inside `descript_api/transcription.py` the constants `UPLOAD_PATH`,
`TRANSCRIBE_PATH`, and `JOB_PATH` plus the request/response field names
(`id`, `asset_id`, `status`, `transcript`) are best-guess defaults. Once you
have your key and can pull up the Descript API reference, those are the
only spots that need adjusting — the surrounding flow (upload → start →
poll → fetch) is the standard pattern.

## Adding more automations

Each Descript feature gets its own module that takes a `DescriptClient`:

```python
# descript_api/overdub.py
class OverdubAPI:
    def __init__(self, client): self.client = client
    def synthesize(self, voice_id, text): ...
```

Then a script in `scripts/` for the actual job, and (optionally) a workflow
in `.github/workflows/` if you want it on a schedule.
