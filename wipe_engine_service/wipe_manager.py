from __future__ import annotations

import logging
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone

from .certificate_generator import CertificateGenerator
from .device_detector import DeviceDetector
from .forensic_verifier import ForensicVerifier
from .models import CertificateMetadata, JobStatus, WipeJobResponse, WipeMethod, WipeRequest
from .wipe_executor import WipeExecutor


@dataclass
class JobRecord:
    job_id: str
    device: str
    device_serial_number: str
    device_type: str
    wipe_method: WipeMethod
    status: JobStatus
    progress: float
    start_time: datetime | None = None
    end_time: datetime | None = None
    certificate_id: str | None = None
    last_message: str | None = None
    error: str | None = None
    bytes_wiped: int = 0
    passes_completed: int = 0
    execution_seconds: float = 0.0
    lock: threading.Lock = field(default_factory=threading.Lock)


class WipeManager:
    """Thread-safe asynchronous wipe job manager."""

    def __init__(
        self,
        executor: WipeExecutor,
        detector: DeviceDetector,
        certificate_generator: CertificateGenerator,
        forensic_verifier: ForensicVerifier | None = None,
        max_workers: int = 4,
    ) -> None:
        self.executor = executor
        self.detector = detector
        self.certificate_generator = certificate_generator
        self.forensic_verifier = forensic_verifier or ForensicVerifier()
        self.logger = logging.getLogger("wipe_engine_service.wipe_manager")
        self._jobs: dict[str, JobRecord] = {}
        self._certificates: dict[str, CertificateMetadata] = {}
        self._lock = threading.RLock()
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="wipe-job")

    def start_wipe(self, payload: WipeRequest) -> WipeJobResponse:
        device_info = self._resolve_device(payload.device)
        job_id = f"job_{uuid.uuid4().hex[:12]}"
        job = JobRecord(
            job_id=job_id,
            device=device_info.device,
            device_serial_number=device_info.serial,
            device_type=device_info.type,
            wipe_method=payload.method,
            status=JobStatus.QUEUED,
            progress=0.0,
            last_message="Job queued.",
        )
        with self._lock:
            self._jobs[job_id] = job

        self._executor.submit(self._run_wipe_job, job_id, device_info.device, device_info.size_bytes)
        self.logger.info(
            "Wipe job queued",
            extra={
                "event": "wipe_job_queued",
                "job_id": job_id,
                "device": device_info.device,
                "wipe_method": payload.method.value,
            },
        )
        return self._to_response(job)

    def get_status(self, job_id: str) -> WipeJobResponse | None:
        with self._lock:
            job = self._jobs.get(job_id)
        if not job:
            return None
        return self._to_response(job)

    def get_certificate(self, certificate_id: str) -> CertificateMetadata | None:
        with self._lock:
            existing = self._certificates.get(certificate_id)
        if existing:
            return existing
        loaded = self.certificate_generator.load(certificate_id)
        if loaded:
            with self._lock:
                self._certificates[certificate_id] = loaded
        return loaded

    def get_certificate_by_job_id(self, job_id: str) -> CertificateMetadata | None:
        with self._lock:
            job = self._jobs.get(job_id)
            if not job or not job.certificate_id:
                return None
            certificate_id = job.certificate_id
            existing = self._certificates.get(certificate_id)
        if existing:
            return existing
        loaded = self.certificate_generator.load(certificate_id)
        if loaded:
            with self._lock:
                self._certificates[certificate_id] = loaded
        return loaded

    def _run_wipe_job(self, job_id: str, target_device: str, size_bytes: int) -> None:
        with self._lock:
            job = self._jobs[job_id]

        with job.lock:
            job.status = JobStatus.RUNNING
            job.start_time = datetime.now(timezone.utc)
            job.last_message = "Wipe started."
        self.logger.info(
            "Wipe job started",
            extra={"event": "wipe_job_started", "job_id": job.job_id, "device": target_device},
        )

        def on_progress(progress: float, message: str) -> None:
            with job.lock:
                job.progress = progress
                job.last_message = message
            self.logger.debug(
                "Wipe job progress updated",
                extra={
                    "event": "wipe_job_progress",
                    "job_id": job.job_id,
                    "progress": round(progress, 2),
                    "message": message,
                },
            )

        try:
            result = self.executor.wipe(
                target=target_device,
                method=job.wipe_method,
                size_hint=size_bytes,
                progress_callback=on_progress,
            )
            with job.lock:
                job.progress = 100.0
                job.status = JobStatus.COMPLETED
                job.end_time = result["end_time"]
                job.bytes_wiped = int(result["bytes_wiped"])
                job.passes_completed = int(result["passes_completed"])
                job.execution_seconds = float(result["execution_seconds"])
                job.last_message = "Wipe completed. Running forensic verification."
                certificate_id = str(uuid.uuid4())
                job.certificate_id = certificate_id

            forensic_result = self.forensic_verifier.verify(job.device)
            recovered_files = int(forensic_result.get("recovered_files", 0))
            verification_status = str(forensic_result.get("verification", "FAILED"))
            with job.lock:
                job.last_message = "Forensic verification complete. Generating certificate."

            self.logger.info(
                "Forensic verification complete",
                extra={
                    "event": "wipe_job_forensic_verification",
                    "job_id": job.job_id,
                    "device": job.device,
                    "recovered_files": recovered_files,
                    "verification_status": verification_status,
                },
            )

            with job.lock:
                certificate = self.certificate_generator.generate(
                    certificate_id=certificate_id,
                    job_id=job.job_id,
                    device=job.device,
                    device_serial_number=job.device_serial_number,
                    device_type=job.device_type,
                    wipe_method=job.wipe_method,
                    overwrite_passes=job.passes_completed,
                    timestamp=job.end_time,
                    verification_status=verification_status,
                    recovered_files=recovered_files,
                    bytes_wiped=job.bytes_wiped,
                    execution_seconds=job.execution_seconds,
                )
                with self._lock:
                    self._certificates[certificate_id] = certificate
                job.last_message = "Wipe completed successfully."
            self.logger.info(
                "Wipe job completed",
                extra={
                    "event": "wipe_job_completed",
                    "job_id": job.job_id,
                    "device": job.device,
                    "certificate_id": job.certificate_id,
                },
            )
        except Exception as exc:
            with job.lock:
                job.status = JobStatus.FAILED
                job.end_time = datetime.now(timezone.utc)
                job.error = str(exc)
                job.last_message = "Wipe failed."
            self.logger.exception(
                "Wipe job failed",
                extra={"event": "wipe_job_failed", "job_id": job.job_id, "device": job.device},
            )

    def _resolve_device(self, requested_device: str):
        devices = self.detector.list_devices()
        exact = next((d for d in devices if d.device == requested_device), None)
        if exact:
            return exact

        normalized = requested_device.replace("/dev/", "").upper()
        for device in devices:
            if device.device.replace("/dev/", "").upper() == normalized:
                return device
        raise ValueError(f"Device '{requested_device}' not found.")

    @staticmethod
    def _to_response(job: JobRecord) -> WipeJobResponse:
        with job.lock:
            return WipeJobResponse(
                job_id=job.job_id,
                device=job.device,
                wipe_method=job.wipe_method,
                method=job.wipe_method,
                status=job.status,
                progress=round(job.progress, 2),
                start_time=job.start_time,
                end_time=job.end_time,
                certificate_id=job.certificate_id,
                last_message=job.last_message,
                error=job.error,
            )
