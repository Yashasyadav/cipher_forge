from __future__ import annotations

import logging
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone

from .folder_wipe_service import FolderWipeService
from .models import FolderWipeJobStatusResponse, FolderWipeRequest


@dataclass
class FolderWipeJobRecord:
    job_id: str
    path: str
    method: str
    status: str
    progress: float = 0.0
    total_files: int = 0
    processed_files: int = 0
    deleted_files: int = 0
    failed_files: int = 0
    current_file: str | None = None
    start_time: datetime | None = None
    end_time: datetime | None = None
    last_message: str | None = None
    error: str | None = None
    lock: threading.Lock = field(default_factory=threading.Lock)


class FolderWipeManager:
    """Asynchronous manager for folder wipe jobs with live progress state."""

    def __init__(self, folder_wipe_service: FolderWipeService, max_workers: int = 2) -> None:
        self.folder_wipe_service = folder_wipe_service
        self.logger = logging.getLogger("wipe_engine_service.folder_wipe_manager")
        self._lock = threading.RLock()
        self._jobs: dict[str, FolderWipeJobRecord] = {}
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="folder-wipe-job")

    def start_wipe(self, payload: FolderWipeRequest) -> FolderWipeJobStatusResponse:
        # Validate early so bad paths fail immediately.
        self.folder_wipe_service.validate_folder_path(payload.path)
        method = (payload.method or self.folder_wipe_service.default_method).strip()

        job_id = f"folder_job_{uuid.uuid4().hex[:12]}"
        job = FolderWipeJobRecord(
            job_id=job_id,
            path=payload.path,
            method=method,
            status="queued",
            last_message="Folder wipe queued. Waiting for available worker.",
        )
        with self._lock:
            self._jobs[job_id] = job

        self._executor.submit(self._run_folder_wipe, job_id)
        self.logger.info("Folder wipe job queued", extra={"event": "folder_wipe_queued", "job_id": job_id, "path": payload.path})
        return self._to_response(job)

    def get_status(self, job_id: str) -> FolderWipeJobStatusResponse | None:
        with self._lock:
            job = self._jobs.get(job_id)
        if not job:
            return None
        return self._to_response(job)

    def _run_folder_wipe(self, job_id: str) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
        if not job:
            return

        with job.lock:
            job.status = "running"
            job.start_time = datetime.now(timezone.utc)
            job.last_message = "Folder wipe started."

        self.logger.info("Folder wipe job started", extra={"event": "folder_wipe_started", "job_id": job.job_id, "path": job.path})

        def on_progress(progress_payload: dict[str, object]) -> None:
            with job.lock:
                job.progress = float(progress_payload.get("progress", job.progress) or 0.0)
                job.total_files = int(progress_payload.get("total_files", job.total_files) or 0)
                job.processed_files = int(progress_payload.get("processed_files", job.processed_files) or 0)
                job.deleted_files = int(progress_payload.get("deleted_files", job.deleted_files) or 0)
                job.failed_files = int(progress_payload.get("failed_files", job.failed_files) or 0)
                job.current_file = self._to_optional_str(progress_payload.get("current_file"))
                job.last_message = self._to_optional_str(progress_payload.get("last_message")) or job.last_message

        try:
            result = self.folder_wipe_service.wipe_folder(job.path, job.method, progress_callback=on_progress)
            with job.lock:
                job.total_files = int(result.get("total_files", job.total_files) or 0)
                job.processed_files = int(result.get("processed_files", job.processed_files) or 0)
                job.deleted_files = int(result.get("deleted_files", job.deleted_files) or 0)
                job.failed_files = int(result.get("failed_files", job.failed_files) or 0)
                job.progress = 100.0
                job.end_time = datetime.now(timezone.utc)
                if job.failed_files > 0 or str(result.get("status", "")).lower() == "failed":
                    job.status = "failed"
                else:
                    job.status = "completed"
                job.last_message = self._to_optional_str(result.get("last_message")) or "Folder wipe finished."
                job.current_file = None

            self.logger.info(
                "Folder wipe job finished",
                extra={
                    "event": "folder_wipe_finished",
                    "job_id": job.job_id,
                    "path": job.path,
                    "status": job.status,
                    "deleted_files": job.deleted_files,
                    "failed_files": job.failed_files,
                },
            )
        except Exception as exc:
            with job.lock:
                job.status = "failed"
                job.end_time = datetime.now(timezone.utc)
                job.error = str(exc)
                job.last_message = f"Folder wipe failed: {exc}"
                job.current_file = None
            self.logger.exception(
                "Folder wipe job failed",
                extra={"event": "folder_wipe_failed", "job_id": job.job_id, "path": job.path},
            )

    @staticmethod
    def _to_optional_str(value: object) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    @staticmethod
    def _to_response(job: FolderWipeJobRecord) -> FolderWipeJobStatusResponse:
        with job.lock:
            return FolderWipeJobStatusResponse(
                job_id=job.job_id,
                path=job.path,
                method=job.method,
                status=job.status,
                progress=round(job.progress, 2),
                total_files=job.total_files,
                processed_files=job.processed_files,
                deleted_files=job.deleted_files,
                failed_files=job.failed_files,
                current_file=job.current_file,
                start_time=job.start_time,
                end_time=job.end_time,
                last_message=job.last_message,
                error=job.error,
            )
