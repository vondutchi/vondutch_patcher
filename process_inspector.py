#!/usr/bin/env python3
"""
Terminal-based process data inspector for educational, offline debugging.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import platform
import struct
import sys
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple
import textwrap

try:
    from addon import auto_patch, patch_runner
except ImportError:
    auto_patch = None
    patch_runner = None

import psutil
from tqdm import tqdm

IS_WINDOWS = platform.system() == "Windows"

try:
    import ctypes
    from ctypes import wintypes
except ImportError:  # pragma: no cover - ctypes is part of stdlib but guarded for completeness
    ctypes = None  # type: ignore


# ----- Windows helpers -----------------------------------------------------

PAGE_GUARD = 0x100
PAGE_NOACCESS = 0x01
MEM_COMMIT = 0x1000
READABLE_PROTECTIONS = {
    0x02,  # PAGE_READONLY
    0x04,  # PAGE_READWRITE
    0x08,  # PAGE_WRITECOPY
    0x20,  # PAGE_EXECUTE_READ
    0x40,  # PAGE_EXECUTE_READWRITE
    0x80,  # PAGE_EXECUTE_WRITECOPY
}

PROCESS_QUERY_INFORMATION = 0x0400
PROCESS_VM_READ = 0x0010
PROCESS_VM_WRITE = 0x0020
PROCESS_VM_OPERATION = 0x0008


@dataclass
class Region:
    base_address: int
    size: int
    protect: int
    state: int
    type: int
    description: str = ""


@dataclass
class ModuleInfo:
    path: str
    base_address: int
    size: int


@dataclass
class ScanContext:
    pid: int
    name: str
    pointer_size: int
    handle: Optional[int] = None
    modules: List[ModuleInfo] = field(default_factory=list)
    mock: bool = False
    mock_regions: List[Region] = field(default_factory=list)
    mock_data: Dict[int, bytearray] = field(default_factory=dict)
    mock_dynamic_addr: Optional[int] = None
    mock_dynamic_type: str = "int32"
    mock_dynamic_value: float = 0.0
    mock_dynamic_step: float = -1.0


def warn_banner() -> None:
    """Show mandatory offline/legal warning and require confirmation."""
    banner = r"""
=====================================================================
   PROCESS DATA INSPECTOR - OFFLINE/SINGLEPLAYER USE ONLY

   This tool exists solely for debugging, modding, or educational
   reverse engineering of software YOU OWN on YOUR machine.
   It must never be used against multiplayer titles or other people's
   software. Proceed only if you accept full responsibility.
=====================================================================
"""
    print(banner)
    answer = input("Type YES to confirm you understand and comply: ").strip()
    if answer.upper() != "YES":
        print("Confirmation missing. Exiting.")
        sys.exit(1)


# ----- Process enumeration -------------------------------------------------


def list_processes(limit: int = 25) -> List[Dict[str, Any]]:
    """Return a list of running processes sorted by RSS size."""
    processes: List[Dict[str, Any]] = []
    for proc in psutil.process_iter(["pid", "name", "exe", "memory_info"]):
        try:
            info = proc.info
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
        mem = info.get("memory_info")
        rss = getattr(mem, "rss", 0) if mem else 0
        processes.append(
            {
                "pid": info.get("pid"),
                "name": info.get("name") or "unknown",
                "exe": info.get("exe") or "",
                "rss": rss,
            }
        )
    processes.sort(key=lambda item: item["rss"], reverse=True)
    return processes[:limit] if limit else processes


def format_size(num: int) -> str:
    """Printable memory size."""
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if num < 1024:
            return f"{num:.1f}{unit}"
        num /= 1024
    return f"{num:.1f}PB"


def select_process_interactive() -> int:
    """Prompt the user to pick a process."""
    print("\nGathering running processes...")
    processes = list_processes(limit=40)
    if not processes:
        raise RuntimeError("No processes found.")
    for idx, proc in enumerate(processes, 1):
        exe = proc["exe"] or "(path unavailable)"
        print(
            f"[{idx:02d}] PID {proc['pid']:>6}  {format_size(proc['rss']):>8}  "
            f"{proc['name']:<25} {exe}"
        )
    while True:
        choice = input("Select process by number (or PID): ").strip()
        if not choice:
            continue
        if choice.isdigit():
            number = int(choice)
            if 1 <= number <= len(processes):
                return int(processes[number - 1]["pid"])
        try:
            pid = int(choice)
            if psutil.pid_exists(pid):
                return pid
        except ValueError:
            pass
        print("Invalid selection. Try again.")


# ----- Memory helpers ------------------------------------------------------


def open_process_handle(pid: int) -> int:
    """Open a Windows process handle with read permissions."""
    if not IS_WINDOWS or ctypes is None:
        raise RuntimeError("OpenProcess is only available on Windows.")
    kernel32 = ctypes.windll.kernel32
    handle = kernel32.OpenProcess(
        PROCESS_QUERY_INFORMATION | PROCESS_VM_READ | PROCESS_VM_WRITE | PROCESS_VM_OPERATION,
        False,
        pid,
    )
    if not handle:
        raise PermissionError(f"Failed to open process {pid}. Try running as Administrator.")
    return handle


def close_handle(handle: Optional[int]) -> None:
    if handle and IS_WINDOWS and ctypes is not None:
        ctypes.windll.kernel32.CloseHandle(handle)


def fetch_modules(pid: int) -> List[ModuleInfo]:
    """Collect module base addresses using psutil."""
    modules: List[ModuleInfo] = []
    try:
        proc = psutil.Process(pid)
        for mmap in proc.memory_maps(grouped=False):
            addr_range = mmap.addr.split("-")
            try:
                base = int(addr_range[0], 16)
                upper = int(addr_range[1], 16)
                size = max(0, upper - base)
            except (ValueError, IndexError):
                base = 0
                size = 0
            modules.append(ModuleInfo(path=mmap.path or "unknown", base_address=base, size=size))
    except (psutil.AccessDenied, psutil.NoSuchProcess):
        pass
    modules.sort(key=lambda m: m.base_address)
    return modules


def describe_address(address: int, modules: Sequence[ModuleInfo]) -> str:
    """Return module+offset notation if possible."""
    for module in modules:
        if module.base_address <= address < module.base_address + module.size:
            offset = address - module.base_address
            base_name = os.path.basename(module.path) or module.path
            return f"{base_name}+0x{offset:X}"
    return f"0x{address:X}"


def read_regions(context: ScanContext) -> List[Region]:
    """Enumerate readable and committed memory regions."""
    if context.mock:
        return context.mock_regions

    if not IS_WINDOWS or ctypes is None:
        raise RuntimeError("Memory enumeration requires Windows.")

    class MEMORY_BASIC_INFORMATION(ctypes.Structure):  # type: ignore
        _fields_ = [
            ("BaseAddress", ctypes.c_void_p),
            ("AllocationBase", ctypes.c_void_p),
            ("AllocationProtect", wintypes.DWORD),
            ("RegionSize", ctypes.c_size_t),
            ("State", wintypes.DWORD),
            ("Protect", wintypes.DWORD),
            ("Type", wintypes.DWORD),
        ]

    kernel32 = ctypes.windll.kernel32
    regions: List[Region] = []
    addr = 0
    mbi = MEMORY_BASIC_INFORMATION()

    def to_int(value: Any) -> int:
        """Safely coerce ctypes scalars to Python ints."""
        if hasattr(value, "value"):
            inner = value.value
            return int(inner) if inner is not None else 0
        if value is None:
            return 0
        return int(value)

    while kernel32.VirtualQueryEx(
        context.handle, ctypes.c_void_p(addr), ctypes.byref(mbi), ctypes.sizeof(mbi)
    ):
        base = to_int(mbi.BaseAddress)
        size = to_int(mbi.RegionSize)
        state = to_int(mbi.State)
        protect = to_int(mbi.Protect)
        readable = (protect & PAGE_GUARD) == 0 and (protect in READABLE_PROTECTIONS)
        if state == MEM_COMMIT and readable and size:
            regions.append(Region(base, size, protect, state, to_int(mbi.Type)))
        addr = base + size
        if addr > (1 << (context.pointer_size * 8)) - 1:
            break
    return regions


def read_process_memory(context: ScanContext, address: int, size: int) -> bytes:
    """Read raw bytes from the target process or mock memory."""
    if context.mock:
        for region in context.mock_regions:
            if region.base_address <= address < region.base_address + region.size:
                offset = address - region.base_address
                block = context.mock_data[region.base_address]
                return bytes(block[offset : offset + size])
        raise ValueError(f"Mock address 0x{address:X} outside generated regions.")

    if not IS_WINDOWS or ctypes is None or not context.handle:
        raise RuntimeError("Process reading requires Windows and a valid handle.")
    buffer = (ctypes.c_ubyte * size)()
    bytes_read = ctypes.c_size_t(0)
    success = ctypes.windll.kernel32.ReadProcessMemory(
        context.handle,
        ctypes.c_void_p(address),
        ctypes.byref(buffer),
        size,
        ctypes.byref(bytes_read),
    )
    if not success:
        raise OSError(f"Could not read memory at 0x{address:X}")
    return bytes(buffer[: bytes_read.value])


# ----- Value search --------------------------------------------------------

VALUE_FORMATS = {
    "int32": ("<i", 4),
    "uint32": ("<I", 4),
    "int64": ("<q", 8),
    "uint64": ("<Q", 8),
    "float": ("<f", 4),
    "double": ("<d", 8),
}


def normalize_for_type(value: float, value_type: str) -> float:
    """Cast the supplied value appropriately for struct packing."""
    if value_type in {"float", "double"}:
        return float(value)
    return int(round(value))


def write_mock_value(context: ScanContext, address: int, value_type: str, value: float) -> None:
    """Update a mock memory address with the supplied value."""
    if not context.mock:
        return
    if value_type not in VALUE_FORMATS:
        return
    fmt, size = VALUE_FORMATS[value_type]
    coerced = normalize_for_type(value, value_type)
    packed = struct.pack(fmt, coerced)
    for region in context.mock_regions:
        start = region.base_address
        end = start + region.size
        if start <= address <= end - size:
            block = context.mock_data[start]
            offset = address - start
            block[offset : offset + size] = packed
            return


def advance_mock_dynamic_value(context: ScanContext, value_type: str) -> None:
    """Simulate a predictable value change during mock dynamic scans."""
    if not context.mock or context.mock_dynamic_addr is None:
        return
    if value_type != context.mock_dynamic_type:
        return
    next_value = context.mock_dynamic_value + context.mock_dynamic_step
    context.mock_dynamic_value = next_value
    write_mock_value(context, context.mock_dynamic_addr, value_type, next_value)


def pack_value(value: float, fmt_key: str) -> bytes:
    if fmt_key not in VALUE_FORMATS:
        raise ValueError(f"Unsupported value type '{fmt_key}'.")
    fmt, _ = VALUE_FORMATS[fmt_key]
    try:
        return struct.pack(fmt, value)
    except struct.error as exc:
        raise ValueError(str(exc)) from exc


def search_values(
    context: ScanContext,
    regions: Sequence[Region],
    target_value: float,
    value_type: str,
) -> List[int]:
    """Scan readable regions for the requested value."""
    pattern = pack_value(target_value, value_type)
    size = len(pattern)
    found: List[int] = []
    for region in tqdm(regions, desc="Scanning memory", unit="region"):
        chunk_size = 0x4000
        offset = 0
        while offset < region.size:
            to_read = min(chunk_size, region.size - offset)
            address = region.base_address + offset
            try:
                data = read_process_memory(context, address, to_read)
            except Exception:
                offset += to_read
                continue
            idx = data.find(pattern)
            while idx != -1:
                found_addr = address + idx
                found.append(found_addr)
                idx = data.find(pattern, idx + 1)
            offset += to_read
    return found


def rescan(
    context: ScanContext,
    addresses: Sequence[int],
    expected_value: float,
    value_type: str,
) -> Dict[int, bool]:
    """Check whether the previously found addresses still hold the expected value."""
    fmt, size = VALUE_FORMATS[value_type]
    packed = struct.pack(fmt, expected_value)
    results: Dict[int, bool] = {}
    for addr in tqdm(addresses, desc="Rescanning", unit="addr"):
        try:
            data = read_process_memory(context, addr, size)
        except Exception:
            results[addr] = False
            continue
        results[addr] = data == packed
    return results


# ----- Snapshot/dynamic scanning -------------------------------------------

SNAPSHOT_WARN_SECONDS = 6.0


def take_snapshot(
    context: ScanContext,
    regions: Sequence[Region],
    value_type: str,
    chunk_size: int,
) -> Dict[int, float]:
    """Capture a mapping of address->value for the given numeric type."""
    if value_type not in VALUE_FORMATS:
        raise ValueError(f"Unsupported value type '{value_type}'.")
    fmt, size = VALUE_FORMATS[value_type]
    snapshot: Dict[int, float] = {}
    for region in tqdm(regions, desc="Snapshot", unit="region"):
        offset = 0
        while offset < region.size:
            to_read = min(chunk_size, region.size - offset)
            address = region.base_address + offset
            try:
                data = read_process_memory(context, address, to_read)
            except Exception:
                offset += to_read
                continue
            usable = len(data) - (len(data) % size)
            for idx in range(0, usable, size):
                raw = data[idx : idx + size]
                value = struct.unpack(fmt, raw)[0]
                snapshot[address + idx] = value
            offset += to_read
    return snapshot


def compare_snapshots(
    previous: Dict[int, float],
    current: Dict[int, float],
) -> Dict[int, Tuple[float, float]]:
    """Produce a dictionary of addresses mapped to (old, new) tuples."""
    comparisons: Dict[int, Tuple[float, float]] = {}
    if len(previous) <= len(current):
        for addr, old_value in previous.items():
            if addr in current:
                comparisons[addr] = (old_value, current[addr])
    else:
        for addr, new_value in current.items():
            if addr in previous:
                comparisons[addr] = (previous[addr], new_value)
    return comparisons


def filter_snapshot_by_regions(
    snapshot: Dict[int, float],
    regions: Sequence[Region],
) -> Dict[int, float]:
    """Restrict snapshot entries to the supplied region list."""
    allowed_ranges = [(r.base_address, r.base_address + r.size) for r in regions]
    if not allowed_ranges:
        return {}
    filtered: Dict[int, float] = {}
    for addr, value in snapshot.items():
        for start, end in allowed_ranges:
            if start <= addr < end:
                filtered[addr] = value
                break
    return filtered


def values_equal(old: float, new: float, value_type: str) -> bool:
    """Equality helper with tolerance for floating-point types."""
    if value_type in {"float", "double"}:
        return abs(new - old) <= 1e-5 if value_type == "float" else abs(new - old) <= 1e-9
    return new == old


def filter_candidates(
    comparisons: Dict[int, Tuple[float, float]],
    relation: str,
    value_type: str,
) -> Dict[int, float]:
    """Keep only addresses whose values satisfy the requested relation."""
    filtered: Dict[int, float] = {}
    for addr, (old_value, new_value) in comparisons.items():
        if relation == "increase" and new_value > old_value:
            filtered[addr] = new_value
        elif relation == "decrease" and new_value < old_value:
            filtered[addr] = new_value
        elif relation == "same" and values_equal(old_value, new_value, value_type):
            filtered[addr] = new_value
    return filtered


def prompt_region_reduction(regions: Sequence[Region]) -> List[Region]:
    """Allow the user to narrow the region set."""
    if not regions:
        return []
    print("Enter address bounds (hex or decimal) to limit the scan.")
    start_raw = input("  Start address (leave blank to keep current minimum): ").strip()
    end_raw = input("  End address (leave blank to keep current maximum): ").strip()

    def parse_bound(raw: str, default: Optional[int]) -> Optional[int]:
        if not raw:
            return default
        try:
            return int(raw, 0)
        except ValueError:
            print("  Invalid number. Keeping default.")
            return default

    overall_start = min(r.base_address for r in regions)
    overall_end = max(r.base_address + r.size for r in regions)
    start_bound = parse_bound(start_raw, overall_start)
    end_bound = parse_bound(end_raw, overall_end)
    if start_bound is None or end_bound is None or start_bound >= end_bound:
        print("  Bounds unchanged.")
        return list(regions)

    trimmed = [
        r
        for r in regions
        if r.base_address < end_bound and (r.base_address + r.size) > start_bound
    ]
    if not trimmed:
        print("  No regions match the requested range. Keeping existing set.")
        return list(regions)
    print(f"  Region count reduced from {len(regions)} to {len(trimmed)}.")
    return trimmed


def prompt_trend() -> Optional[str]:
    """Ask the user whether the target value increased, decreased, or stayed the same."""
    mapping = {"i": "increase", "d": "decrease", "s": "same", "q": "quit"}
    while True:
        choice = input("Did the target value increase, decrease, or stay the same? i/d/s (q to quit): ").strip().lower()
        if not choice:
            continue
        if choice in mapping:
            relation = mapping[choice]
            if relation == "quit":
                return None
            return relation
        print("Please enter i, d, s, or q.")


def run_dynamic_scan_loop(
    context: ScanContext,
    args: argparse.Namespace,
    regions: Sequence[Region],
) -> Dict[str, Any]:
    """Execute the automated next-scan style workflow."""
    if not regions:
        raise RuntimeError("No readable regions available for dynamic scan.")
    default_dynamic_type = (
        context.mock_dynamic_type if context.mock and context.mock_dynamic_type in VALUE_FORMATS else "float"
    )
    value_type = args.value_kind or default_dynamic_type
    chunk_size = max(args.chunk_size, VALUE_FORMATS[value_type][1])
    max_steps = args.max_steps or 0

    print("\nDynamic scan mode initialized. Offline/singleplayer targets only.")
    print("Snapshotting baseline values...")
    baseline_regions = list(regions)
    previous_snapshot = take_snapshot(context, baseline_regions, value_type, chunk_size)
    candidates: Optional[Dict[int, float]] = None
    step_counter = 0

    while True:
        if max_steps and step_counter >= max_steps:
            print("Reached maximum scan steps.")
            candidates = None
            break
        step_counter += 1
        print(f"\nStep {step_counter}:")
        print("Perform your in-game action (shoot, jump, take damage, spend ammo).")
        print("Reminder: this tool is for software you own in offline/singleplayer contexts.")
        ready = input("Press Enter when ready for the next scan step (or type q to quit): ").strip().lower()
        if ready == "q":
            candidates = None
            break
        if context.mock:
            advance_mock_dynamic_value(context, value_type)
        start_time = time.time()
        next_snapshot = take_snapshot(context, baseline_regions, value_type, chunk_size)
        duration = time.time() - start_time
        if duration >= SNAPSHOT_WARN_SECONDS:
            reduce = input("Reduce memory range? y/n: ").strip().lower()
            if reduce == "y":
                baseline_regions = prompt_region_reduction(baseline_regions)
                previous_snapshot = filter_snapshot_by_regions(previous_snapshot, baseline_regions)
                next_snapshot = filter_snapshot_by_regions(next_snapshot, baseline_regions)

        if candidates is None:
            comparisons = compare_snapshots(previous_snapshot, next_snapshot)
        else:
            comparisons = {
                addr: (old_value, next_snapshot.get(addr, old_value))
                for addr, old_value in candidates.items()
                if addr in next_snapshot
            }
        if not comparisons:
            print("No comparable addresses found. Try a more dramatic in-game action.")
            previous_snapshot = next_snapshot
            continue

        relation = prompt_trend()
        if relation is None:
            candidates = None
            break
        candidates = filter_candidates(comparisons, relation, value_type)
        count = len(candidates)
        print(f"{count} candidate address(es) remain after filtering.")
        if count <= 3 and count > 0:
            print("Potential matches narrowed sufficiently:")
            for addr, value in candidates.items():
                print(f"  {describe_address(addr, context.modules)} -> {value}")
            break
        if count == 0:
            print("No addresses match the specified trend. Restarting from current snapshot.")
            candidates = None
            previous_snapshot = next_snapshot
            continue

        previous_snapshot = next_snapshot

    final_addresses = sorted(candidates.keys()) if candidates else []
    return {
        "addresses": final_addresses,
        "values": candidates or {},
        "value_type": value_type,
        "regions": baseline_regions,
        "steps": step_counter,
    }


# ----- Reference tracing ---------------------------------------------------

def find_pointer_references(
    context: ScanContext,
    regions: Sequence[Region],
    target: int,
) -> List[int]:
    """Search for raw pointers that reference the supplied address."""
    pointer_size = context.pointer_size
    target_bytes = target.to_bytes(pointer_size, byteorder="little", signed=False)
    refs: List[int] = []
    for region in regions:
        chunk_size = 0x4000
        offset = 0
        while offset + pointer_size <= region.size:
            to_read = min(chunk_size, region.size - offset)
            address = region.base_address + offset
            try:
                data = read_process_memory(context, address, to_read)
            except Exception:
                offset += to_read
                continue
            for idx in range(0, len(data) - pointer_size + 1, pointer_size):
                if data[idx : idx + pointer_size] == target_bytes:
                    refs.append(address + idx)
            offset += to_read
    return refs


def trace_references(
    context: ScanContext,
    regions: Sequence[Region],
    seeds: Sequence[int],
    max_depth: int = 3,
) -> List[List[int]]:
    """Build pointer chains pointing to the seed addresses."""
    chains: List[List[int]] = []
    frontier = {addr: [[addr]] for addr in seeds}
    depth = 0
    while frontier and depth < max_depth:
        next_frontier: Dict[int, List[List[int]]] = {}
        for target, existing_paths in tqdm(
            frontier.items(), desc=f"Tracing depth {depth+1}", unit="addr"
        ):
            refs = find_pointer_references(context, regions, target)
            for ref in refs:
                for path in existing_paths:
                    new_path = [ref] + path
                    chains.append(new_path)
                    next_frontier.setdefault(ref, []).append(new_path)
        frontier = next_frontier
        depth += 1
    return chains


# ----- Pattern generation --------------------------------------------------

def generate_pattern(
    context: ScanContext,
    address: int,
    window: int = 32,
) -> Dict[str, Any]:
    """Grab surrounding bytes and convert them into a masked pattern."""
    half = window // 2
    start = max(address - half, 0)
    try:
        data = read_process_memory(context, start, window)
    except Exception:
        data = b""

    hex_bytes = []
    mask_chars = []
    for byte in data:
        hex_bytes.append(f"{byte:02X}")
        mask_chars.append("x")
    pattern = " ".join(hex_bytes) if hex_bytes else ""
    mask = "".join(mask_chars) if mask_chars else ""
    return {
        "address": address,
        "start": start,
        "pattern": pattern,
        "mask": mask,
    }


# ----- Persistence ---------------------------------------------------------

def save_results(payload: Dict[str, Any], output_path: str) -> None:
    with open(output_path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2)
    print(f"Results saved to {output_path}")


def load_results(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


# ----- Mock mode -----------------------------------------------------------

def build_mock_context() -> ScanContext:
    """Create deterministic fake memory layout for demo purposes."""
    pointer_size = 8
    regions: List[Region] = []
    data_map: Dict[int, bytearray] = {}
    base1 = 0x10000000
    base2 = 0x20000000
    region1 = bytearray(0x2000)
    region2 = bytearray(0x2000)
    struct.pack_into("<f", region1, 0x400, 3.14159)
    struct.pack_into("<I", region1, 0x800, 123456)
    dynamic_addr = base1 + 0x900
    struct.pack_into("<i", region1, 0x900, 30)
    # pointers
    addr_value = base1 + 0x400
    struct.pack_into("<Q", region2, 0x100, addr_value)
    struct.pack_into("<Q", region2, 0x108, base2 + 0x100)
    regions.append(Region(base1, len(region1), 0, MEM_COMMIT, 0, "mock-region-1"))
    regions.append(Region(base2, len(region2), 0, MEM_COMMIT, 0, "mock-region-2"))
    data_map[base1] = region1
    data_map[base2] = region2
    return ScanContext(
        pid=9999,
        name="mock-process",
        pointer_size=pointer_size,
        mock=True,
        mock_regions=regions,
        mock_data=data_map,
        mock_dynamic_addr=dynamic_addr,
        mock_dynamic_type="int32",
        mock_dynamic_value=30,
        mock_dynamic_step=-1,
    )


# ----- Core flow -----------------------------------------------------------

def prompt_value_type(default: str = "float") -> str:
    options = "/".join(VALUE_FORMATS.keys())
    while True:
        choice = input(f"Value type [{default}] ({options}): ").strip().lower()
        if not choice:
            return default
        if choice in VALUE_FORMATS:
            return choice
        print("Unknown type. Please choose a supported value type.")


def prompt_value() -> float:
    while True:
        raw = input("Enter numeric or floating-point value to search for: ").strip()
        try:
            return float(raw)
        except ValueError:
            print("Please enter a valid number.")


def construct_context(pid: int, mock: bool) -> ScanContext:
    if mock:
        return build_mock_context()
    proc = psutil.Process(pid)
    name = proc.name()
    pointer_size = struct.calcsize("P")
    handle = open_process_handle(pid)
    modules = fetch_modules(pid)
    return ScanContext(pid=pid, name=name, pointer_size=pointer_size, handle=handle, modules=modules)


def interactive_scan(context: ScanContext, args: argparse.Namespace) -> Dict[str, Any]:
    """Drive the scanning workflow."""
    regions = read_regions(context)
    if not regions:
        raise RuntimeError("No readable regions discovered.")
    print(f"Identified {len(regions)} readable regions.")

    scan_mode = "dynamic" if args.dynamic else "manual"
    addresses: List[int] = []
    rescan_results: Dict[int, bool] = {}
    pointer_chains: List[List[int]] = []
    signatures: List[Dict[str, Any]] = []
    final_values: Dict[int, float] = {}
    target_value: Optional[float] = None

    if args.dynamic:
        dynamic_result = run_dynamic_scan_loop(context, args, list(regions))
        addresses = dynamic_result.get("addresses", [])
        final_values = dynamic_result.get("values", {})
        value_type = dynamic_result.get("value_type", args.value_kind or "float")
        target_value = None
        if not addresses:
            print("Dynamic scan ended without enough candidates.")
            return {}
        rescan_results = {addr: True for addr in addresses}
        run_extras = (
            input("Run reference tracing and signature generation now? y/n: ").strip().lower() == "y"
        )
    else:
        value_type = args.value_type or prompt_value_type()
        target_value = args.value if args.value is not None else prompt_value()
        print(f"Searching for {target_value} ({value_type})...")
        addresses = search_values(context, regions, target_value, value_type)
        if not addresses:
            print("No matching values found.")
        else:
            print(f"Found {len(addresses)} candidate address(es).")
            for idx, addr in enumerate(addresses[:10], 1):
                print(f"  [{idx}] {describe_address(addr, context.modules)}")
            if len(addresses) > 10:
                print("  ...")

        if addresses and args.allow_rescan:
            input("Change the value in your target software, then press Enter to rescan...")
            rescan_results = rescan(context, addresses, target_value, value_type)
            still_valid = [addr for addr, ok in rescan_results.items() if ok]
            print(f"{len(still_valid)}/{len(addresses)} addresses still match after rescan.")
        final_values = {addr: target_value for addr in addresses}
        run_extras = True

    if addresses and run_extras:
        pointer_chains = trace_references(context, regions, addresses, max_depth=args.reference_depth)
        print(f"Discovered {len(pointer_chains)} pointer chain(s).")
        for addr in addresses[: min(5, len(addresses))]:
            signatures.append(generate_pattern(context, addr))
    elif addresses and not run_extras:
        print("Skipping pointer tracing and signature generation per user request.")

    if addresses and getattr(args, "use_addon", False):
        if not args.dynamic:
            print("Addon autopatch requires --dynamic scans; skipping addon processing.")
        elif patch_runner is None:
            print("Addon subsystem not available. Install the /addon package to enable autopatching.")
        else:
            try:
                patch_runner.execute_autopatch(
                    context,
                    addresses,
                    args=args,
                    value_type=value_type,
                    discovered_values=final_values,
                    describe_func=lambda addr: describe_address(addr, context.modules),
                    read_func=read_process_memory,
                    config_path=args.addon_config,
                )
            except Exception as exc:
                print(f"Addon autopatch failed: {exc}")

    payload = {
        "process": {
            "pid": context.pid,
            "name": context.name,
        },
        "timestamp": dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z"),
        "value": target_value,
        "value_type": value_type,
        "scan_mode": scan_mode,
        "addresses": [
            {
                "address": addr,
                "label": describe_address(addr, context.modules),
                "still_valid": rescan_results.get(addr),
                "current_value": final_values.get(addr),
            }
            for addr in addresses
        ],
        "references": [
            {
                "chain": [describe_address(a, context.modules) for a in chain],
            }
            for chain in pointer_chains
        ],
        "signatures": signatures,
    }
    return payload


def display_saved_results(data: Dict[str, Any]) -> None:
    print("\nLoaded previous results:")
    proc = data.get("process", {})
    print(f"  Process: {proc.get('name')} (PID {proc.get('pid')})")
    print(f"  Timestamp: {data.get('timestamp')}")
    print(f"  Value: {data.get('value')} ({data.get('value_type')})")
    addresses = data.get("addresses", [])
    print(f"  Stored addresses: {len(addresses)}")
    for entry in addresses[:5]:
        print(f"    - {entry.get('label')} -> {entry.get('address')}")
    if len(addresses) > 5:
        print("    ...")
    print(f"  Pointer chains stored: {len(data.get('references', []))}")


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Inspect and trace process memory for offline debugging.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent(
            """\
Examples:
  python process_inspector.py --pid 4242 --dynamic --type int32 --max-steps 5
  python process_inspector.py --pid 4242 --dynamic --use-addon --patch-value 50 --patch-type int32 --auto-threshold 3 --enforce-interval 2
  python process_inspector.py --mock --dynamic --use-addon --dry-run
"""
        ),
    )
    parser.add_argument("--pid", type=int, help="PID of the target process.")
    parser.add_argument("--mock", action="store_true", help="Run in mock/demo mode.")
    parser.add_argument("--value-type", choices=VALUE_FORMATS.keys(), help="Value type to search for.")
    parser.add_argument("--value", type=float, help="Numeric value to search for.")
    parser.add_argument("--save", default="scan_results.json", help="Path for JSON export.")
    parser.add_argument("--load", help="Load previous JSON and display/apply it.")
    parser.add_argument("--dynamic", action="store_true", help="Enable automated dynamic scan workflow.")
    parser.add_argument("--max-steps", type=int, help="Maximum number of dynamic scan cycles.")
    parser.add_argument("--type", dest="value_kind", choices=["int32", "int64", "float", "double"], help="Numeric type for dynamic scans.")
    parser.add_argument("--chunk-size", type=int, default=0x4000, help="Snapshot chunk size in bytes.")
    parser.add_argument("--use-addon", "--enable-autopatch", dest="use_addon", action="store_true", help="Enable optional addon-based auto patching after scans.")
    parser.add_argument("--patch-value", type=float, help="Value to enforce when addon autopatching is enabled.")
    parser.add_argument("--patch-type", choices=["int32", "int64", "float", "double"], help="Numeric type for addon patching.")
    parser.add_argument("--addon-config", help="Path to addon_config.json to override defaults.")
    parser.add_argument("--auto-threshold", type=int, help="Maximum candidate count that allows addon autopatching.")
    parser.add_argument("--enforce-interval", type=float, help="Seconds between re-applying values via addon enforcement.")
    parser.add_argument("--dry-run", dest="addon_dry_run", action="store_true", default=None, help="Use addon autopatch in dry-run mode (no writes).")
    parser.add_argument("--patch-live", dest="addon_dry_run", action="store_false", help="Allow addon autopatch to modify memory (confirmation required).")
    parser.add_argument(
        "--allow-rescan",
        action="store_true",
        help="Enable rescanning after you change the in-game value.",
    )
    parser.add_argument(
        "--reference-depth",
        type=int,
        default=3,
        help="Max pointer chain depth when tracing references.",
    )
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> None:
    warn_banner()
    args = parse_args(argv)
    mock_mode = args.mock or not IS_WINDOWS
    if not IS_WINDOWS and not args.mock:
        print("Non-Windows platform detected. Switching to mock mode.")

    if args.load:
        data = load_results(args.load)
        display_saved_results(data)
        if not args.pid:
            return

    if mock_mode:
        context = build_mock_context()
        print("Running in mock demonstration mode. No real processes will be touched.")
    else:
        pid = args.pid or select_process_interactive()
        context = construct_context(pid, mock=False)

    try:
        payload = interactive_scan(context, args)
    except KeyboardInterrupt:
        print("\nScan interrupted by user.")
        payload = {}
    finally:
        close_handle(context.handle)

    if payload:
        save_results(payload, args.save)

    print("\nReminder: educational offline debugging only.")
    print("Required pip packages: pip install psutil tqdm pywin32")
    print("\nExample usage:")
    print("python process_inspector.py --pid 1234 --value-type float --value 3.14 --allow-rescan")
    print("python process_inspector.py --pid 4242 --dynamic --type int32 --max-steps 6")
    print("python process_inspector.py --mock --dynamic --type int32 --use-addon --dry-run")
    print("python process_inspector.py --pid 4242 --dynamic --use-addon --patch-value 25 --patch-type int32 --auto-threshold 3 --enforce-interval 2")
    print("python process_inspector.py --load scan_results.json")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # pragma: no cover - last-resort guardrail
        print(f"Fatal error: {exc}")
        if not IS_WINDOWS:
            print("Hint: use --mock on non-Windows systems.")
        sys.exit(1)
