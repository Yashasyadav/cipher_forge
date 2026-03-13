from __future__ import annotations

import json
import logging
import os
from html import escape
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from starlette.concurrency import run_in_threadpool

from .certificate_generator import CertificateGenerator
from .device_detector import DeviceDetector
from .filesystem_scanner import FilesystemScanner
from .folder_browser_api import router as folder_browser_router
from .folder_wipe_manager import FolderWipeManager
from .folder_wipe_service import FolderWipeService
from .file_wipe_executor import FileWipeExecutor
from .models import (
  CertificateMetadata,
  DeviceInfo,
  FileWipeRequest,
  FileWipeResponse,
  FolderWipeJobStatusResponse,
  FolderWipeRequest,
  FolderWipeResponse,
  LogicalDriveInfo,
  VerificationResponse,
  WipeJobResponse,
  WipeRequest,
)
from .wipe_executor import WipeExecutor
from .wipe_manager import WipeManager


class JsonFormatter(logging.Formatter):
    """Simple structured JSON formatter for production logs."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure_logging() -> None:
    root = logging.getLogger()
    root.setLevel(os.getenv("LOG_LEVEL", "INFO").upper())
    root.handlers.clear()
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root.addHandler(handler)


configure_logging()
logger = logging.getLogger("wipe_engine_service.api")

app = FastAPI(
    title="CipherForge Wipe Engine",
    version="1.0.0",
    description="FastAPI microservice for secure data wiping.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "*").split(","),
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)
app.include_router(folder_browser_router)

device_detector = DeviceDetector()
filesystem_scanner = FilesystemScanner()
wipe_executor = WipeExecutor()
file_wipe_executor = FileWipeExecutor()
folder_wipe_service = FolderWipeService()
folder_wipe_manager = FolderWipeManager(folder_wipe_service=folder_wipe_service)
certificate_generator = CertificateGenerator()
wipe_manager = WipeManager(
    executor=wipe_executor,
    detector=device_detector,
    certificate_generator=certificate_generator,
)


@app.get("/devices", response_model=list[DeviceInfo], tags=["devices"])
async def get_devices() -> list[DeviceInfo]:
    try:
        return device_detector.list_devices()
    except Exception as exc:
        logger.exception("Device detection failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Device detection failed: {exc}",
        ) from exc


@app.get("/drives", response_model=list[LogicalDriveInfo], tags=["devices"])
async def get_drives() -> list[LogicalDriveInfo]:
    try:
        return filesystem_scanner.list_logical_drives()
    except Exception as exc:
        logger.exception("Logical drive scan failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Logical drive scan failed: {exc}",
        ) from exc


@app.post("/wipe", response_model=WipeJobResponse, status_code=status.HTTP_202_ACCEPTED, tags=["wipe"])
async def start_wipe(request: WipeRequest) -> WipeJobResponse:
    try:
        return wipe_manager.start_wipe(request)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Failed to start wipe job")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to start wipe job: {exc}",
        ) from exc


@app.post("/wipe/folder", response_model=FolderWipeResponse, tags=["wipe"])
async def wipe_folder(request: FolderWipeRequest) -> FolderWipeResponse:
    try:
        result = await run_in_threadpool(folder_wipe_service.wipe_folder, request.path, request.method)
        return FolderWipeResponse(**result)
    except (ValueError, FileNotFoundError, NotADirectoryError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Failed to wipe folder", extra={"path": request.path})
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to wipe folder: {exc}",
        ) from exc


@app.post("/wipe/folder/start", response_model=FolderWipeJobStatusResponse, status_code=status.HTTP_202_ACCEPTED, tags=["wipe"])
async def start_folder_wipe(request: FolderWipeRequest) -> FolderWipeJobStatusResponse:
    try:
        return folder_wipe_manager.start_wipe(request)
    except (ValueError, FileNotFoundError, NotADirectoryError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Failed to queue folder wipe", extra={"path": request.path})
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to queue folder wipe: {exc}",
        ) from exc


@app.get("/wipe/folder/status/{jobId}", response_model=FolderWipeJobStatusResponse, tags=["wipe"])
async def get_folder_wipe_status(jobId: str) -> FolderWipeJobStatusResponse:
    response = folder_wipe_manager.get_status(jobId)
    if not response:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Folder job '{jobId}' not found.")
    return response


@app.post("/wipe/file", response_model=FileWipeResponse, tags=["wipe"])
async def wipe_file(request: FileWipeRequest) -> FileWipeResponse:
    try:
        enable_free_space_cleanup = os.getenv("WIPE_ENABLE_FREE_SPACE_CLEANUP", "false").lower() in {"1", "true", "yes"}
        result = await run_in_threadpool(
            file_wipe_executor.secure_delete,
            request.path,
            request.method,
            enable_free_space_cleanup,
        )
        return FileWipeResponse(**result)
    except (ValueError, FileNotFoundError, IsADirectoryError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Failed to wipe file", extra={"path": request.path})
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to wipe file: {exc}",
        ) from exc


@app.get("/wipe/status/{jobId}", response_model=WipeJobResponse, tags=["wipe"])
async def get_wipe_status(jobId: str) -> WipeJobResponse:
    response = wipe_manager.get_status(jobId)
    if not response:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Job '{jobId}' not found.")
    return response


@app.get("/certificate/{jobId}", response_model=CertificateMetadata, tags=["certificate"])
async def get_certificate(jobId: str) -> CertificateMetadata:
    # Primary contract: certificate by wipe job id.
    certificate = wipe_manager.get_certificate_by_job_id(jobId)
    # Backward compatibility: allow direct certificate-id lookup.
    if not certificate:
        certificate = wipe_manager.get_certificate(jobId)
    if not certificate:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Certificate for '{jobId}' not found.")
    return certificate


@app.get("/verify/{certificate_id}", tags=["verification"])
async def verify_certificate(certificate_id: str, request: Request, view: str | None = None):
    certificate = wipe_manager.get_certificate(certificate_id)
    if not certificate:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Certificate '{certificate_id}' not found.")

    payload = VerificationResponse(
        device=certificate.device,
        wipe_method=certificate.wipe_method,
        timestamp=certificate.timestamp,
        verification_status=certificate.verification_status,
    )

    accept = request.headers.get("accept", "").lower()
    render_html = view == "html" or ("text/html" in accept and view != "json")
    if render_html:
        return HTMLResponse(content=_render_verification_page(certificate_id, payload))
    return payload


def _render_verification_page(certificate_id: str, payload: VerificationResponse) -> str:
    is_authentic = payload.verification_status.upper() == "PASSED"
    status_class = "ok" if is_authentic else "bad"
    authenticity_text = "Certificate is authentic" if is_authentic else "Certificate failed verification"
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>CipherForge Verification</title>
  <style>
    body {{
      margin: 0;
      font-family: 'Segoe UI', Tahoma, sans-serif;
      background: linear-gradient(135deg, #e6f4f7 0%, #f7fbfc 100%);
      color: #1c2f3f;
      min-height: 100vh;
      display: grid;
      place-items: center;
      padding: 24px;
    }}
    .card {{
      width: min(720px, 100%);
      background: #ffffff;
      border: 1px solid #dbe5ed;
      border-radius: 16px;
      box-shadow: 0 10px 30px rgba(15, 40, 64, 0.12);
      padding: 24px;
    }}
    h1 {{
      margin: 0 0 8px;
      font-size: 1.5rem;
    }}
    .meta {{
      color: #607387;
      margin-bottom: 20px;
      font-size: 0.92rem;
    }}
    .grid {{
      display: grid;
      gap: 12px;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
    }}
    .item {{
      border: 1px solid #e3eaf1;
      border-radius: 10px;
      padding: 12px;
      background: #fbfdff;
    }}
    .label {{
      font-size: 0.82rem;
      color: #607387;
    }}
    .value {{
      margin-top: 4px;
      font-size: 1rem;
      font-weight: 600;
    }}
    .ok {{
      color: #0a7f37;
    }}
    .bad {{
      color: #b42318;
    }}
    .banner {{
      margin: 0 0 18px;
      padding: 10px 12px;
      border-radius: 10px;
      font-weight: 600;
      border: 1px solid #e3eaf1;
      background: #f8fbff;
    }}
  </style>
</head>
<body>
  <section class="card">
    <h1>Certificate Verification</h1>
    <p class="meta">Certificate ID: {escape(certificate_id)}</p>
    <p class="banner {status_class}">{escape(authenticity_text)}</p>
    <div class="grid">
      <div class="item">
        <div class="label">Device</div>
        <div class="value">{escape(payload.device)}</div>
      </div>
      <div class="item">
        <div class="label">Wipe Method</div>
        <div class="value">{escape(payload.wipe_method.value)}</div>
      </div>
      <div class="item">
        <div class="label">Timestamp</div>
        <div class="value">{escape(payload.timestamp.isoformat())}</div>
      </div>
      <div class="item">
        <div class="label">Verification Status</div>
        <div class="value {status_class}">{escape(payload.verification_status)}</div>
      </div>
    </div>
  </section>
</body>
</html>"""


@app.get("/health", tags=["service"])
async def health() -> dict[str, str]:
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "wipe_engine_service.main:app",
        host=os.getenv("WIPE_ENGINE_HOST", "0.0.0.0"),
        port=int(os.getenv("WIPE_ENGINE_PORT", "8000")),
        log_level=os.getenv("WIPE_ENGINE_LOG_LEVEL", "info").lower(),
    )
