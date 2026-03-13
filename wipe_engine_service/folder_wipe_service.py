from __future__ import annotations

import logging
import os
from pathlib import Path
from collections.abc import Callable

from .file_wipe_executor import FileWipeExecutor


class FolderWipeService:
    """Securely shreds all files in a folder and removes its directory structure."""

    def __init__(self, file_wipe_executor: FileWipeExecutor | None = None) -> None:
        self.file_wipe_executor = file_wipe_executor or FileWipeExecutor()
        self.logger = logging.getLogger("wipe_engine_service.folder_wipe")
        self.default_method = os.getenv("WIPE_FOLDER_METHOD", "DoD")
        self.enable_free_space_cleanup = os.getenv("WIPE_ENABLE_FREE_SPACE_CLEANUP", "false").lower() in {"1", "true", "yes"}

    def wipe_folder(
        self,
        folder_path: str,
        method: str | None = None,
        progress_callback: Callable[[dict[str, object]], None] | None = None,
    ) -> dict[str, object]:
        target = self._validate_target_folder(folder_path)
        selected_method = (method or self.default_method).strip()
        files_to_wipe = self.collect_wipe_targets(str(target))
        total_files = len(files_to_wipe)

        deleted_files = 0
        failed_files = 0
        processed_files = 0

        self._notify_progress(
            progress_callback,
            total_files=total_files,
            processed_files=0,
            deleted_files=0,
            failed_files=0,
            current_file=None,
            last_message=f"Folder wipe queued for {total_files} file(s).",
        )

        for target_file in files_to_wipe:
            file_path = str(target_file)
            try:
                result = self.file_wipe_executor.secure_delete(file_path, selected_method, cleanup_free_space=False)
                deleted_files += 1
                self.logger.info("Deleted file", extra={"path": file_path, "method": selected_method})
                last_message = str(result.get("last_message") or f"Deleted: {file_path}")
            except Exception as exc:
                failed_files += 1
                last_message = f"Failed: {file_path} ({exc})"
                self.logger.warning(
                    "Failed to delete file",
                    extra={"path": file_path, "method": selected_method, "error": str(exc)},
                )

            processed_files += 1
            self._notify_progress(
                progress_callback,
                total_files=total_files,
                processed_files=processed_files,
                deleted_files=deleted_files,
                failed_files=failed_files,
                current_file=file_path,
                last_message=last_message,
            )

        self._remove_directories_bottom_up(target)

        # Free-space cleanup is expensive; keep it configurable for operational control.
        if self.enable_free_space_cleanup:
            cleanup_result = self.file_wipe_executor.sanitize_free_space(str(target))
        else:
            cleanup_result = "skipped-by-config"
        final_status = "completed" if failed_files == 0 else "failed"
        final_message = (
            f"Folder wipe completed: deleted={deleted_files}, failed={failed_files}, total={total_files}, cleanup={cleanup_result}"
            if failed_files == 0
            else f"Folder wipe finished with errors: deleted={deleted_files}, failed={failed_files}, total={total_files}, cleanup={cleanup_result}"
        )
        self._notify_progress(
            progress_callback,
            total_files=total_files,
            processed_files=processed_files,
            deleted_files=deleted_files,
            failed_files=failed_files,
            current_file=None,
            last_message=final_message,
        )
        return {
            "deleted_files": deleted_files,
            "failed_files": failed_files,
            "processed_files": processed_files,
            "total_files": total_files,
            "status": final_status,
            "last_message": final_message,
        }

    def validate_folder_path(self, folder_path: str) -> Path:
        return self._validate_target_folder(folder_path)

    def collect_wipe_targets(self, folder_path: str) -> list[Path]:
        target = self._validate_target_folder(folder_path)
        visited_dirs: set[Path] = set()
        files_to_wipe: list[Path] = []

        for root, dirnames, filenames in os.walk(target, topdown=True, followlinks=False):
            current = Path(root)

            resolved_current = self._safe_resolve(current)
            if not resolved_current:
                self.logger.warning("Skipping unresolved directory", extra={"path": str(current)})
                dirnames[:] = []
                continue

            if resolved_current in visited_dirs:
                dirnames[:] = []
                continue
            visited_dirs.add(resolved_current)

            allowed_dirnames: list[str] = []
            for dirname in dirnames:
                child = current / dirname
                if child.is_symlink():
                    self.logger.warning("Skipping symlink directory", extra={"path": str(child)})
                    continue

                resolved_child = self._safe_resolve(child)
                if not resolved_child:
                    self.logger.warning("Skipping unresolved child directory", extra={"path": str(child)})
                    continue

                if not self._is_within_target(target, resolved_child):
                    self.logger.warning("Skipping directory outside target", extra={"path": str(resolved_child)})
                    continue

                if self._is_system_protected(resolved_child):
                    self.logger.warning("Skipping protected directory", extra={"path": str(resolved_child)})
                    continue

                allowed_dirnames.append(dirname)
            dirnames[:] = allowed_dirnames

            for filename in filenames:
                candidate = current / filename
                if candidate.is_symlink():
                    self.logger.warning("Skipping symlink file", extra={"path": str(candidate)})
                    continue

                resolved_file = self._safe_resolve(candidate)
                if not resolved_file:
                    self.logger.warning("Skipping unresolved file", extra={"path": str(candidate)})
                    continue

                if not self._is_within_target(target, resolved_file):
                    self.logger.warning("Skipping file outside target", extra={"path": str(resolved_file)})
                    continue

                if self._is_system_protected(resolved_file):
                    self.logger.warning("Skipping protected file", extra={"path": str(resolved_file)})
                    continue

                if resolved_file.is_file():
                    files_to_wipe.append(resolved_file)

        return files_to_wipe

    def _validate_target_folder(self, folder_path: str) -> Path:
        candidate = (folder_path or "").strip()
        if not candidate:
            raise ValueError("path is required")

        normalized = Path(os.path.normpath(os.path.abspath(candidate)))

        if not normalized.exists():
            raise FileNotFoundError(f"Folder not found: {normalized}")
        if not normalized.is_dir():
            raise NotADirectoryError(f"Expected a folder path, received: {normalized}")

        resolved = normalized.resolve(strict=True)
        if self._is_system_protected(resolved):
            raise PermissionError(f"Protected directory is not allowed: {resolved}")

        if len(resolved.parts) <= 1:
            # Prevent wiping filesystem roots such as C:\ or /.
            raise PermissionError("Wiping a filesystem root is not allowed")

        return resolved

    def _remove_directories_bottom_up(self, target: Path) -> None:
        for root, _, _ in os.walk(target, topdown=False, followlinks=False):
            current = Path(root)
            try:
                current.rmdir()
                self.logger.info("Removed directory", extra={"path": str(current)})
            except OSError:
                # Keep resilient behavior: some directories may be non-empty or protected.
                self.logger.warning("Unable to remove directory", extra={"path": str(current)})

    @staticmethod
    def _safe_resolve(path: Path) -> Path | None:
        try:
            return path.resolve(strict=False)
        except OSError:
            return None

    @staticmethod
    def _is_system_protected(path: Path) -> bool:
        normalized = str(path).lower()

        protected_keywords = [
            "\\windows",
            "\\program files",
            "\\program files (x86)",
            "\\programdata",
            "\\$recycle.bin",
            "\\system volume information",
            "\\recovery",
        ]

        if os.name == "nt":
            parts = {part.lower() for part in path.parts}
            if any(keyword.strip("\\") in parts for keyword in ["windows", "programdata", "$recycle.bin"]):
                return True

        return any(keyword in normalized for keyword in protected_keywords)

    @staticmethod
    def _is_within_target(target: Path, candidate: Path) -> bool:
        try:
            candidate.relative_to(target)
            return True
        except ValueError:
            return False

    @staticmethod
    def _notify_progress(
        callback: Callable[[dict[str, object]], None] | None,
        *,
        total_files: int,
        processed_files: int,
        deleted_files: int,
        failed_files: int,
        current_file: str | None,
        last_message: str,
    ) -> None:
        if callback is None:
            return
        if total_files <= 0:
            progress = 100.0
        else:
            progress = min(100.0, max(0.0, (processed_files / total_files) * 100))
        callback(
            {
                "total_files": total_files,
                "processed_files": processed_files,
                "deleted_files": deleted_files,
                "failed_files": failed_files,
                "current_file": current_file,
                "progress": progress,
                "last_message": last_message,
            }
        )
