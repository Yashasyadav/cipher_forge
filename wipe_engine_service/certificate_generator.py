from __future__ import annotations

import hashlib
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

from .models import CertificateMetadata, WipeMethod

try:
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    REPORTLAB_AVAILABLE = True
except Exception:  # pragma: no cover
    REPORTLAB_AVAILABLE = False

try:
    import segno

    SEGNO_AVAILABLE = True
except Exception:  # pragma: no cover
    SEGNO_AVAILABLE = False


class CertificateGenerator:
    """Generates and stores wipe certificates as JSON + PDF."""

    def __init__(self, output_dir: str | Path | None = None) -> None:
        self.logger = logging.getLogger("wipe_engine_service.certificate_generator")
        self.verification_base_url = os.getenv(
            "CERTIFICATE_VERIFY_BASE_URL",
            "http://localhost:8080",
        ).rstrip("/")
        self.output_dir = (
            Path(output_dir)
            if output_dir
            else Path(__file__).resolve().parents[1] / "certificates"
        )
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def generate(
        self,
        certificate_id: str,
        job_id: str,
        device: str,
        device_serial_number: str,
        device_type: str,
        wipe_method: WipeMethod,
        overwrite_passes: int,
        timestamp: datetime | None = None,
        verification_status: str = "PASSED",
        recovered_files: int = 0,
        bytes_wiped: int = 0,
        execution_seconds: float = 0.0,
        verification_url: str | None = None,
    ) -> CertificateMetadata:
        ts = timestamp or datetime.now(timezone.utc)
        verify_url = verification_url or self._verification_url(certificate_id)
        qr_code_path = self.output_dir / f"{certificate_id}_qr.png"
        qr_written = self._write_qr(qr_code_path, verify_url)

        payload_without_hash = {
            "certificate_id": certificate_id,
            "job_id": job_id,
            "device": device,
            "device_serial_number": device_serial_number or "UNKNOWN",
            "device_type": device_type or "UNKNOWN",
            "method": wipe_method.value,
            "overwrite_passes": overwrite_passes,
            "timestamp": ts.isoformat(),
            "verification": verification_status,
            "recovered_files": recovered_files,
            "bytes_wiped": bytes_wiped,
            "execution_seconds": round(execution_seconds, 4),
            "verification_url": verify_url,
            "qr_code_path": str(qr_code_path) if qr_written else "",
        }
        sha256_hash = self._sha256(payload_without_hash)
        payload = {**payload_without_hash, "sha256_hash": sha256_hash}

        json_path = self.output_dir / f"{certificate_id}.json"
        pdf_path = self.output_dir / f"{certificate_id}.pdf"
        self._write_json(json_path, payload)
        self._write_pdf(pdf_path, payload)

        return CertificateMetadata(
            id=certificate_id,
            job_id=job_id,
            device=device,
            device_serial_number=payload["device_serial_number"],
            device_type=payload["device_type"],
            wipe_method=wipe_method,
            overwrite_passes=overwrite_passes,
            timestamp=ts,
            verification_status=verification_status,
            recovered_files=recovered_files,
            sha256_hash=sha256_hash,
            bytes_wiped=bytes_wiped,
            execution_seconds=execution_seconds,
            verification_url=verify_url,
            qr_code_path=str(qr_code_path) if qr_written else "",
            json_path=str(json_path),
            pdf_path=str(pdf_path),
        )

    def load(self, certificate_id: str) -> CertificateMetadata | None:
        json_path = self.output_dir / f"{certificate_id}.json"
        pdf_path = self.output_dir / f"{certificate_id}.pdf"
        if not json_path.exists():
            return None

        payload = json.loads(json_path.read_text(encoding="utf-8"))
        cert_id = payload.get("certificate_id", payload.get("id", certificate_id))
        overwrite_passes = int(payload.get("overwrite_passes", payload.get("passes", 0)))
        verification_url = str(payload.get("verification_url", "")).strip()
        if not verification_url:
            verification_url = self._verification_url(cert_id)
        elif verification_url.startswith("/"):
            verification_url = f"{self.verification_base_url}{verification_url}"
        return CertificateMetadata(
            id=cert_id,
            job_id=payload["job_id"],
            device=payload["device"],
            device_serial_number=payload.get("device_serial_number", "UNKNOWN"),
            device_type=payload.get("device_type", "UNKNOWN"),
            wipe_method=payload["method"],
            overwrite_passes=overwrite_passes,
            timestamp=datetime.fromisoformat(payload["timestamp"]),
            verification_status=payload.get("verification", payload.get("status", "UNKNOWN")),
            recovered_files=int(payload.get("recovered_files", 0)),
            sha256_hash=payload["sha256_hash"],
            bytes_wiped=int(payload.get("bytes_wiped", 0)),
            execution_seconds=float(payload.get("execution_seconds", 0.0)),
            verification_url=verification_url,
            qr_code_path=payload.get("qr_code_path", str(self.output_dir / f"{cert_id}_qr.png")),
            json_path=str(json_path),
            pdf_path=str(pdf_path),
        )

    def _verification_url(self, certificate_id: str) -> str:
        return f"{self.verification_base_url}/verify/{certificate_id}"

    def _write_qr(self, path: Path, verification_url: str) -> bool:
        if not SEGNO_AVAILABLE:
            self.logger.warning("segno is not installed, skipping QR generation for certificate.")
            return False
        try:
            qr = segno.make(verification_url)
            qr.save(str(path), kind="png", scale=6, border=2)
            return True
        except Exception as exc:
            self.logger.warning("Failed to write QR code at %s: %s", path, exc)
            return False

    def _write_json(self, path: Path, payload: dict[str, object]) -> None:
        try:
            path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        except Exception as exc:
            self.logger.exception("Failed to write certificate JSON", extra={"path": str(path)})
            raise RuntimeError(f"Failed to write certificate JSON: {exc}") from exc

    def _write_pdf(self, path: Path, payload: dict[str, object]) -> None:
        if not REPORTLAB_AVAILABLE:
            self.logger.warning("reportlab is not installed, writing fallback PDF for certificate.")
            self._write_fallback_pdf(path, payload)
            return

        try:
            pdf = canvas.Canvas(str(path), pagesize=A4)
            _, page_height = A4
            y = page_height - 56

            pdf.setFont("Helvetica-Bold", 18)
            pdf.drawString(48, y, "CipherForge Wipe Certificate")
            y -= 30

            pdf.setFont("Helvetica", 11)
            lines = [
                f"Certificate ID: {payload['certificate_id']}",
                f"Job ID: {payload['job_id']}",
                f"Device: {payload['device']}",
                f"Device Serial Number: {payload['device_serial_number']}",
                f"Device Type: {payload['device_type']}",
                f"Wipe Method: {payload['method']}",
                f"Overwrite Passes: {payload['overwrite_passes']}",
                f"Timestamp: {payload['timestamp']}",
                f"Verification Status: {payload['verification']}",
                f"Recovered Files: {payload['recovered_files']}",
                f"Verification URL: {payload['verification_url']}",
                f"SHA256 Hash: {payload['sha256_hash']}",
                f"Bytes Wiped: {payload['bytes_wiped']}",
                f"Execution Seconds: {payload['execution_seconds']}",
            ]
            for line in lines:
                pdf.drawString(48, y, line)
                y -= 18
                if y < 40:
                    pdf.showPage()
                    pdf.setFont("Helvetica", 11)
                    y = page_height - 56

            qr_path = payload.get("qr_code_path")
            if qr_path and os.path.exists(str(qr_path)):
                image_size = 120
                if y < image_size + 30:
                    pdf.showPage()
                    pdf.setFont("Helvetica", 11)
                    y = page_height - 56
                pdf.drawString(48, y, "Verification QR Code:")
                y -= 12
                pdf.drawImage(str(qr_path), 48, y - image_size, width=image_size, height=image_size)

            pdf.save()
        except Exception as exc:
            self.logger.exception("Failed to write certificate PDF", extra={"path": str(path)})
            raise RuntimeError(f"Failed to write certificate PDF: {exc}") from exc

    def _write_fallback_pdf(self, path: Path, payload: dict[str, object]) -> None:
        # Minimal valid PDF payload so download/open still works without reportlab.
        lines = [
            "CipherForge Wipe Certificate",
            f"Certificate ID: {payload.get('certificate_id', '')}",
            f"Job ID: {payload.get('job_id', '')}",
            f"Device: {payload.get('device', '')}",
            f"Wipe Method: {payload.get('method', '')}",
            f"Timestamp: {payload.get('timestamp', '')}",
            f"Verification: {payload.get('verification', '')}",
            f"SHA256: {payload.get('sha256_hash', '')}",
            f"Verification URL: {payload.get('verification_url', '')}",
        ]
        text = "\\n".join(lines).replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        stream = f"BT /F1 11 Tf 50 780 Td ({text}) Tj ET"
        stream_bytes = stream.encode("latin-1", "replace")

        objects: list[bytes] = [
            b"1 0 obj<< /Type /Catalog /Pages 2 0 R >>endobj\n",
            b"2 0 obj<< /Type /Pages /Kids [3 0 R] /Count 1 >>endobj\n",
            b"3 0 obj<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>endobj\n",
            f"4 0 obj<< /Length {len(stream_bytes)} >>stream\n".encode("ascii") + stream_bytes + b"\nendstream\nendobj\n",
            b"5 0 obj<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>endobj\n",
        ]

        header = b"%PDF-1.4\n"
        body = bytearray(header)
        offsets = [0]
        for obj in objects:
            offsets.append(len(body))
            body.extend(obj)
        xref_start = len(body)
        body.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
        body.extend(b"0000000000 65535 f \n")
        for offset in offsets[1:]:
            body.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
        body.extend(
            f"trailer<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_start}\n%%EOF\n".encode("ascii")
        )
        path.write_bytes(bytes(body))

    @staticmethod
    def _sha256(payload: dict[str, object]) -> str:
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(canonical).hexdigest()
