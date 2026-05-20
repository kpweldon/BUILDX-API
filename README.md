# BUILDX-API — Descript integration

Python scaffolding for talking to the Descript API, plus a nightly GitHub
Actions workflow that pulls fresh YouTube content (long-form >2min and
Shorts ≤60s, kept in separate buckets) and batch-transcribes it through
Descript.

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

4. **Add YouTube channels to monitor**
   Edit `config/channels.txt` and add channel URLs or @handles, one per line.

5. **Run the nightly job locally**
   ```bash
   # Ingest YouTube + transcribe everything
   python scripts/ingest_youtube.py

   # Or just download, skip transcription
   python scripts/ingest_youtube.py --no-transcribe

   # Or transcribe a folder of local media files
   python scripts/batch_transcribe.py --input ./data --output ./out
   ```

## Repo layout

```
config/channels.txt   YouTube channels the nightly job watches
descript_api/         Python client + per-feature modules
  client.py           Auth, retries, request plumbing
  transcription.py    Upload / start / poll / fetch transcript
  youtube_ingest.py   yt-dlp wrapper: list channel, filter by duration, download
  exceptions.py
scripts/
  ingest_youtube.py   Nightly: pull YouTube -> bucket -> transcribe
  batch_transcribe.py Transcribe any local folder of media files
.github/workflows/
  nightly-transcribe.yml   Cron job (07:00 UTC daily)
data/                 (gitignored) downloaded media, split into long_form/ + shorts/
data/.state/          (gitignored) seen-video-id cache so reruns are incremental
out/                  (gitignored) JSON transcripts, mirrored long_form/ + shorts/
```

## How the YouTube pipeline works

For each channel in `config/channels.txt`:
1. `yt-dlp --flat-playlist` lists the latest videos (default 10).
2. Each video is filtered by duration:
   - `> 120s` → `data/long_form/` (transcribed into `out/long_form/`)
   - `≤ 60s` (or `/shorts/` URL) → `data/shorts/` (→ `out/shorts/`)
   - `60–120s` → skipped (ambiguous "long" but under your 2-minute bar)
3. Already-downloaded video IDs are remembered in `data/.state/seen.json`
   so reruns only fetch new uploads.
4. Audio-only (`m4a`) is pulled to keep storage and transcription cost down.

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
