"""
Automatic patching helpers for the Process Data Inspector addon.
"""
from __future__ import annotations

import ctypes
import time
from typing import Any, Callable, Dict, Iterable, List, Optional

from . import utils
from .utils import LOG_PATH

CONFIRMATION_PHRASE = "YES I OWN THIS COPY"
_confirmation_granted = False


def require_write_confirmation(prompt: Callable[[str], str] = input) -> bool:
    """Ensure the user explicitly consents before any write."""
    global _confirmation_granted
    if _confirmation_granted:
        return True
    user = prompt(
        'Type "YES I OWN THIS COPY" to enable memory patching (or press Enter to cancel): '
    ).strip()
    if user == CONFIRMATION_PHRASE:
        _confirmation_granted = True
        return True
    print("Memory patching disabled (confirmation phrase not provided).")
    return False


def _write_mock_memory(context: Any, address: int, data: bytes) -> None:
    size = len(data)
    for region in getattr(context, "mock_regions", []):
        start = region.base_address
        end = start + region.size
        if start <= address <= end - size:
            buf = context.mock_data[start]
            offset = address - start
            buf[offset : offset + size] = data
            return
    raise ValueError(f"Mock write outside of allocated regions at 0x{address:X}")


def _write_process_memory(context: Any, address: int, data: bytes) -> None:
    handle = getattr(context, "handle", None)
    if handle is None:
        raise RuntimeError("Process handle missing; cannot write memory.")
    size = len(data)
    written = ctypes.c_size_t(0)
    success = ctypes.windll.kernel32.WriteProcessMemory(
        handle,
        ctypes.c_void_p(address),
        ctypes.c_char_p(data),
        size,
        ctypes.byref(written),
    )
    if not success or written.value != size:
        raise OSError(f"Failed to write process memory at 0x{address:X}")


def write_process_value(
    context: Any,
    address: int,
    value: float,
    value_type: str,
    *,
    read_callback: Optional[Callable[[Any, int, int], bytes]] = None,
    describe_func: Optional[Callable[[int], str]] = None,
    dry_run: bool = True,
    log_path: str = LOG_PATH,
    require_confirmation: bool = True,
) -> Dict[str, Any]:
    """Write a numeric value to the target process (or simulate in mock mode)."""
    label = utils.format_address_label(address, describe_func)
    packed = utils.pack_value(value, value_type)
    result: Dict[str, Any] = {
        "address": address,
        "label": label,
        "value": value,
        "value_type": value_type,
        "dry_run": dry_run,
        "success": False,
        "verified": False,
        "error": None,
    }
    if require_confirmation and not require_write_confirmation():
        result["error"] = "confirmation_missing"
        utils.log_patch_attempt(
            log_path, {**result, "action": "skip", "reason": "confirmation_missing"}
        )
        return result

    try:
        if dry_run:
            print(f"[DRY RUN] Would patch {label} -> {value} ({value_type}).")
            result["success"] = True
        else:
            if getattr(context, "mock", False):
                _write_mock_memory(context, address, packed)
            else:
                _write_process_memory(context, address, packed)
            result["success"] = True
            if read_callback:
                verification = utils.read_value(
                    context, address, value_type, read_callback
                )
                result["verified"] = abs(verification - float(value)) < 1e-4
            print(
                f"Patched {label} -> {value} ({value_type}) | verified={result['verified']}"
            )
    except Exception as exc:  # pragma: no cover
        result["error"] = str(exc)
        print(f"Patch failed for {label}: {exc}")

    utils.log_patch_attempt(
        log_path,
        {
            **result,
            "action": "write" if not dry_run else "dry_run",
        },
    )
    return result


def auto_apply_patch(
    context: Any,
    addresses: Iterable[int],
    value: float,
    value_type: str,
    *,
    read_callback: Optional[Callable[[Any, int, int], bytes]] = None,
    describe_func: Optional[Callable[[int], str]] = None,
    dry_run: bool = True,
    log_path: str = LOG_PATH,
    require_confirmation: bool = True,
) -> List[Dict[str, Any]]:
    """Apply the requested value to multiple addresses."""
    results = []
    for address in addresses:
        results.append(
            write_process_value(
                context,
                address,
                value,
                value_type,
                read_callback=read_callback,
                describe_func=describe_func,
                dry_run=dry_run,
                log_path=log_path,
                require_confirmation=require_confirmation and not dry_run,
            )
        )
    return results


def run_watch_patch_loop(
    context: Any,
    addresses: Iterable[int],
    value: float,
    value_type: str,
    *,
    interval: float,
    read_callback: Optional[Callable[[Any, int, int], bytes]] = None,
    describe_func: Optional[Callable[[int], str]] = None,
    dry_run: bool = True,
    log_path: str = LOG_PATH,
    require_confirmation: bool = False,
) -> None:
    """Continuously enforce a value every N seconds until interrupted."""
    print(
        f"Entering watch mode (interval={interval}s). Press Ctrl+C to stop enforcement."
    )
    try:
        while True:
            auto_apply_patch(
                context,
                addresses,
                value,
                value_type,
                read_callback=read_callback,
                describe_func=describe_func,
                dry_run=dry_run,
                log_path=log_path,
                require_confirmation=require_confirmation,
            )
            time.sleep(max(0.1, interval))
    except KeyboardInterrupt:
        print("Watch mode stopped.")
