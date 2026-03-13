from __future__ import annotations

import csv
import io
import json
import platform
import subprocess
from typing import Iterable

from .logger import get_logger
from .models import DeviceInfo, DeviceType


class DeviceDetector:
    """Cross-platform storage and Android target discovery."""

    def __init__(self) -> None:
        self.logger = get_logger("cipherforge.device_detector")

    def list_devices(self) -> list[DeviceInfo]:
        """
        Detect block devices on host OS and append Android devices discovered via ADB.
        Returns partial results on failure instead of raising hard errors.
        """
        system_name = platform.system().lower()
        devices: list[DeviceInfo] = []

        if system_name == "linux":
            devices.extend(self._list_linux_devices())
        elif system_name == "windows":
            devices.extend(self._list_windows_devices())
        else:
            self.logger.warning(
                "Unsupported operating system for block device scan",
                extra={"platform": platform.system()},
            )

        devices.extend(self._list_android_devices())
        return devices

    def _list_linux_devices(self) -> list[DeviceInfo]:
        cmd = ["lsblk", "-b", "-d", "-J", "-o", "NAME,SIZE,ROTA,RM,TRAN,SERIAL"]
        output = self._run_command(cmd)
        if output is None:
            return []

        try:
            parsed = json.loads(output)
        except json.JSONDecodeError:
            self.logger.exception("Failed to parse lsblk JSON output")
            return []

        devices: list[DeviceInfo] = []

        for entry in parsed.get("blockdevices", []):
            name = str(entry.get("name", "")).strip()
            if not name:
                continue

            serial = self._safe_text(entry.get("serial")) or "UNKNOWN"
            smartctl_info = self._get_linux_smart_info(name)
            if smartctl_info.get("serial"):
                serial = smartctl_info["serial"]

            device_type = self._infer_linux_type(
                name=name,
                rota=entry.get("rota"),
                removable=entry.get("rm"),
                transport=(entry.get("tran") or ""),
                smartctl_hint=smartctl_info.get("type_hint"),
            )
            size_bytes = self._safe_int(entry.get("size"))
            devices.append(
                DeviceInfo(
                    device=name,
                    type=device_type,
                    size=self._format_size(size_bytes),
                    serial=serial,
                    size_bytes=size_bytes,
                )
            )
        return devices

    def _list_windows_devices(self) -> list[DeviceInfo]:
        cmd = [
            "wmic",
            "diskdrive",
            "get",
            "DeviceID,Model,MediaType,Size,InterfaceType,SerialNumber",
            "/format:csv",
        ]
        output = self._run_command(cmd)
        if output is None:
            return []

        reader = csv.DictReader(io.StringIO(output))
        devices: list[DeviceInfo] = []

        for row in reader:
            device_name = (row.get("DeviceID") or "").strip()
            if not device_name:
                continue

            interface = (row.get("InterfaceType") or "").lower()
            media = (row.get("MediaType") or "").lower()
            model = (row.get("Model") or "").lower()
            size_bytes = self._safe_int(row.get("Size"))
            devices.append(
                DeviceInfo(
                    device=device_name,
                    type=self._infer_windows_type(interface, media, model),
                    size=self._format_size(size_bytes),
                    serial=self._safe_text(row.get("SerialNumber")) or "UNKNOWN",
                    size_bytes=size_bytes,
                )
            )
        return devices

    def _list_android_devices(self) -> list[DeviceInfo]:
        output = self._run_command(["adb", "devices"])
        if output is None:
            return []

        devices: list[DeviceInfo] = []
        for line in output.splitlines():
            line = line.strip()
            if not line or line.lower().startswith("list of devices"):
                continue
            if "\tdevice" not in line:
                continue
            serial = line.split("\t", 1)[0].strip()
            if not serial:
                continue
            devices.append(
                DeviceInfo(
                    device=serial,
                    type=DeviceType.ANDROID,
                    size="N/A",
                    serial=serial,
                    size_bytes=0,
                )
            )
        return devices

    def _get_linux_smart_info(self, device_name: str) -> dict[str, str]:
        """
        Query smartctl for serial and medium hints.
        Returns empty dict if smartctl is unavailable or fails.
        """
        device_path = f"/dev/{device_name}"
        output = self._run_command(["smartctl", "-i", device_path], allow_failure=True)
        if not output:
            return {}

        serial = ""
        type_hint = ""
        for line in output.splitlines():
            lower = line.lower()
            if lower.startswith("serial number:"):
                serial = line.split(":", 1)[1].strip()
            elif lower.startswith("rotation rate:"):
                value = line.split(":", 1)[1].strip().lower()
                if "solid state" in value:
                    type_hint = "ssd"
                elif "rpm" in value:
                    type_hint = "hdd"
            elif "nvme version" in lower:
                type_hint = "nvme"
        return {"serial": serial, "type_hint": type_hint}

    def _run_command(self, command: Iterable[str], allow_failure: bool = False) -> str | None:
        command_list = list(command)
        try:
            result = subprocess.run(
                command_list,
                capture_output=True,
                text=True,
                check=True,
            )
            return result.stdout
        except FileNotFoundError as exc:
            self.logger.warning(
                "Required system command was not found",
                extra={"command": command_list, "error": str(exc)},
            )
            return None
        except subprocess.CalledProcessError as exc:
            level = self.logger.warning if allow_failure else self.logger.error
            level(
                "Device discovery command failed",
                extra={
                    "command": command_list,
                    "stderr": (exc.stderr or "").strip(),
                    "returncode": exc.returncode,
                },
            )
            return None

    @staticmethod
    def _safe_int(value: object) -> int:
        try:
            return int(str(value).strip())
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _safe_text(value: object) -> str:
        return str(value).strip() if value is not None else ""

    @staticmethod
    def _format_size(size_bytes: int) -> str:
        if size_bytes <= 0:
            return "0B"
        units = ["B", "KB", "MB", "GB", "TB", "PB"]
        size = float(size_bytes)
        unit_index = 0
        while size >= 1024 and unit_index < len(units) - 1:
            size /= 1024
            unit_index += 1
        if unit_index == 0:
            return f"{int(size)}{units[unit_index]}"
        if size >= 100:
            return f"{int(round(size))}{units[unit_index]}"
        value = f"{size:.1f}".rstrip("0").rstrip(".")
        return f"{value}{units[unit_index]}"

    @staticmethod
    def _infer_linux_type(
        name: str,
        rota: object,
        removable: object,
        transport: str,
        smartctl_hint: str = "",
    ) -> DeviceType:
        is_removable = str(removable).strip() == "1"
        is_rotational = str(rota).strip() == "1"
        transport = transport.lower()
        name_lower = name.lower()
        smart_hint = smartctl_hint.lower()

        if "usb" in transport or is_removable:
            return DeviceType.USB
        if "nvme" in transport or name_lower.startswith("nvme") or smart_hint == "nvme":
            return DeviceType.NVME
        if smart_hint == "ssd":
            return DeviceType.SSD
        if smart_hint == "hdd":
            return DeviceType.HDD
        if is_rotational:
            return DeviceType.HDD
        return DeviceType.SSD

    @staticmethod
    def _infer_windows_type(interface: str, media: str, model: str) -> DeviceType:
        if "usb" in interface:
            return DeviceType.USB
        if "nvme" in interface or "nvme" in media or "nvme" in model:
            return DeviceType.NVME
        if "ssd" in media or "ssd" in model:
            return DeviceType.SSD
        if "hdd" in media or "fixed hard disk" in media:
            return DeviceType.HDD
        return DeviceType.UNKNOWN
