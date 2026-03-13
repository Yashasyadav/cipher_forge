from __future__ import annotations

import os
import random
import shutil
import subprocess
import importlib
import stat
from dataclasses import dataclass


@dataclass(frozen=True)
class PassSpec:
    kind: str
    pattern: bytes | None = None


class FileWipeExecutor:
    """Secure file shredder with detailed staged logging."""

    WINDOWS_RESERVED_FILES = {
        "pagefile.sys",
        "hiberfil.sys",
        "swapfile.sys",
        "dumpstack.log.tmp",
    }

    GUTMANN_PATTERNS = [
        b"\x55",
        b"\xAA",
        b"\x92\x49\x24",
        b"\x49\x24\x92",
        b"\x24\x92\x49",
        b"\x00",
        b"\x11",
        b"\x22",
        b"\x33",
        b"\x44",
        b"\x55",
        b"\x66",
        b"\x77",
        b"\x88",
        b"\x99",
        b"\xAA",
        b"\xBB",
        b"\xCC",
        b"\xDD",
        b"\xEE",
        b"\xFF",
        b"\x92\x49\x24",
        b"\x49\x24\x92",
        b"\x24\x92\x49",
        b"\x6D\xB6\xDB",
        b"\xB6\xDB\x6D",
        b"\xDB\x6D\xB6",
    ]

    def __init__(self, chunk_size: int = 4 * 1024 * 1024) -> None:
        self.chunk_size = chunk_size

    def secure_delete(self, file_path: str, method: str, cleanup_free_space: bool = False) -> dict[str, object]:
        stage_logs: list[str] = []
        target = self._normalize_and_validate_path(file_path)
        self._guard_reserved_windows_files(target)
        self._ensure_writable(target, stage_logs)
        file_size = os.path.getsize(target)

        self._stage(stage_logs, f"Target selected: {target}")
        self._encrypt_file_in_place(target, stage_logs)

        passes = self._resolve_passes(method)
        self._stage(stage_logs, f"Using method={method} with {len(passes)} overwrite pass(es)")

        if file_size > 0:
            for pass_idx, pass_spec in enumerate(passes, start=1):
                self._stage(stage_logs, f"Overwrite pass {pass_idx}/{len(passes)}")
                self._run_overwrite_pass(target, file_size, pass_spec)
        else:
            with open(target, "r+b") as handle:
                handle.flush()
                os.fsync(handle.fileno())
            self._stage(stage_logs, "Target file is empty; sync-only pass completed")

        randomized_path = self._rename_target(target)
        self._stage(stage_logs, f"Renamed file before delete: {os.path.basename(randomized_path)}")

        self._safe_remove(randomized_path)
        self._stage(stage_logs, "File unlink completed")

        verified = not os.path.exists(randomized_path)
        self._stage(stage_logs, f"Post-delete verification: {'OK' if verified else 'FAILED'}")

        cleanup_result = "skipped"
        if cleanup_free_space:
            cleanup_result = self.sanitize_free_space(os.path.dirname(file_path), stage_logs)

        return {
            "status": "deleted" if verified else "verification_failed",
            "passes": len(passes),
            "verified": verified,
            "deleted_files": 1 if verified else 0,
            "last_message": stage_logs[-1] if stage_logs else "",
            "stage_logs": stage_logs,
            "free_space_cleanup": cleanup_result,
        }

    def sanitize_free_space(self, path: str, stage_logs: list[str] | None = None) -> str:
        logs = stage_logs if stage_logs is not None else []

        if os.name != "nt":
            self._stage(logs, "Free-space cleanup skipped: platform is not Windows")
            return "skipped-non-windows"

        drive, _ = os.path.splitdrive(os.path.abspath(path or os.getcwd()))
        if not drive:
            self._stage(logs, "Free-space cleanup skipped: unable to resolve target drive")
            return "skipped-no-drive"

        self._stage(logs, f"Starting free-space cleanup for {drive}")

        if shutil.which("sdelete"):
            self._run_best_effort_command(
                ["sdelete", "-z", drive],
                logs,
                label="SDelete",
                timeout_seconds=1800,
            )
        else:
            self._stage(logs, "SDelete not available in PATH; skipping SDelete phase")

        self._run_best_effort_command(
            ["cipher", f"/w:{drive}"],
            logs,
            label="CipherW",
            timeout_seconds=1800,
        )

        self._stage(logs, "Free-space cleanup phase completed")
        return "completed"

    def _encrypt_file_in_place(self, file_path: str, stage_logs: list[str]) -> None:
        self._stage(stage_logs, "Starting in-place pre-encryption")
        try:
            fernet_module = importlib.import_module("cryptography.fernet")
            Fernet = getattr(fernet_module, "Fernet")

            key = Fernet.generate_key()
            cipher = Fernet(key)
            with open(file_path, "rb+") as handle:
                source = handle.read()
                encrypted = cipher.encrypt(source)
                handle.seek(0)
                handle.write(encrypted)
                handle.truncate()
                handle.flush()
                os.fsync(handle.fileno())

            # Explicitly discard key material references.
            del key
            del cipher
            del source
            del encrypted
            self._stage(stage_logs, "Pre-encryption completed and ephemeral key destroyed")
        except PermissionError as exc:
            raise PermissionError(self._permission_help(file_path, exc)) from exc
        except Exception as exc:
            self._stage(stage_logs, f"Pre-encryption skipped: {exc}")

    def _run_overwrite_pass(self, file_path: str, total_size: int, pass_spec: PassSpec) -> None:
        try:
            with open(file_path, "r+b", buffering=0) as handle:
                handle.seek(0)
                remaining = total_size
                while remaining > 0:
                    chunk_len = min(self.chunk_size, remaining)
                    data = self._build_chunk(pass_spec, chunk_len)
                    handle.write(data)
                    remaining -= chunk_len
                handle.flush()
                os.fsync(handle.fileno())
        except PermissionError as exc:
            raise PermissionError(self._permission_help(file_path, exc)) from exc

    @staticmethod
    def _build_chunk(pass_spec: PassSpec, chunk_len: int) -> bytes:
        if pass_spec.kind == "random":
            return os.urandom(chunk_len)
        if pass_spec.kind == "zeros":
            return b"\x00" * chunk_len
        if pass_spec.kind == "pattern" and pass_spec.pattern:
            repeated = pass_spec.pattern * ((chunk_len // len(pass_spec.pattern)) + 1)
            return repeated[:chunk_len]
        raise ValueError(f"Unsupported pass specification: {pass_spec.kind}")

    def _rename_target(self, file_path: str) -> str:
        directory, _ = os.path.split(file_path)
        for _ in range(8):
            random_name = "".join(random.choices("abcdefghijklmnopqrstuvwxyz0123456789", k=16))
            new_path = os.path.join(directory, random_name)
            if not os.path.exists(new_path):
                try:
                    os.rename(file_path, new_path)
                    return new_path
                except PermissionError as exc:
                    raise PermissionError(self._permission_help(file_path, exc)) from exc
        raise RuntimeError("Unable to allocate randomized file name for secure delete.")

    @staticmethod
    def _run_best_effort_command(
        command: list[str],
        stage_logs: list[str],
        label: str,
        timeout_seconds: int,
    ) -> None:
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                check=False,
                timeout=timeout_seconds,
            )
            if result.returncode == 0:
                FileWipeExecutor._stage(stage_logs, f"{label}: completed")
            else:
                stderr = (result.stderr or "").strip()
                FileWipeExecutor._stage(stage_logs, f"{label}: exited with code {result.returncode} ({stderr})")
        except Exception as exc:
            FileWipeExecutor._stage(stage_logs, f"{label}: failed ({exc})")

    @classmethod
    def _resolve_passes(cls, method: str) -> list[PassSpec]:
        key = (method or "").strip().lower()

        if key in {"nist", "nist clear"}:
            return [PassSpec(kind="random"), PassSpec(kind="zeros")]

        if key in {"dod", "dod 5220.22-m", "dod 5220.22m"}:
            return [PassSpec(kind="random"), PassSpec(kind="zeros"), PassSpec(kind="random")]

        if key in {"gutmann", "gutmann method"}:
            return [
                PassSpec(kind="random"),
                PassSpec(kind="random"),
                PassSpec(kind="random"),
                PassSpec(kind="random"),
                *[PassSpec(kind="pattern", pattern=pattern) for pattern in cls.GUTMANN_PATTERNS],
                PassSpec(kind="random"),
                PassSpec(kind="random"),
                PassSpec(kind="random"),
                PassSpec(kind="random"),
            ]

        raise ValueError("Unsupported method. Use: NIST Clear, DoD 5220.22-M, or Gutmann.")

    @staticmethod
    def _normalize_and_validate_path(file_path: str) -> str:
        candidate = (file_path or "").strip()
        if not candidate:
            raise ValueError("file_path is required.")

        normalized = os.path.normpath(os.path.abspath(candidate))
        if not os.path.exists(normalized):
            raise FileNotFoundError(f"File not found: {normalized}")
        if not os.path.isfile(normalized):
            raise IsADirectoryError(f"Expected a file path, received: {normalized}")
        return normalized

    def _ensure_writable(self, file_path: str, stage_logs: list[str]) -> None:
        if os.access(file_path, os.W_OK):
            return
        try:
            os.chmod(file_path, stat.S_IREAD | stat.S_IWRITE)
            self._stage(stage_logs, "Adjusted file attributes to writable.")
        except Exception:
            # Permission diagnostics are surfaced by the explicit check below.
            pass
        if not os.access(file_path, os.W_OK):
            raise PermissionError(
                "Write access denied. Run the wipe service with elevated permissions "
                "or move the file to a user-writable directory and retry."
            )

    def _safe_remove(self, file_path: str) -> None:
        try:
            os.remove(file_path)
            return
        except PermissionError:
            try:
                os.chmod(file_path, stat.S_IREAD | stat.S_IWRITE)
                os.remove(file_path)
                return
            except PermissionError as exc:
                raise PermissionError(self._permission_help(file_path, exc)) from exc

    @staticmethod
    def _permission_help(file_path: str, exc: Exception) -> str:
        return (
            f"Permission denied for '{file_path}'. "
            "The file may be open/locked by another application or protected by OS permissions. "
            "Close any app using the file and retry (or run service as administrator). "
            f"Original error: {exc}"
        )

    def _guard_reserved_windows_files(self, file_path: str) -> None:
        if os.name != "nt":
            return
        base_name = os.path.basename(file_path).lower()
        if base_name in self.WINDOWS_RESERVED_FILES:
            raise PermissionError(
                f"'{base_name}' is managed by Windows and cannot be shredded while the OS is running."
            )

    @staticmethod
    def _stage(stage_logs: list[str], message: str) -> None:
        stage_logs.append(message)


def secure_delete(file_path: str, method: str) -> dict[str, object]:
    """Convenience function API required by backend integration."""

    return FileWipeExecutor().secure_delete(file_path=file_path, method=method)
