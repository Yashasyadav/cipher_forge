from __future__ import annotations

import logging
import os
from typing import Iterable

from fastapi import APIRouter, HTTPException, Query, status

from .filesystem_scanner import FilesystemScanner
from .models import FileMetadata, FilesystemBrowseResponse

router = APIRouter(tags=["filesystem"])


class FolderBrowser:
    """Safe filesystem browsing for drive/file selection workflows."""

    def __init__(self) -> None:
        self.logger = logging.getLogger("wipe_engine_service.folder_browser")
        self.filesystem_scanner = FilesystemScanner()

    def browse(self, requested_path: str) -> FilesystemBrowseResponse:
        safe_path = self._validate_path(requested_path)

        try:
            entries = os.listdir(safe_path)
        except PermissionError as exc:
            self.logger.warning("Permission denied while listing path: %s", safe_path)
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Permission denied for the requested path.",
            ) from exc
        except FileNotFoundError as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Requested path does not exist.",
            ) from exc
        except NotADirectoryError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Requested path is not a directory.",
            ) from exc
        except OSError as exc:
            self.logger.exception("Filesystem listing failed for path: %s", safe_path)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Unable to browse the requested path.",
            ) from exc

        folders: list[str] = []
        files: list[FileMetadata] = []
        for name in sorted(entries, key=str.casefold):
            full_path = os.path.join(safe_path, name)
            try:
                if os.path.isdir(full_path):
                    folders.append(name)
                elif os.path.isfile(full_path):
                    size_bytes = self._safe_getsize(full_path)
                    files.append(
                        FileMetadata(
                            name=name,
                            size_bytes=size_bytes,
                            size=self._format_size(size_bytes),
                        )
                    )
            except OSError:
                # Skip entries that are deleted or become inaccessible during the scan.
                continue

        return FilesystemBrowseResponse(path=safe_path, folders=folders, files=files)

    def _validate_path(self, requested_path: str) -> str:
        candidate = (requested_path or "").strip()
        if not candidate:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Query parameter 'path' is required.",
            )

        if candidate.startswith("\\\\"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="UNC paths are not allowed.",
            )

        normalized_candidate = candidate.replace("/", "\\")
        path_parts = [part for part in normalized_candidate.split("\\") if part]
        if ".." in path_parts:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Path traversal is not allowed.",
            )

        normalized = os.path.normpath(os.path.abspath(normalized_candidate))
        if not os.path.isabs(normalized):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Path must be an absolute directory path.",
            )

        if os.name == "nt":
            drive, _ = os.path.splitdrive(normalized)
            if not drive:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="A valid Windows drive path is required.",
                )

            allowed_drives = self._get_allowed_drives()
            if allowed_drives and drive.upper() not in allowed_drives:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Access to the requested drive is not allowed.",
                )

        return normalized

    def _get_allowed_drives(self) -> set[str]:
        detected = self.filesystem_scanner.list_logical_drives()
        drives = {d.drive.upper().rstrip("\\") for d in detected if d.drive}
        return drives

    @staticmethod
    def _safe_getsize(path: str) -> int:
        try:
            return int(os.path.getsize(path))
        except OSError:
            return 0

    @staticmethod
    def _format_size(size_bytes: int) -> str:
        if size_bytes <= 0:
            return "0B"

        units: Iterable[str] = ("B", "KB", "MB", "GB", "TB", "PB")
        value = float(size_bytes)
        unit = "B"
        for unit in units:
            if value < 1024 or unit == "PB":
                break
            value /= 1024

        if unit == "B":
            return f"{int(value)}{unit}"
        return f"{value:.1f}".rstrip("0").rstrip(".") + unit


folder_browser = FolderBrowser()


@router.get("/filesystem", response_model=FilesystemBrowseResponse)
async def browse_filesystem(path: str = Query(..., min_length=1)) -> FilesystemBrowseResponse:
    return folder_browser.browse(path)

