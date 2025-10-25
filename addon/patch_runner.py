"""
Orchestration helpers that bridge scan results with automatic patching.
"""
from __future__ import annotations

import json
import os
from typing import Any, Callable, Dict, List, Optional

from . import auto_patch, utils

DEFAULT_CONFIG = {
    "auto_threshold": 3,
    "dry_run": True,
    "log_path": utils.LOG_PATH,
    "enforce_interval": 0.0,
}


def load_addon_config(path: Optional[str] = None) -> Dict[str, Any]:
    config_path = path or "addon_config.json"
    data = dict(DEFAULT_CONFIG)
    if os.path.exists(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as handle:
                loaded = json.load(handle)
                if isinstance(loaded, dict):
                    data.update(loaded)
        except Exception as exc:  # pragma: no cover
            print(f"Failed to read {config_path}: {exc}")
    return data


def _resolve_patch_value(
    args_value: Optional[float],
    config: Dict[str, Any],
    discovered_values: Dict[int, float],
) -> Optional[float]:
    if args_value is not None:
        return args_value
    config_value = config.get("patch_value")
    if config_value is not None:
        return float(config_value)
    if discovered_values:
        return float(next(iter(discovered_values.values())))
    return None


def _resolve_patch_type(
    args_type: Optional[str],
    config: Dict[str, Any],
    fallback_type: str,
) -> str:
    if args_type:
        return args_type
    if config.get("patch_type"):
        return config["patch_type"]
    return fallback_type


def should_auto_patch(addresses: List[int], threshold: int) -> bool:
    """Check whether the candidate count is within the allowed threshold."""
    count = len(addresses)
    return 0 < count <= max(1, threshold)


def execute_autopatch(
    context: Any,
    addresses: List[int],
    *,
    args: Any,
    value_type: str,
    discovered_values: Dict[int, float],
    describe_func: Callable[[int], str],
    read_func: Callable[[Any, int, int], bytes],
    config_path: Optional[str] = None,
) -> None:
    if not addresses:
        print("Addon autopatch requested, but no addresses are available.")
        return

    config = load_addon_config(config_path)
    threshold = (
        args.auto_threshold
        if getattr(args, "auto_threshold", None) is not None
        else int(config.get("auto_threshold", DEFAULT_CONFIG["auto_threshold"]))
    )
    if not should_auto_patch(addresses, threshold):
        print(
            f"Addon autopatch requires <= {threshold} addresses. Currently have {len(addresses)}."
        )
        return

    patch_value = _resolve_patch_value(args.patch_value, config, discovered_values)
    if patch_value is None:
        print("No patch value provided or inferred; skipping autopatch.")
        return

    patch_type = _resolve_patch_type(args.patch_type, config, value_type)
    utils.ensure_value_type(patch_type)

    if getattr(args, "dynamic", False) is False:
        print("Addon autopatch is only available after dynamic scans.")
        return

    dry_run = (
        args.addon_dry_run
        if getattr(args, "addon_dry_run", None) is not None
        else bool(config.get("dry_run", True))
    )
    log_path = config.get("log_path", utils.LOG_PATH)
    watch_interval = (
        args.enforce_interval
        if getattr(args, "enforce_interval", None) is not None
        else float(config.get("enforce_interval", 0.0))
    )

    print(
        f"Addon autopatch active for {len(addresses)} address(es); "
        f"target={patch_value} ({patch_type}) | dry_run={dry_run}"
    )
    if not dry_run:
        print(
            "WARNING: Writing to live process memory. Offline/singleplayer titles you own only."
        )
        if not auto_patch.require_write_confirmation():
            print("Addon autopatch aborted (confirmation missing).")
            return

    auto_patch.auto_apply_patch(
        context,
        addresses,
        patch_value,
        patch_type,
        read_callback=read_func,
        describe_func=describe_func,
        dry_run=dry_run,
        log_path=log_path,
        require_confirmation=False,
    )

    if watch_interval and watch_interval > 0:
        auto_patch.run_watch_patch_loop(
            context,
            addresses,
            patch_value,
            patch_type,
            interval=watch_interval,
            read_callback=read_func,
            describe_func=describe_func,
            dry_run=dry_run,
            log_path=log_path,
            require_confirmation=False,
        )
