import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel

from desktop.downloader import download_video, get_video_info, validate_video_url


class DownloadRequest(BaseModel):
    url: str
    format: str
    quality: str | None = None
    start: str | None = None
    end: str | None = None


class DownloadManager:
    def __init__(self):
        self._lock = threading.Lock()
        self._jobs = []
        self._pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="download")

    def snapshot(self):
        with self._lock:
            return [job.copy() for job in self._jobs]

    def add(self, request, video_info):
        job = {
            "id": uuid.uuid4().hex,
            "title": video_info["title"],
            "url": request.url,
            "format": request.format.upper(),
            "status": "queued",
            "progress": 0,
            "speed": None,
            "eta": None,
            "filepath": None,
            "error": None,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        with self._lock:
            self._jobs.insert(0, job)
            self._jobs = self._jobs[:50]
        self._pool.submit(self._run, job["id"], request, video_info)
        return job

    def _update(self, job_id, **changes):
        with self._lock:
            job = next((item for item in self._jobs if item["id"] == job_id), None)
            if job:
                job.update(changes)

    def _run(self, job_id, request, video_info):
        self._update(job_id, status="downloading")

        def progress_hook(data):
            if data.get("status") == "downloading":
                total = data.get("total_bytes") or data.get("total_bytes_estimate")
                progress = int(data.get("downloaded_bytes", 0) * 100 / total) if total else 0
                self._update(
                    job_id,
                    progress=min(progress, 100),
                    speed=data.get("speed"),
                    eta=data.get("eta"),
                )
            elif data.get("status") == "finished":
                self._update(job_id, progress=100)

        try:
            filepath = download_video(request.model_dump(), video_info, progress_hook)
            self._update(job_id, status="completed", progress=100, filepath=filepath)
        except Exception as error:
            self._update(job_id, status="failed", error=str(error), speed=None, eta=None)


manager = DownloadManager()
app = FastAPI(title="LeonTV Downloader", docs_url=None, redoc_url=None)
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"^chrome-extension://[a-p]{32}$",
    allow_methods=["GET", "POST"],
    allow_headers=["content-type"],
)


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/info")
async def video_info(url: str):
    try:
        validate_video_url(url)
        return await run_in_threadpool(get_video_info, url)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except Exception as error:
        raise HTTPException(status_code=502, detail=f"Metadaten konnten nicht geladen werden: {error}") from error


@app.post("/api/download", status_code=202)
def start_download(request: DownloadRequest):
    try:
        validate_video_url(request.url)
        if request.format not in {"mp4", "mp3"}:
            raise ValueError("Das Ausgabeformat muss MP4 oder MP3 sein.")
        info = {"title": request.url}
        manager.add(request, info)
        return {"id": manager.snapshot()[0]["id"], "status": "queued"}
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@app.get("/api/status")
def download_status():
    jobs = manager.snapshot()
    return {
        "active": [job for job in jobs if job["status"] in {"queued", "downloading"}],
        "completed": [job for job in jobs if job["status"] == "completed"],
        "failed": [job for job in jobs if job["status"] == "failed"],
    }
