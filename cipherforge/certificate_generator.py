from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from .logger import get_logger
from .models import CertificateResponse, DeviceType, WipeMethod

try:
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    REPORTLAB_AVAILABLE = True
except Exception:  # pragma: no cover - handled gracefully at runtime
    REPORTLAB_AVAILABLE = False


class CertificateGenerator:
    """Generates JSON + PDF wipe certificates on completed jobs."""

    def __init__(self, output_dir: str | Path | None = None) -> None:
        base_dir = Path(output_dir) if output_dir else Path(__file__).resolve().parents[1] / "certificates"
        self.output_dir = base_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.logger = get_logger("cipherforge.certificate_generator")

    def generate(
        self,
        certificate_id: str,
        job_id: str,
        device: str,
        device_serial: str,
        device_type: DeviceType,
        wipe_method: WipeMethod,
        overwrite_passes: int,
        verification_status: str,
        recovered_files: int,
        bytes_wiped: int,
        execution_seconds: float,
        timestamp: datetime | None = None,
    ) -> CertificateResponse:
        ts = timestamp or datetime.now(timezone.utc)
        payload = {
            "certificate_id": certificate_id,
            "job_id": job_id,
            "device": device,
            "device_serial": device_serial or "UNKNOWN",
            "device_type": device_type.value,
            "method": wipe_method.value,
            "overwrite_passes": overwrite_passes,
            "timestamp": ts.isoformat(),
            "verification": verification_status,
            "recovered_files": recovered_files,
            "bytes_wiped": bytes_wiped,
            "execution_seconds": round(execution_seconds, 4),
        }
        sha256_hash = self._compute_hash(payload)
        payload["sha256_hash"] = sha256_hash

        json_path = self.output_dir / f"{certificate_id}.json"
        pdf_path = self.output_dir / f"{certificate_id}.pdf"

        self._write_json(json_path, payload)
        self._write_pdf(pdf_path, payload)

        return CertificateResponse(
            id=certificate_id,
            job_id=job_id,
            device=device,
            device_serial=payload["device_serial"],
            device_type=device_type,
            wipe_method=wipe_method,
            overwrite_passes=overwrite_passes,
            timestamp=ts,
            verification_status=verification_status,
            recovered_files=recovered_files,
            sha256_hash=sha256_hash,
            pdf_path=str(pdf_path),
            json_path=str(json_path),
            bytes_wiped=bytes_wiped,
            execution_seconds=execution_seconds,
        )

    @staticmethod
    def _compute_hash(payload: dict[str, object]) -> str:
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(canonical).hexdigest()

    def _write_json(self, output_path: Path, payload: dict[str, object]) -> None:
        try:
            output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        except Exception as exc:
            self.logger.exception("Failed to write JSON certificate", extra={"path": str(output_path)})
            raise RuntimeError(f"Failed to write JSON certificate: {exc}") from exc

    def _write_pdf(self, output_path: Path, payload: dict[str, object]) -> None:
        if not REPORTLAB_AVAILABLE:
            raise RuntimeError("reportlab is not installed. Install it with: pip install reportlab")

        try:
            pdf = canvas.Canvas(str(output_path), pagesize=A4)
            width, height = A4
            y = height - 60

            pdf.setFont("Helvetica-Bold", 18)
            pdf.drawString(50, y, "CipherForge Wipe Certificate")
            y -= 35

            pdf.setFont("Helvetica", 11)
            lines = [
                f"Certificate ID: {payload['certificate_id']}",
                f"Job ID: {payload['job_id']}",
                f"Device: {payload['device']}",
                f"Device Serial: {payload['device_serial']}",
                f"Device Type: {payload['device_type']}",
                f"Wipe Method: {payload['method']}",
                f"Overwrite Passes: {payload['overwrite_passes']}",
                f"Timestamp: {payload['timestamp']}",
                f"Verification Status: {payload['verification']}",
                f"Recovered Files: {payload['recovered_files']}",
                f"Bytes Wiped: {payload['bytes_wiped']}",
                f"Execution Seconds: {payload['execution_seconds']}",
                f"SHA256 Hash: {payload['sha256_hash']}",
            ]

            for line in lines:
                pdf.drawString(50, y, line)
                y -= 20

            pdf.save()
        except Exception as exc:
            self.logger.exception("Failed to write PDF certificate", extra={"path": str(output_path)})
            raise RuntimeError(f"Failed to write PDF certificate: {exc}") from exc
