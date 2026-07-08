# Song → Piano

Turns a YouTube link into a piano arrangement: an audible piano rendition
(wav) plus playable, downloadable sheet music (MusicXML/MIDI, rendered
interactively in the browser).

## How it works

```
YouTube URL
   │  yt-dlp
   ▼
full mix (wav)
   │  Demucs (--two-stems vocals)
   ▼
instrumental stem ("no_vocals")
   │  basic-pitch (Spotify's polyphonic transcription model)
   ▼
raw MIDI transcription
   │  music21: quantize rhythm, split into treble/bass staves by pitch
   ▼
two-staff piano score
   ├─ FluidSynth → piano_rendition.wav   (what you hear)
   └─ music21   → sheet_music.musicxml  (what you read, rendered client-side
                                          with OpenSheetMusicDisplay)
```

Nothing here does "sheet music lookup" — it's a real transcription pipeline,
which means:
- **It's not perfect.** Polyphonic transcription from a full instrumental mix
  is a hard, unsolved problem. Expect a good approximation, not a
  publisher-quality transcription — dense arrangements, guitar solos, and
  heavily produced tracks will transcribe worse than a simple piano/vocal
  original.
- **It takes real time and compute** (30 seconds to several minutes per song,
  more without a GPU), because it's running two ML models per request.

## Project layout

```
backend/
  app/
    main.py       FastAPI routes
    pipeline.py   the actual processing pipeline (steps above)
    jobs.py       in-memory job tracking + thread pool
    config.py     paths, soundfont location, quantization settings
  requirements.txt
  Dockerfile
frontend/
  index.html      single-page UI (no build step needed)
```

## Running it locally

1. **System dependencies** (the Python packages need these underneath):
   ```bash
   # macOS
   brew install ffmpeg fluid-synth
   # Debian/Ubuntu
   sudo apt-get install ffmpeg fluidsynth fluid-soundfont-gm
   ```
   On Debian/Ubuntu the soundfont lands at
   `/usr/share/sounds/sf2/FluidR3_GM.sf2` (matches the default in
   `config.py`). On macOS, download a free GM soundfont (search
   "FluidR3_GM.sf2") and set `PT_SOUNDFONT_PATH` to wherever you put it.

2. **Python environment:**
   ```bash
   cd backend
   python3 -m venv venv && source venv/bin/activate
   pip install -r requirements.txt
   ```
   Note: `basic-pitch` pulls in TensorFlow and `demucs` pulls in PyTorch —
   this is a multi-GB install and will take a while the first time.

3. **Run the API:**
   ```bash
   uvicorn app.main:app --reload --port 8000
   ```

4. **Serve the frontend** (it's static, any web server works):
   ```bash
   cd ../frontend
   python3 -m http.server 5500
   ```
   Open http://localhost:5500. The frontend auto-targets
   `http://localhost:8000` when running on localhost.

## Deploying it for others to use

A few things to decide before you put this in front of real users:

- **Compute.** `demucs` and `basic-pitch` run meaningfully faster on a GPU
  but work fine on CPU for short clips. A single always-on CPU box (e.g. a
  4 vCPU / 8GB instance) can handle a modest trickle of requests serially;
  for real concurrency, put a GPU worker behind a queue.
- **Move from the in-memory job store to a real queue.** `jobs.py` uses an
  in-process `ThreadPoolExecutor`, which is fine for one server process but
  won't survive a restart or scale past one instance. Swap it for
  Celery/RQ + Redis, keeping `pipeline.run_pipeline(job_id)` as the task body
  — it doesn't know or care how it's invoked.
- **Storage.** Right now output files live in `config.DATA_DIR` on local
  disk with a rough retention window. For a multi-instance deployment, write
  outputs to S3/GCS instead of local disk.
- **Rate-limit and cap duration.** `config.MAX_DURATION_SECONDS` already caps
  video length (default 10 min) so one request can't tie up a worker
  indefinitely — tune it, and add per-IP rate limiting in front of `/api/jobs`.
- **Containerized deploy:** the included `Dockerfile` builds the backend with
  all system dependencies. Any container host works (Fly.io, Render, a
  plain VPS with Docker, ECS, etc.); just serve `frontend/index.html` from
  a static host (Netlify, Vercel, S3+CloudFront, or the same box via nginx)
  and set `window.API_BASE` in the page (or edit the constant in
  `index.html`) to your backend's URL.

## A note on rights

This tool downloads audio from YouTube and produces a derivative arrangement
and transcription of it. Copyright rules around this vary by jurisdiction and
by whether use is personal or public-facing, and YouTube's own terms of
service restrict downloading video/audio outside their app. If you're
deploying this for other people to use, it's worth working out with a lawyer
(not me) what license terms, takedown process, and usage restrictions make
sense — this README won't cover that for you.

## Extending it

- **Different transcription target:** `separate_stems` currently keeps
  "everything but vocals." For a cappella-to-piano covers, you'd instead want
  to transcribe the *vocal* stem's melody and harmonize it — a different
  (harder) task.
  as-is.
- **Difficulty levels:** `arrange_for_piano` is a good place to add a
  "simplify" pass (drop grace notes, thin out dense chords) for a beginner
  arrangement mode.
- **PDF export:** if you have MuseScore installed on the server, you can
  point music21's environment at it
  (`music21.environment.UserSettings()['musescoreDirectPNGPath']`) and call
  `score.write('musicxml.pdf')` for a printable PDF instead of/alongside the
  browser-rendered MusicXML.
