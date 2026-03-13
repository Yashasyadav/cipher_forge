from __future__ import annotations

import json
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from .certificate_generator import CertificateGenerator
from .device_detector import DeviceDetector
from .forensic_verifier import ForensicVerifier
from .logger import get_logger
from .models import (
    CertificateResponse,
    DeviceType,
    JobState,
    WipeJobResponse,
    WipeMethod,
    WipeRequest,
)
from .wipe_engine import WipeEngine


@dataclass
class JobRecord:
    job_id: str
    device: str
    wipe_method: WipeMethod
    status: JobState
    progress: float
    submitted_at: datetime
    device_serial: str
    device_type: DeviceType
    start_time: datetime | None = None
    end_time: datetime | None = None
    certificate_id: str | None = None
    last_message: str | None = None
    error: str | None = None
    bytes_wiped: int = 0
    passes_completed: int = 0
    execution_seconds: float = 0.0
    audit_digest: str | None = None
    lock: threading.Lock = field(default_factory=threading.Lock)


class WipeManager:
    """Coordinates asynchronous wipe job execution and status tracking."""

    def __init__(
        self,
        detector: DeviceDetector,
        engine: WipeEngine,
        certificate_generator: CertificateGenerator | None = None,
        forensic_verifier: ForensicVerifier | None = None,
        max_workers: int = 2,
    ) -> None:
        self.detector = detector
        self.engine = engine
        self.certificate_generator = certificate_generator or CertificateGenerator()
        self.forensic_verifier = forensic_verifier or ForensicVerifier()
        self.logger = get_logger("cipherforge.wipe_manager")
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="wipe-worker")
        self._jobs: dict[str, JobRecord] = {}
        self._certificates: dict[str, CertificateResponse] = {}
        self._global_lock = threading.RLock()

    def start_wipe(self, payload: WipeRequest) -> WipeJobResponse:
        device = self._resolve_device(payload.device)
        now = datetime.now(timezone.utc)
        job_id = f"job_{uuid.uuid4().hex[:12]}"
        job = JobRecord(
            job_id=job_id,
            device=device.device,
            wipe_method=payload.method,
            status=JobState.QUEUED,
            progress=0.0,
            submitted_at=now,
            device_serial=device.serial,
            device_type=device.type,
            last_message="Job queued.",
        )

        with self._global_lock:
            self._jobs[job_id] = job

        self._executor.submit(
            self._run_wipe_job,
            job_id,
            payload.method,
            device.device,
            device.serial,
            device.type,
            device.size_bytes,
        )
        self.logger.info(
            "Wipe job queued",
            extra={"event": "job_queued", "job_id": job_id, "device": device.device, "method": payload.method.value},
        )

        return self._to_job_response(job)

    def get_status(self, job_id: str) -> WipeJobResponse | None:
        with self._global_lock:
            job = self._jobs.get(job_id)
            if not job:
                return None
        return self._to_job_response(job)

    def get_certificate(self, certificate_id: str) -> CertificateResponse | None:
        with self._global_lock:
            existing = self._certificates.get(certificate_id)
        if existing:
            return existing
        return self._load_certificate_from_disk(certificate_id)

    def _run_wipe_job(
        self,
        job_id: str,
        method: WipeMethod,
        device_name: str,
        device_serial: str,
        device_type: DeviceType,
        device_size: int,
    ) -> None:
        job = self._jobs[job_id]
        with job.lock:
            job.status = JobState.RUNNING
            job.start_time = datetime.now(timezone.utc)
            job.last_message = "Wipe started."

        def progress_callback(progress: float, message: str) -> None:
            with job.lock:
                job.progress = progress
                job.last_message = message

        try:
            result = self.engine.wipe(
                target=device_name,
                method=method,
                size_hint=device_size,
                progress_callback=progress_callback,
            )

            with job.lock:
                job.end_time = result["finished_at"]
                job.progress = 100.0
                job.status = JobState.COMPLETED
                job.bytes_wiped = int(result["bytes_wiped"])
                job.passes_completed = int(result["passes_completed"])
                job.execution_seconds = float(result["execution_seconds"])
                job.audit_digest = str(result["audit_digest"])
                job.last_message = "Wipe completed. Running forensic verification."

            forensic_result = self.forensic_verifier.verify(device_name)
            recovered_files = int(forensic_result.get("recovered_files", 0))
            verification_status = str(forensic_result.get("verification", "FAILED"))

            with job.lock:
                job.last_message = "Forensic verification finished. Generating certificate."

            with job.lock:
                certificate_id = str(uuid.uuid4())
                job.certificate_id = certificate_id

                certificate = self.certificate_generator.generate(
                    certificate_id=certificate_id,
                    job_id=job.job_id,
                    device=device_name,
                    device_serial=device_serial,
                    device_type=device_type,
                    wipe_method=method,
                    overwrite_passes=job.passes_completed,
                    verification_status=verification_status,
                    recovered_files=recovered_files,
                    bytes_wiped=job.bytes_wiped,
                    execution_seconds=job.execution_seconds,
                    timestamp=result["finished_at"],
                )
                with self._global_lock:
                    self._certificates[certificate_id] = certificate
                job.last_message = "Wipe completed successfully. Certificate generated."

            self.logger.info(
                "Wipe job completed",
                extra={
                    "event": "job_completed",
                    "job_id": job_id,
                    "device": device_name,
                    "method": method.value,
                    "certificate_id": certificate_id,
                },
            )
        except Exception as exc:
            with job.lock:
                job.end_time = datetime.now(timezone.utc)
                job.status = JobState.FAILED
                job.error = str(exc)
                job.last_message = "Wipe failed."
            self.logger.exception(
                "Wipe job failed",
                extra={"event": "job_failed", "job_id": job_id, "device": device_name, "method": method.value},
            )

    def _resolve_device(self, requested_device: str):
        devices = self.detector.list_devices()
        direct_match = next((item for item in devices if item.device == requested_device), None)
        if direct_match:
            if direct_match.type == DeviceType.ANDROID:
                raise ValueError("Android devices are discoverable but not wipe-enabled in this endpoint.")
            return direct_match

        normalized = requested_device.replace("/dev/", "").upper()
        for item in devices:
            if item.device.replace("/dev/", "").upper() == normalized:
                if item.type == DeviceType.ANDROID:
                    raise ValueError("Android devices are discoverable but not wipe-enabled in this endpoint.")
                return item

        raise ValueError(f"Device '{requested_device}' was not found in detected devices.")

    @staticmethod
    def _to_job_response(job: JobRecord) -> WipeJobResponse:
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
                submitted_at=job.submitted_at,
                certificate_id=job.certificate_id,
                last_message=job.last_message,
                error=job.error,
            )

    def _load_certificate_from_disk(self, certificate_id: str) -> CertificateResponse | None:
        path = Path(self.certificate_generator.output_dir) / f"{certificate_id}.json"
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            certificate = CertificateResponse(
                id=payload["certificate_id"],
                job_id=payload["job_id"],
                device=payload["device"],
                device_serial=payload.get("device_serial", "UNKNOWN"),
                device_type=payload.get("device_type", DeviceType.UNKNOWN.value),
                wipe_method=payload["method"],
                overwrite_passes=int(payload.get("overwrite_passes", 0)),
                timestamp=datetime.fromisoformat(payload["timestamp"]),
                verification_status=payload.get("verification", "UNKNOWN"),
                recovered_files=int(payload.get("recovered_files", 0)),
                sha256_hash=payload["sha256_hash"],
                pdf_path=str(Path(self.certificate_generator.output_dir) / f"{certificate_id}.pdf"),
                json_path=str(path),
                bytes_wiped=int(payload.get("bytes_wiped", 0)),
                execution_seconds=float(payload.get("execution_seconds", 0.0)),
            )
        except Exception:
            self.logger.exception(
                "Failed to load certificate from disk",
                extra={"event": "certificate_load_failed", "certificate_id": certificate_id},
            )
            return None
        with self._global_lock:
            self._certificates[certificate_id] = certificate
        return certificate
