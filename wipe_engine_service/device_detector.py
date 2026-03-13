from __future__ import annotations

import csv
import io
import json
import logging
import platform
import subprocess
from typing import Iterable

from .models import DeviceInfo


class DeviceDetector:
    """Cross-platform storage + Android device discovery."""

    def __init__(self) -> None:
        self.logger = logging.getLogger("wipe_engine_service.device_detector")

    def list_devices(self) -> list[DeviceInfo]:
        os_name = platform.system().lower()
        devices: list[DeviceInfo] = []

        if os_name == "linux":
            devices.extend(self._linux_devices())
        elif os_name == "windows":
            devices.extend(self._windows_devices())
        else:
            self.logger.warning("Unsupported OS for block device scan", extra={"os": platform.system()})

        devices.extend(self._android_devices())
        return devices

    def _linux_devices(self) -> list[DeviceInfo]:
        output = self._run_command(["lsblk", "-b", "-d", "-J", "-o", "NAME,SIZE,ROTA,RM,TRAN,SERIAL"])
        if output is None:
            return []
        try:
            parsed = json.loads(output)
        except json.JSONDecodeError:
            self.logger.exception("Invalid lsblk JSON output")
            return []

        devices: list[DeviceInfo] = []
        for item in parsed.get("blockdevices", []):
            name = str(item.get("name", "")).strip()
            if not name:
                continue

            size_bytes = self._to_int(item.get("size"))
            serial = str(item.get("serial", "") or "").strip() or "UNKNOWN"
            smart = self._linux_smartctl_info(name)
            if smart.get("serial"):
                serial = smart["serial"]

            devices.append(
                DeviceInfo(
                    device=name,
                    type=self._linux_type(
                        name=name,
                        transport=str(item.get("tran", "")).lower(),
                        removable=str(item.get("rm", "0")) == "1",
                        rotational=str(item.get("rota", "0")) == "1",
                        smart_hint=smart.get("type_hint", ""),
                    ),
                    size=self._format_size(size_bytes),
                    serial=serial,
                    size_bytes=size_bytes,
                )
            )
        return devices

    def _windows_devices(self) -> list[DeviceInfo]:
        output = self._run_command(
            [
                "wmic",
                "diskdrive",
                "get",
                "DeviceID,Model,MediaType,Size,SerialNumber,InterfaceType",
                "/format:csv",
            ],
            allow_failure=True,
        )
        devices = self._parse_windows_csv_devices(output) if output else []
        if devices:
            return devices
        return self._windows_devices_via_cim()

    def _parse_windows_csv_devices(self, output: str) -> list[DeviceInfo]:
        reader = csv.DictReader(io.StringIO(output))
        devices: list[DeviceInfo] = []

        for row in reader:
            device_id = (row.get("DeviceID") or "").strip()
            if not device_id:
                continue

            model = (row.get("Model") or "").lower()
            media = (row.get("MediaType") or "").lower()
            interface = (row.get("InterfaceType") or "").lower()
            size_bytes = self._to_int(row.get("Size"))

            devices.append(
                DeviceInfo(
                    device=device_id,
                    type=self._windows_type(model=model, media=media, interface=interface),
                    size=self._format_size(size_bytes),
                    serial=(row.get("SerialNumber") or "UNKNOWN").strip(),
                    size_bytes=size_bytes,
                )
            )

        return devices

    def _windows_devices_via_cim(self) -> list[DeviceInfo]:
        output = self._run_command(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                "Get-CimInstance Win32_DiskDrive | "
                "Select-Object DeviceID,Model,MediaType,Size,SerialNumber,InterfaceType | "
                "ConvertTo-Json -Compress",
            ],
            allow_failure=True,
        )
        if not output:
            return []

        try:
            parsed = json.loads(output)
        except json.JSONDecodeError:
            self.logger.exception("Invalid PowerShell JSON output for Win32_DiskDrive")
            return []

        rows = parsed if isinstance(parsed, list) else [parsed]
        devices: list[DeviceInfo] = []

        for row in rows:
            if not isinstance(row, dict):
                continue
            device_id = str(row.get("DeviceID") or "").strip()
            if not device_id:
                continue

            model = str(row.get("Model") or "").lower()
            media = str(row.get("MediaType") or "").lower()
            interface = str(row.get("InterfaceType") or "").lower()
            size_bytes = self._to_int(row.get("Size"))

            devices.append(
                DeviceInfo(
                    device=device_id,
                    type=self._windows_type(model=model, media=media, interface=interface),
                    size=self._format_size(size_bytes),
                    serial=str(row.get("SerialNumber") or "UNKNOWN").strip() or "UNKNOWN",
                    size_bytes=size_bytes,
                )
            )

        return devices

    def _android_devices(self) -> list[DeviceInfo]:
        output = self._run_command(["adb", "devices"], allow_failure=True)
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
            devices.append(DeviceInfo(device=serial, type="ANDROID", size="N/A", serial=serial, size_bytes=0))
        return devices

    def _linux_smartctl_info(self, name: str) -> dict[str, str]:
        output = self._run_command(["smartctl", "-i", f"/dev/{name}"], allow_failure=True)
        if not output:
            return {}

        serial = ""
        type_hint = ""
        for line in output.splitlines():
            lowered = line.lower()
            if lowered.startswith("serial number:"):
                serial = line.split(":", 1)[1].strip()
            elif lowered.startswith("rotation rate:"):
                value = line.split(":", 1)[1].strip().lower()
                if "solid state" in value:
                    type_hint = "ssd"
                elif "rpm" in value:
                    type_hint = "hdd"
            elif "nvme version" in lowered:
                type_hint = "nvme"
        return {"serial": serial, "type_hint": type_hint}

    @staticmethod
    def _linux_type(name: str, transport: str, removable: bool, rotational: bool, smart_hint: str = "") -> str:
        lowered = name.lower()
        hint = smart_hint.lower()
        if removable or "usb" in transport:
            return "USB"
        if lowered.startswith("nvme") or "nvme" in transport or hint == "nvme":
            return "NVMe"
        if hint == "ssd":
            return "SSD"
        if hint == "hdd":
            return "HDD"
        if rotational:
            return "HDD"
        return "SSD"

    @staticmethod
    def _windows_type(model: str, media: str, interface: str) -> str:
        if "usb" in interface:
            return "USB"
        if "nvme" in model or "nvme" in media or "nvme" in interface:
            return "NVMe"
        if "ssd" in model or "ssd" in media:
            return "SSD"
        if "hdd" in media or "fixed hard disk" in media:
            return "HDD"
        return "UNKNOWN"

    @staticmethod
    def _to_int(value: object) -> int:
        try:
            return int(str(value).strip())
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _format_size(size_bytes: int) -> str:
        if size_bytes <= 0:
            return "0B"
        units = ["B", "KB", "MB", "GB", "TB", "PB"]
        size = float(size_bytes)
        unit_idx = 0
        while size >= 1024 and unit_idx < len(units) - 1:
            size /= 1024
            unit_idx += 1
        if unit_idx == 0:
            return f"{int(size)}{units[unit_idx]}"
        value = f"{size:.1f}".rstrip("0").rstrip(".")
        return f"{value}{units[unit_idx]}"

    def _run_command(self, command: Iterable[str], allow_failure: bool = False) -> str | None:
        command_list = list(command)
        try:
            result = subprocess.run(command_list, capture_output=True, text=True, check=True)
            return result.stdout
        except FileNotFoundError:
            if allow_failure:
                self.logger.debug("Optional command not available", extra={"command": command_list})
            else:
                self.logger.warning("Command not available", extra={"command": command_list})
            return None
        except subprocess.CalledProcessError as exc:
            level = self.logger.warning if allow_failure else self.logger.error
            level(
                "Command execution failed",
                extra={
                    "command": command_list,
                    "stderr": (exc.stderr or "").strip(),
                    "returncode": exc.returncode,
                },
            )
            return None
