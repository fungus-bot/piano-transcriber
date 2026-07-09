"""
Central configuration for the piano transcription service.
Override any of these with environment variables in production.
"""
import os
from pathlib import Path

# Where per-job working files (audio, midi, xml, etc.) live.
DATA_DIR = Path(os.environ.get("PT_DATA_DIR", "/tmp/piano-transcriber-jobs"))
DATA_DIR.mkdir(parents=True, exist_ok=True)

COOKIES_PATH = os.environ.get("YT_COOKIES_PATH", "/etc/secrets/cookies.txt")

# Path to a General MIDI soundfont used to render MIDI -> audible piano audio.
# FluidR3_GM.sf2 is a common free choice (~140MB). Download once at build/deploy
# time (see README) and point this at it.
SOUNDFONT_PATH = os.environ.get("PT_SOUNDFONT_PATH", "/usr/share/sounds/sf2/FluidR3_GM.sf2")

# Pitch (MIDI note number) used to split transcribed notes between the
# treble (right hand) and bass (left hand) staves. 60 = middle C.
HAND_SPLIT_PITCH = int(os.environ.get("PT_HAND_SPLIT_PITCH", "60"))

# Smallest rhythmic subdivision used when quantizing transcribed notes,
# expressed as a fraction of a quarter note (0.25 = sixteenth notes).
QUANTIZE_UNIT = float(os.environ.get("PT_QUANTIZE_UNIT", "0.25"))

# Max source video length we'll process, to keep jobs bounded on shared infra.
MAX_DURATION_SECONDS = int(os.environ.get("PT_MAX_DURATION_SECONDS", "600"))  # 10 min

# How long finished job files are kept on disk before cleanup (seconds).
JOB_RETENTION_SECONDS = int(os.environ.get("PT_JOB_RETENTION_SECONDS", str(60 * 60 * 6)))
