import re

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, field_validator

from . import pipeline
from .jobs import job_store

app = FastAPI(title="Piano Transcriber API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://piano-transcriber-1.onrender.com",  # replace with your real frontend URL
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


YOUTUBE_URL_RE = re.compile(
    r"^(https?://)?(www\.)?(youtube\.com/watch\?v=|youtu\.be/)[\w-]+"
)


class CreateJobRequest(BaseModel):
    youtube_url: str

    @field_validator("youtube_url")
    @classmethod
    def validate_youtube_url(cls, v: str) -> str:
        if not YOUTUBE_URL_RE.match(v.strip()):
            raise ValueError("That doesn't look like a valid YouTube URL.")
        return v.strip()


@app.post("/api/jobs")
def create_job(req: CreateJobRequest):
    job = job_store.create(req.youtube_url)
    job_store.submit(job.id, pipeline.run_pipeline)
    return {"job_id": job.id, "status": job.status}


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str):
    job = job_store.get(job_id)
    if job is None:
        raise HTTPException(404, "Job not found")
    return {
        "job_id": job.id,
        "status": job.status,
        "progress": job.progress,
        "message": job.message,
        "error": job.error,
    }


def _job_file_response(job_id: str, attr: str, filename: str, media_type: str):
    job = job_store.get(job_id)
    if job is None:
        raise HTTPException(404, "Job not found")
    path = getattr(job, attr, None)
    if not path:
        raise HTTPException(409, "File not ready yet")
    return FileResponse(path, filename=filename, media_type=media_type)


@app.get("/api/jobs/{job_id}/midi")
def get_midi(job_id: str):
    return _job_file_response(job_id, "midi_path", "piano_arrangement.mid", "audio/midi")


@app.get("/api/jobs/{job_id}/audio")
def get_audio(job_id: str):
    return _job_file_response(job_id, "piano_audio_path", "piano_rendition.wav", "audio/wav")


@app.get("/api/jobs/{job_id}/musicxml")
def get_musicxml(job_id: str):
    return _job_file_response(
        job_id, "musicxml_path", "sheet_music.musicxml", "application/vnd.recordare.musicxml+xml"
    )


@app.get("/api/health")
def health():
    return {"ok": True}
