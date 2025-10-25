"""
Shared helpers for the Process Data Inspector addon subsystem.
"""
from __future__ import annotations

import ctypes
import datetime as dt
import os
import struct
from typing import Any, Callable, Dict, Optional

VALUE_TYPES: Dict[str, str] = {
    "int32": "<i",
    "int64": "<q",
    "float": "<f",
    "double": "<d",
}

LOG_PATH = "addon_patch_log.txt"


def ensure_value_type(value_type: str) -> str:
    """Validate an incoming value type token."""
    if value_type not in VALUE_TYPES:
        raise ValueError(f"Unsupported patch value type '{value_type}'.")
    return value_type


def pack_value(value: float, value_type: str) -> bytes:
    fmt = VALUE_TYPES[ensure_value_type(value_type)]
    if value_type.startswith("int"):
        coerced = int(round(value))
    else:
        coerced = float(value)
    return struct.pack(fmt, coerced)


def unpack_value(raw: bytes, value_type: str) -> float:
    fmt = VALUE_TYPES[ensure_value_type(value_type)]
    (value,) = struct.unpack(fmt, raw)
    return float(value)


def _default_read_memory(context: Any, address: int, size: int) -> bytes:
    """Fallback memory reader that handles mock and real processes."""
    if getattr(context, "mock", False):
        for region in getattr(context, "mock_regions", []):
            start = region.base_address
            end = start + region.size
            if start <= address <= end - size:
                block = context.mock_data[start]
                offset = address - start
                return bytes(block[offset : offset + size])
        raise ValueError(f"Mock read outside known regions at 0x{address:X}")

    handle = getattr(context, "handle", None)
    if handle is None:
        raise RuntimeError("Process handle unavailable for read.")
    buffer = (ctypes.c_ubyte * size)()
    read = ctypes.c_size_t(0)
    success = ctypes.windll.kernel32.ReadProcessMemory(
        handle,
        ctypes.c_void_p(address),
        ctypes.byref(buffer),
        size,
        ctypes.byref(read),
    )
    if not success:
        raise OSError(f"Failed to read memory at 0x{address:X}")
    return bytes(buffer[: read.value])


def read_value(
    context: Any,
    address: int,
    value_type: str,
    read_callback: Optional[Callable[[Any, int, int], bytes]] = None,
) -> float:
    """Read a typed value via the provided reader or default accessor."""
    size = struct.calcsize(VALUE_TYPES[ensure_value_type(value_type)])
    reader = read_callback or _default_read_memory
    raw = reader(context, address, size)
    return unpack_value(raw, value_type)


def format_address_label(
    address: int,
    describe_func: Optional[Callable[[int], str]] = None,
) -> str:
    """Render module+offset if possible, otherwise hexadecimal address."""
    if describe_func:
        try:
            return describe_func(address)
        except Exception:
            pass
    return f"0x{address:X}"


def log_patch_attempt(path: str, payload: Dict[str, Any]) -> None:
    """Append a structured log line for each patch attempt."""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    timestamp = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    payload = dict(payload)
    payload["timestamp"] = timestamp
    line = " | ".join(f"{key}={value}" for key, value in payload.items())
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(line + os.linesep)
