"""
The actual audio -> piano sheet music pipeline.

Stages:
  1. download_audio      YouTube URL -> wav  (yt-dlp)
  2. separate_stems      full mix -> "no_vocals" stem  (Demucs)
  3. transcribe_to_midi  audio -> polyphonic MIDI  (Spotify basic-pitch)
  4. arrange_for_piano   raw MIDI -> two-staff piano MIDI/score (music21)
  5. render_piano_audio  piano MIDI -> audible wav  (FluidSynth)
  6. export_musicxml     piano score -> MusicXML (for OpenSheetMusicDisplay
                         in the browser, and as a downloadable file)

Each stage is a separate function so you can test/replace them independently
(e.g. swap basic-pitch for a different transcription model, or skip stem
separation for a cappella piano covers).
"""
import logging
import os
import shutil
from pathlib import Path

from . import config
from .jobs import job_store, JobStatus

logger = logging.getLogger(__name__)


class PipelineError(Exception):
    pass


def download_audio(youtube_url: str, out_dir: Path) -> Path:
    """Download best-quality audio from a YouTube URL as a wav file."""
    import yt_dlp

    out_template = str(out_dir / "source.%(ext)s")

    # Render's Secret Files are mounted read-only, but yt-dlp writes back
    # to the cookie file after use — so copy it to a writable tmp path first.
    cookies_path = config.COOKIES_PATH
    logger.info("Checking for cookies file at: %s (exists=%s)", cookies_path, os.path.exists(cookies_path))
    if cookies_path and os.path.exists(cookies_path):
        writable_cookies_path = "/tmp/cookies.txt"
        shutil.copyfile(cookies_path, writable_cookies_path)
        cookies_path = writable_cookies_path
    else:
        logger.warning("Cookies file not found at %s — YouTube requests may be blocked.", cookies_path)

    ydl_opts = {
        "format": "bestaudio/best",
        "outtmpl": out_template,
        "cookiefile": cookies_path,
        "postprocessors": [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "wav",
            "preferredquality": "0",
        }],
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(youtube_url, download=False)
        duration = info.get("duration") or 0
        if duration > config.MAX_DURATION_SECONDS:
            raise PipelineError(
                f"Video is {duration}s long; this service caps at "
                f"{config.MAX_DURATION_SECONDS}s to keep processing time reasonable."
            )
        ydl.download([youtube_url])

    wav_path = out_dir / "source.wav"
    if not wav_path.exists():
        raise PipelineError("Audio download finished but no wav file was produced.")
    return wav_path


def separate_stems(audio_path: Path, out_dir: Path) -> Path:
    """
    Run Demucs to split out vocals, keeping everything else ("no_vocals")
    as the transcription target. This matters because vocal formants and
    consonants badly confuse pitch-detection models; stripping vocals first
    gives a much cleaner transcription of the instrumental content.
    """
    import subprocess

    separated_root = out_dir / "separated"
    cmd = [
        "python", "-m", "demucs.separate",
        "--two-stems", "vocals",
        "-o", str(separated_root),
        str(audio_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise PipelineError(f"Demucs separation failed: {result.stderr[-2000:]}")

    # demucs writes to <out>/<model_name>/<track_name>/no_vocals.wav
    matches = list(separated_root.rglob("no_vocals.wav"))
    if not matches:
        raise PipelineError("Demucs did not produce a no_vocals stem.")
    return matches[0]


def transcribe_to_midi(audio_path: Path, out_dir: Path) -> Path:
    """Use Spotify's basic-pitch model to transcribe audio into MIDI."""
    from basic_pitch.inference import predict
    from basic_pitch import ICASSP_2022_MODEL_PATH

    model_output, midi_data, note_events = predict(str(audio_path), ICASSP_2022_MODEL_PATH)
    midi_path = out_dir / "raw_transcription.mid"
    midi_data.write(str(midi_path))
    return midi_path


def arrange_for_piano(midi_path: Path, out_dir: Path):
    """
    Turn the raw (often messy) polyphonic transcription into a proper
    two-staff piano arrangement:
      - quantize note timing to a sane rhythmic grid
      - split notes across a bass/treble staff by pitch so it reads like
        real piano sheet music instead of one dense line
      - set the instrument to Piano

    Returns a music21 Score object.
    """
    from music21 import converter, stream, instrument, clef, layout, meter

    score = converter.parse(str(midi_path))
    notes_and_chords = list(score.flatten().notes)

    treble = stream.Part()
    treble.insert(0, instrument.Piano())
    treble.insert(0, clef.TrebleClef())

    bass = stream.Part()
    bass.insert(0, clef.BassClef())

    for element in notes_and_chords:
        pitches = element.pitches if hasattr(element, "pitches") else [element.pitch]
        avg_midi = sum(p.midi for p in pitches) / len(pitches)
        target = treble if avg_midi >= config.HAND_SPLIT_PITCH else bass
        target.insert(element.offset, element)

    for part in (treble, bass):
        part.quantize(
            (1 / config.QUANTIZE_UNIT,),
            processOffsets=True,
            processDurations=True,
            inPlace=True,
        )

    piano_score = stream.Score()
    piano_score.insert(0, treble)
    piano_score.insert(0, bass)
    staff_group = layout.StaffGroup(
        [treble, bass], name="Piano", abbreviation="Pno.", symbol="brace"
    )
    piano_score.insert(0, staff_group)

    return piano_score


def render_piano_audio(piano_score, out_dir: Path) -> Path:
    """Render the arranged piano score to an audible wav via FluidSynth."""
    from midi2audio import FluidSynth

    midi_path = out_dir / "piano_arrangement.mid"
    piano_score.write("midi", fp=str(midi_path))

    if not os.path.exists(config.SOUNDFONT_PATH):
        raise PipelineError(
            f"Soundfont not found at {config.SOUNDFONT_PATH}. "
            "See README for how to install one."
        )

    wav_path = out_dir / "piano_rendition.wav"
    fs = FluidSynth(sound_font=config.SOUNDFONT_PATH)
    fs.midi_to_audio(str(midi_path), str(wav_path))
    return wav_path, midi_path


def export_musicxml(piano_score, out_dir: Path) -> Path:
    xml_path = out_dir / "sheet_music.musicxml"
    piano_score.write("musicxml", fp=str(xml_path))
    return xml_path


def run_pipeline(job_id: str):
    """Entry point run in the background thread pool by JobStore.submit."""
    job = job_store.get(job_id)
    if job is None:
        return

    out_dir = config.DATA_DIR / job_id
    out_dir.mkdir(parents=True, exist_ok=True)

    try:
        job_store.update(job_id, status=JobStatus.DOWNLOADING, progress=5,
                          message="Downloading audio from YouTube...")
        audio_path = download_audio(job.youtube_url, out_dir)

        job_store.update(job_id, status=JobStatus.SEPARATING, progress=25,
                          message="Separating vocals from instrumentation...")
        instrumental_path = separate_stems(audio_path, out_dir)

        job_store.update(job_id, status=JobStatus.TRANSCRIBING, progress=50,
                          message="Transcribing notes...")
        raw_midi_path = transcribe_to_midi(instrumental_path, out_dir)

        job_store.update(job_id, status=JobStatus.RENDERING, progress=70,
                          message="Arranging for piano...")
        piano_score = arrange_for_piano(raw_midi_path, out_dir)
        piano_wav_path, piano_midi_path = render_piano_audio(piano_score, out_dir)

        job_store.update(job_id, status=JobStatus.ENGRAVING, progress=90,
                          message="Engraving sheet music...")
        xml_path = export_musicxml(piano_score, out_dir)

        job_store.update(
            job_id,
            status=JobStatus.DONE,
            progress=100,
            message="Done!",
            midi_path=str(piano_midi_path),
            piano_audio_path=str(piano_wav_path),
            musicxml_path=str(xml_path),
        )
    except PipelineError as e:
        logger.warning("Pipeline error for job %s: %s", job_id, e)
        job_store.update(job_id, status=JobStatus.ERROR, error=str(e))
    except Exception as e:  # noqa: BLE001 - surface any failure to the client
        logger.exception("Unexpected failure for job %s", job_id)
        job_store.update(job_id, status=JobStatus.ERROR, error=f"Internal error: {e}")
    finally:
        # Best-effort cleanup of the largest intermediate files to save disk;
        # keep the final artifacts (midi/wav/musicxml) referenced above.
        for stray in ("source.wav", "separated"):
            p = out_dir / stray
            if p.is_dir():
                shutil.rmtree(p, ignore_errors=True)
            elif p.exists():
                p.unlink(missing_ok=True)
