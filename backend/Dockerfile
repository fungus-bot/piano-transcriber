FROM python:3.11-slim

# System dependencies:
#   ffmpeg     - audio extraction/conversion (yt-dlp, demucs)
#   fluidsynth - renders MIDI to audio
#   fluid-soundfont-gm - a free General MIDI soundfont (includes acoustic piano)
#   libsndfile1, libgomp1 - required by demucs/torchaudio
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    fluidsynth \
    fluid-soundfont-gm \
    libsndfile1 \
    libgomp1 \
    git \
    && rm -rf /var/lib/apt/lists/*

# fluid-soundfont-gm installs to this path on Debian/Ubuntu
ENV PT_SOUNDFONT_PATH=/usr/share/sounds/sf2/FluidR3_GM.sf2

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
