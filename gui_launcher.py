"""
CustomTkinter GUI launcher for process_inspector.py with a guided dark UI.
"""
from __future__ import annotations

import queue
import subprocess
import sys
import threading
from pathlib import Path
from typing import Callable, Dict, List

try:
    import customtkinter as ctk
    from tkinter import messagebox
except ImportError as exc:  # pragma: no cover
    raise SystemExit("Install CustomTkinter first: pip install customtkinter") from exc


PROJECT_ROOT = Path(__file__).resolve().parent
SCRIPT_PATH = PROJECT_ROOT / "process_inspector.py"

ACCENT_COLOR = "#3B82F6"
ACCENT_HOVER = "#2563EB"
WINDOW_BG = "#05070B"
PANEL_BG = "#0E1117"
SECTION_BG = "#161C2A"
INPUT_BG = "#0A0F1C"
BORDER_COLOR = "#1E2535"
TEXT_PRIMARY = "#F3F4F6"
TEXT_SECONDARY = "#9CA3AF"
STATUS_BG = "#090D16"
STATUS_DONE_SENTINEL = "__STATUS_DONE__"
STEP_ACTIVE_COLOR = "#131A2A"
STEP_INACTIVE_COLOR = "#0C111C"

StepBuilder = Callable[[ctk.CTkFrame], None]


class ProcessInspectorGUI(ctk.CTk):
    """Main application window."""

    def __init__(self) -> None:
        super().__init__()
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")
        self.title("Process Data Inspector - GUI")
        self.geometry("980x700")
        self.minsize(880, 600)
        self.protocol("WM_DELETE_WINDOW", self.on_close)

        self.output_queue: queue.Queue[str] = queue.Queue()
        self.process_thread: threading.Thread | None = None
        self.process: subprocess.Popen[str] | None = None
        self.status_var = ctk.StringVar(value="Ready")

        self.step_frames: Dict[str, List[ctk.CTkFrame]] = {}
        self.step_indices: Dict[str, int] = {}
        self.step_indicators: Dict[str, List[ctk.CTkButton]] = {}
        self.step_progress_bars: Dict[str, ctk.CTkProgressBar] = {}
        self.step_progress_values: Dict[str, float] = {}
        self.step_progress_after: Dict[str, str] = {}

        self._configure_styles()
        self._init_variables()
        self._build_layout()

    # ------------------------------------------------------------------ setup
    def _configure_styles(self) -> None:
        self.configure(fg_color=WINDOW_BG)
        self.header_font = ctk.CTkFont(family="Segoe UI", size=26, weight="bold")
        self.subheader_font = ctk.CTkFont(family="Segoe UI", size=14)
        self.body_font = ctk.CTkFont(family="Segoe UI", size=14)
        self.small_font = ctk.CTkFont(family="Segoe UI", size=13)
        self.mono_font = ctk.CTkFont(family="Cascadia Code", size=13)

        self.entry_style = {
            "height": 44,
            "font": self.body_font,
            "text_color": TEXT_PRIMARY,
            "fg_color": INPUT_BG,
            "border_color": BORDER_COLOR,
            "border_width": 1,
            "corner_radius": 10,
        }
        self.option_menu_style = {
            "fg_color": INPUT_BG,
            "button_color": ACCENT_COLOR,
            "button_hover_color": ACCENT_HOVER,
            "dropdown_fg_color": SECTION_BG,
            "dropdown_text_color": TEXT_PRIMARY,
            "text_color": TEXT_PRIMARY,
            "font": self.body_font,
            "height": 44,
            "corner_radius": 10,
        }
        self.secondary_button_style = {
            "fg_color": "#1F2937",
            "hover_color": "#374151",
            "text_color": TEXT_PRIMARY,
            "font": self.body_font,
            "corner_radius": 10,
            "height": 38,
        }
        self.primary_button_style = {
            "fg_color": ACCENT_COLOR,
            "hover_color": ACCENT_HOVER,
            "text_color": TEXT_PRIMARY,
            "font": self.body_font,
            "corner_radius": 12,
            "height": 46,
        }

    def _init_variables(self) -> None:
        # Scan tab
        self.pid_var = ctk.StringVar()
        self.value_type_var = ctk.StringVar(value="int32")
        self.search_value_var = ctk.StringVar()
        self.dynamic_checkbox_var = ctk.BooleanVar(value=True)

        # Dynamic tab
        self.max_steps_var = ctk.StringVar(value="4")
        self.value_kind_var = ctk.StringVar(value="int32")
        self.chunk_size_var = ctk.StringVar(value="16384")
        self.allow_rescan_var = ctk.BooleanVar(value=False)
        self.reference_depth_var = ctk.StringVar(value="3")

        # Addon tab
        self.addon_enable_var = ctk.BooleanVar(value=False)
        self.patch_value_var = ctk.StringVar()
        self.patch_type_var = ctk.StringVar(value="int32")
        self.auto_threshold_var = ctk.StringVar()
        self.enforce_interval_var = ctk.StringVar()
        self.addon_dry_run_var = ctk.BooleanVar(value=True)

    def _build_layout(self) -> None:
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        content = ctk.CTkFrame(self, fg_color=WINDOW_BG)
        content.grid(row=0, column=0, sticky="nsew", padx=32, pady=(30, 12))
        content.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(content, text="Process Data Inspector", font=self.header_font, text_color=TEXT_PRIMARY).grid(
            row=0, column=0, pady=(0, 6), sticky="n"
        )
        ctk.CTkLabel(
            content,
            text="Guide through each decision one step at a time – scan, tune dynamics, or launch addons.",
            font=self.subheader_font,
            text_color=TEXT_SECONDARY,
        ).grid(row=1, column=0, pady=(0, 10), sticky="n")

        shell = ctk.CTkFrame(
            content,
            fg_color=PANEL_BG,
            border_color=BORDER_COLOR,
            border_width=1,
            corner_radius=24,
        )
        shell.grid(row=2, column=0, sticky="nsew", pady=(18, 0))
        shell.grid_columnconfigure(0, weight=1)
        shell.grid_rowconfigure(0, weight=1)

        self.tabview = ctk.CTkTabview(
            shell,
            segmented_button_fg_color="#182032",
            segmented_button_unselected_color="#182032",
            segmented_button_unselected_hover_color="#243049",
            segmented_button_selected_color=ACCENT_COLOR,
            segmented_button_selected_hover_color=ACCENT_HOVER,
            text_color=TEXT_PRIMARY,
            corner_radius=16,
        )
        self.tabview.grid(row=0, column=0, sticky="nsew", padx=24, pady=24)
        self.tabview.add("Scan")
        self.tabview.add("Dynamic")
        self.tabview.add("Addon")
        self.tabview.add("Log")

        self._build_scan_tab(self.tabview.tab("Scan"))
        self._build_dynamic_tab(self.tabview.tab("Dynamic"))
        self._build_addon_tab(self.tabview.tab("Addon"))
        self._build_log_tab(self.tabview.tab("Log"))

        self._build_status_bar()
        self._set_status("Ready")

    def _build_status_bar(self) -> None:
        status_frame = ctk.CTkFrame(
            self,
            fg_color=STATUS_BG,
            border_color=BORDER_COLOR,
            border_width=1,
            corner_radius=14,
        )
        status_frame.grid(row=1, column=0, sticky="ew", padx=32, pady=(0, 26))
        status_frame.grid_columnconfigure(0, weight=1)

        self.progress_bar = ctk.CTkProgressBar(
            status_frame,
            height=8,
            fg_color="#111827",
            progress_color=ACCENT_COLOR,
            corner_radius=999,
        )
        self.progress_bar.configure(mode="determinate")
        self.progress_bar.set(0)
        self.progress_bar.grid(row=0, column=0, sticky="ew", padx=20, pady=(14, 8))

        label_frame = ctk.CTkFrame(status_frame, fg_color="transparent")
        label_frame.grid(row=1, column=0, sticky="ew", padx=20, pady=(0, 12))
        label_frame.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            label_frame,
            text="Status",
            font=self.small_font,
            text_color=TEXT_SECONDARY,
        ).grid(row=0, column=0, sticky="w")
        self.status_value_label = ctk.CTkLabel(
            label_frame,
            textvariable=self.status_var,
            font=self.body_font,
            text_color=TEXT_SECONDARY,
        )
        self.status_value_label.grid(row=0, column=1, sticky="e")

    # ------------------------------------------------------------------ animation helpers
    @staticmethod
    def _hex_to_rgb(value: str) -> tuple[int, int, int]:
        value = value.lstrip("#")
        return tuple(int(value[i : i + 2], 16) for i in (0, 2, 4))

    @staticmethod
    def _rgb_to_hex(rgb: tuple[int, int, int]) -> str:
        return "#" + "".join(f"{max(0, min(255, v)):02X}" for v in rgb)

    def _animate_color(self, widget: ctk.CTkFrame, start: str, end: str, steps: int = 10, delay: int = 18) -> None:
        start_rgb = self._hex_to_rgb(start)
        end_rgb = self._hex_to_rgb(end)

        def _step(idx: int) -> None:
            ratio = idx / steps
            current = tuple(int(start_rgb[i] + (end_rgb[i] - start_rgb[i]) * ratio) for i in range(3))
            widget.configure(fg_color=self._rgb_to_hex(current))
            if idx < steps:
                widget.after(delay, lambda: _step(idx + 1))

        _step(0)

    def _animate_progress(self, tab_key: str, target: float) -> None:
        bar = self.step_progress_bars.get(tab_key)
        if not bar:
            return
        start = self.step_progress_values.get(tab_key, 0.0)
        steps = 14
        delta = target - start

        if after_id := self.step_progress_after.get(tab_key):
            try:
                bar.after_cancel(after_id)
            except Exception:
                pass

        def _step(idx: int) -> None:
            ratio = idx / steps
            bar.set(start + delta * ratio)
            if idx < steps:
                self.step_progress_after[tab_key] = bar.after(16, lambda: _step(idx + 1))
            else:
                self.step_progress_values[tab_key] = target
                self.step_progress_after.pop(tab_key, None)

        _step(0)

    def _update_step_indicators(self, tab_key: str, active_index: int) -> None:
        buttons = self.step_indicators.get(tab_key, [])
        for idx, button in enumerate(buttons):
            if idx == active_index:
                button.configure(
                    fg_color=ACCENT_COLOR,
                    hover_color=ACCENT_HOVER,
                    text_color="black",
                    state="disabled",
                )
            else:
                button.configure(
                    fg_color="#111827",
                    hover_color="#1F2937",
                    text_color=TEXT_PRIMARY,
                    state="normal",
                )

    def _update_step_progress(self, tab_key: str, active_index: int) -> None:
        frames = self.step_frames.get(tab_key, [])
        if not frames:
            return
        total = len(frames)
        target = (active_index + 1) / total
        self._animate_progress(tab_key, target)

    # ------------------------------------------------------------------ stepper helpers
    def _create_stepper(
        self,
        parent: ctk.CTkFrame,
        tab_key: str,
        steps: List[tuple[str, str, StepBuilder]],
    ) -> None:
        wrapper = ctk.CTkFrame(parent, fg_color=SECTION_BG, corner_radius=20)
        wrapper.pack(fill="both", expand=True, padx=18, pady=18)

        indicator_bar = ctk.CTkFrame(wrapper, fg_color="transparent")
        indicator_bar.pack(fill="x", padx=24, pady=(18, 4))
        ctk.CTkLabel(
            indicator_bar,
            text="Steps",
            font=self.small_font,
            text_color=TEXT_SECONDARY,
        ).pack(anchor="w")

        chip_row = ctk.CTkFrame(indicator_bar, fg_color="transparent")
        chip_row.pack(fill="x", pady=(8, 6))

        progress = ctk.CTkProgressBar(
            wrapper,
            height=10,
            fg_color="#0D1422",
            progress_color=ACCENT_COLOR,
            corner_radius=999,
        )
        progress.pack(fill="x", padx=24, pady=(0, 12))
        progress.set(0)

        cards_container = ctk.CTkFrame(wrapper, fg_color="transparent")
        cards_container.pack(fill="both", expand=True, padx=6, pady=(4, 12))

        self.step_indicators[tab_key] = []
        self.step_progress_bars[tab_key] = progress
        self.step_progress_values[tab_key] = 0.0
        frames: List[ctk.CTkFrame] = []
        total = len(steps)
        for idx, (title, subtitle, builder) in enumerate(steps):
            indicator = ctk.CTkButton(
                chip_row,
                text=f"{idx + 1}. {title}",
                command=lambda key=tab_key, jump=idx: self._show_step(key, jump),
                width=0,
                anchor="w",
                **self.secondary_button_style,
            )
            indicator.pack(side="left", padx=4, pady=4, expand=True, fill="x")
            self.step_indicators[tab_key].append(indicator)

            frame = ctk.CTkFrame(
                cards_container,
                fg_color=STEP_INACTIVE_COLOR,
                corner_radius=18,
                border_width=1,
                border_color=BORDER_COLOR,
            )
            frame.grid_columnconfigure(0, weight=1)

            header = ctk.CTkFrame(frame, fg_color="transparent")
            header.pack(fill="x", padx=20, pady=(18, 0))
            ctk.CTkLabel(
                header,
                text=f"Step {idx + 1} of {total}",
                font=self.small_font,
                text_color=ACCENT_COLOR,
            ).pack(anchor="w")
            ctk.CTkLabel(
                header,
                text=title,
                font=self.body_font,
                text_color=TEXT_PRIMARY,
            ).pack(anchor="w", pady=(2, 2))
            if subtitle:
                ctk.CTkLabel(
                    header,
                    text=subtitle,
                    font=self.small_font,
                    text_color=TEXT_SECONDARY,
                ).pack(anchor="w", pady=(0, 8))

            body = ctk.CTkFrame(frame, fg_color="transparent")
            body.pack(fill="both", expand=True, padx=20, pady=(4, 4))
            builder(body)

            next_hint = steps[idx + 1][0] if idx < total - 1 else None
            self._build_step_nav(frame, tab_key, idx, total, next_hint=next_hint)
            frames.append(frame)
            frame.pack_forget()

        self.step_frames[tab_key] = frames
        self.step_indices[tab_key] = 0
        self._show_step(tab_key, 0)

    def _build_step_nav(
        self,
        frame: ctk.CTkFrame,
        tab_key: str,
        index: int,
        total: int,
        *,
        next_hint: str | None = None,
    ) -> None:
        nav = ctk.CTkFrame(frame, fg_color="transparent")
        nav.pack(fill="x", padx=20, pady=(6, 18))

        if index > 0:
            ctk.CTkButton(
                nav,
                text="Back",
                command=lambda key=tab_key, target=index - 1: self._show_step(key, target),
                **self.secondary_button_style,
            ).pack(side="left")
        else:
            ctk.CTkLabel(nav, text="", font=self.small_font).pack(side="left")

        if index < total - 1:
            next_text = f"Next · {next_hint}" if next_hint else "Next"
            ctk.CTkButton(
                nav,
                text=next_text,
                command=lambda key=tab_key, target=index + 1: self._show_step(key, target),
                **self.primary_button_style,
            ).pack(side="right")
        else:
            ctk.CTkLabel(
                nav,
                text="Review above values, then run.",
                font=self.small_font,
                text_color=TEXT_SECONDARY,
            ).pack(side="right")

    def _show_step(self, tab_key: str, index: int, animate: bool = True) -> None:
        frames = self.step_frames.get(tab_key)
        if not frames:
            return
        total = len(frames)
        index = max(0, min(index, total - 1))
        previous = self.step_indices.get(tab_key, 0)

        if previous == index and frames[index].winfo_manager():
            return

        if 0 <= previous < total and frames[previous].winfo_manager():
            frames[previous].pack_forget()
            frames[previous].configure(fg_color=STEP_INACTIVE_COLOR)

        target_frame = frames[index]
        target_frame.pack(fill="both", expand=True, padx=12, pady=12)
        if animate:
            self._animate_color(target_frame, STEP_INACTIVE_COLOR, STEP_ACTIVE_COLOR)
        else:
            target_frame.configure(fg_color=STEP_ACTIVE_COLOR)

        self.step_indices[tab_key] = index
        self._update_step_indicators(tab_key, index)
        self._update_step_progress(tab_key, index)

    # ------------------------------------------------------------------ atomic UI helpers
    def _add_entry(
        self,
        parent: ctk.CTkFrame,
        label: str,
        variable: ctk.StringVar,
        placeholder: str = "",
    ) -> None:
        ctk.CTkLabel(parent, text=label, font=self.small_font, text_color=TEXT_SECONDARY).pack(
            anchor="w", pady=(4, 4)
        )
        entry = ctk.CTkEntry(parent, textvariable=variable, placeholder_text=placeholder, **self.entry_style)
        entry.pack(fill="x", pady=(0, 12))

    def _add_option_menu(
        self,
        parent: ctk.CTkFrame,
        label: str,
        variable: ctk.StringVar,
        values: List[str],
    ) -> None:
        ctk.CTkLabel(parent, text=label, font=self.small_font, text_color=TEXT_SECONDARY).pack(
            anchor="w", pady=(4, 4)
        )
        option = ctk.CTkOptionMenu(parent, values=values, variable=variable, **self.option_menu_style)
        option.pack(fill="x", pady=(0, 12))

    # ------------------------------------------------------------------ tab builders
    def _build_scan_tab(self, parent: ctk.CTkFrame) -> None:
        steps: List[tuple[str, str, StepBuilder]] = [
            (
                "Choose the process to inspect",
                "Attach using a PID from Task Manager or another source.",
                self._scan_step_target,
            ),
            (
                "Define the value you are searching for",
                "Specify the data type and the optional literal value to filter results.",
                self._scan_step_value,
            ),
            (
                "Pick the scan mode and launch",
                "Decide if you want dynamic mode before executing the scan command.",
                self._scan_step_execution,
            ),
        ]
        self._create_stepper(parent, "Scan", steps)

    def _scan_step_target(self, body: ctk.CTkFrame) -> None:
        self._add_entry(body, "PID (--pid)", self.pid_var, "Example: 4242")
        ctk.CTkLabel(
            body,
            text="Tip: leaving PID blank will prompt the CLI to request one.",
            font=self.small_font,
            text_color=TEXT_SECONDARY,
        ).pack(anchor="w", pady=(0, 6))

    def _scan_step_value(self, body: ctk.CTkFrame) -> None:
        self._add_option_menu(
            body,
            "Value Type (--value-type)",
            self.value_type_var,
            ["int32", "uint32", "int64", "uint64", "float", "double"],
        )
        self._add_entry(body, "Search Value (--value)", self.search_value_var, "Optional literal to match")

    def _scan_step_execution(self, body: ctk.CTkFrame) -> None:
        ctk.CTkCheckBox(
            body,
            text="Enable Dynamic Scan (--dynamic)",
            variable=self.dynamic_checkbox_var,
            font=self.body_font,
            border_color=BORDER_COLOR,
            fg_color=ACCENT_COLOR,
            corner_radius=6,
        ).pack(anchor="w", pady=(6, 18))
        ctk.CTkButton(body, text="Run Scan", command=self.run_scan, **self.primary_button_style).pack(fill="x")

    def _build_dynamic_tab(self, parent: ctk.CTkFrame) -> None:
        steps = [
            (
                "Set primary dynamic parameters",
                "Control maximum passes and data kind for the pointer walk.",
                self._dynamic_step_base,
            ),
            (
                "Tune depth and iteration behavior",
                "Adjust chunk sizes, reference depth, and optional rescan flows.",
                self._dynamic_step_iteration,
            ),
        ]
        self._create_stepper(parent, "Dynamic", steps)

    def _dynamic_step_base(self, body: ctk.CTkFrame) -> None:
        self._add_entry(body, "Max Steps (--max-steps)", self.max_steps_var, "Default 4")
        self._add_option_menu(
            body,
            "Value Kind (--type)",
            self.value_kind_var,
            ["int32", "uint32", "int64", "uint64", "float", "double"],
        )

    def _dynamic_step_iteration(self, body: ctk.CTkFrame) -> None:
        self._add_entry(body, "Chunk Size (--chunk-size)", self.chunk_size_var, "Default 16384")
        self._add_entry(body, "Reference Depth (--reference-depth)", self.reference_depth_var, "Default 3")
        ctk.CTkCheckBox(
            body,
            text="Allow Rescan (--allow-rescan)",
            variable=self.allow_rescan_var,
            font=self.body_font,
            border_color=BORDER_COLOR,
            fg_color=ACCENT_COLOR,
            corner_radius=6,
        ).pack(anchor="w", pady=(6, 6))

    def _build_addon_tab(self, parent: ctk.CTkFrame) -> None:
        steps = [
            (
                "Enable addon mode and pick patch basics",
                "Toggle addon support, then describe the new value and its data type.",
                self._addon_step_toggle,
            ),
            (
                "Configure thresholds and intervals",
                "Optional throttling controls ensure stable patch loops.",
                self._addon_step_thresholds,
            ),
            (
                "Choose dry run or live patch",
                "Confirm safety options before executing addon mode.",
                self._addon_step_execution,
            ),
        ]
        self._create_stepper(parent, "Addon", steps)

    def _addon_step_toggle(self, body: ctk.CTkFrame) -> None:
        ctk.CTkSwitch(
            body,
            text="Enable Addon (--use-addon)",
            variable=self.addon_enable_var,
            font=self.body_font,
            progress_color=ACCENT_COLOR,
        ).pack(anchor="w", pady=(0, 18))
        self._add_entry(body, "Patch Value (--patch-value)", self.patch_value_var, "e.g. 1337")
        self._add_option_menu(
            body,
            "Patch Type (--patch-type)",
            self.patch_type_var,
            ["int32", "uint32", "int64", "uint64", "float", "double"],
        )

    def _addon_step_thresholds(self, body: ctk.CTkFrame) -> None:
        self._add_entry(body, "Auto Threshold (--auto-threshold)", self.auto_threshold_var, "Optional")
        self._add_entry(body, "Enforce Interval (--enforce-interval)", self.enforce_interval_var, "Optional seconds")

    def _addon_step_execution(self, body: ctk.CTkFrame) -> None:
        ctk.CTkCheckBox(
            body,
            text="Dry Run (--dry-run)",
            variable=self.addon_dry_run_var,
            font=self.body_font,
            border_color=BORDER_COLOR,
            fg_color=ACCENT_COLOR,
            corner_radius=6,
        ).pack(anchor="w", pady=(0, 18))
        ctk.CTkButton(body, text="Run Addon Mode", command=self.run_addon_mode, **self.primary_button_style).pack(
            fill="x"
        )

    def _build_log_tab(self, parent: ctk.CTkFrame) -> None:
        container = ctk.CTkFrame(parent, fg_color=SECTION_BG, corner_radius=20)
        container.pack(fill="both", expand=True, padx=18, pady=18)
        container.grid_columnconfigure(0, weight=1)
        container.grid_rowconfigure(1, weight=1)

        ctk.CTkLabel(
            container,
            text="Execution Log",
            font=self.body_font,
            text_color=TEXT_PRIMARY,
        ).grid(row=0, column=0, sticky="w", padx=20, pady=(16, 6))

        log_holder = ctk.CTkFrame(
            container,
            fg_color="#080C16",
            corner_radius=16,
            border_width=1,
            border_color=BORDER_COLOR,
        )
        log_holder.grid(row=1, column=0, sticky="nsew", padx=20, pady=(0, 20))
        log_holder.grid_columnconfigure(0, weight=1)
        log_holder.grid_rowconfigure(0, weight=1)

        self.log_text = ctk.CTkTextbox(
            log_holder,
            font=self.mono_font,
            text_color=TEXT_PRIMARY,
            fg_color="#04060C",
            wrap="word",
            corner_radius=12,
            border_width=0,
            scrollbar_button_color=BORDER_COLOR,
            scrollbar_button_hover_color=ACCENT_COLOR,
        )
        self.log_text.grid(row=0, column=0, sticky="nsew", padx=(12, 0), pady=12)
        self.log_text.configure(state="disabled")

        scrollbar = ctk.CTkScrollbar(
            log_holder,
            orientation="vertical",
            fg_color="#0E1320",
            button_color=BORDER_COLOR,
            button_hover_color=ACCENT_COLOR,
        )
        scrollbar.grid(row=0, column=1, sticky="ns", pady=12, padx=(0, 12))
        scrollbar.configure(command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=scrollbar.set)

    # ------------------------------------------------------------------ process + commands
    def build_base_command(self) -> List[str]:
        if not SCRIPT_PATH.exists():
            raise FileNotFoundError(f"Script not found: {SCRIPT_PATH}")

        cmd = [sys.executable, str(SCRIPT_PATH)]
        if pid := self.pid_var.get().strip():
            cmd += ["--pid", pid]
        return cmd

    def add_scan_arguments(self, cmd: List[str], *, dynamic: bool) -> None:
        if dynamic:
            cmd.append("--dynamic")
            if value_kind := self.value_kind_var.get().strip():
                cmd += ["--type", value_kind]
            if steps := self.max_steps_var.get().strip():
                cmd += ["--max-steps", steps]
            if chunk := self.chunk_size_var.get().strip():
                cmd += ["--chunk-size", chunk]
        else:
            cmd += ["--value-type", self.value_type_var.get()]
            if value := self.search_value_var.get().strip():
                cmd += ["--value", value]

        if self.allow_rescan_var.get():
            cmd.append("--allow-rescan")
        if depth := self.reference_depth_var.get().strip():
            cmd += ["--reference-depth", depth]

    def add_addon_arguments(self, cmd: List[str]) -> None:
        if not self.addon_enable_var.get():
            return
        cmd.append("--use-addon")
        if patch_value := self.patch_value_var.get().strip():
            cmd += ["--patch-value", patch_value]
        if patch_type := self.patch_type_var.get().strip():
            cmd += ["--patch-type", patch_type]
        if threshold := self.auto_threshold_var.get().strip():
            cmd += ["--auto-threshold", threshold]
        if interval := self.enforce_interval_var.get().strip():
            cmd += ["--enforce-interval", interval]
        if self.addon_dry_run_var.get():
            cmd.append("--dry-run")
        else:
            cmd.append("--patch-live")

    # ------------------------------------------------------------------ button actions
    def run_scan(self) -> None:
        dynamic = self.dynamic_checkbox_var.get()
        try:
            cmd = self.build_base_command()
        except FileNotFoundError as exc:
            messagebox.showerror("Missing Script", str(exc))
            self._set_status("Ready")
            return

        self.add_scan_arguments(cmd, dynamic=dynamic)
        self.append_log(f"\n[Scan] {' '.join(cmd)}\n")
        self.start_process(cmd)

    def run_addon_mode(self) -> None:
        if not self.addon_enable_var.get():
            messagebox.showinfo("Addon disabled", "Enable the addon switch before running addon mode.")
            return
        try:
            cmd = self.build_base_command()
        except FileNotFoundError as exc:
            messagebox.showerror("Missing Script", str(exc))
            self._set_status("Ready")
            return
        self.add_scan_arguments(cmd, dynamic=True)
        self.add_addon_arguments(cmd)
        self.append_log(f"\n[Addon] {' '.join(cmd)}\n")
        self.start_process(cmd)

    # ------------------------------------------------------------------ process handling
    def start_process(self, command: List[str]) -> None:
        if self.process_thread and self.process_thread.is_alive():
            messagebox.showinfo("Process running", "Wait for the current run to finish.")
            return

        self._set_status("Running...")
        self.process_thread = threading.Thread(target=self._run_process, args=(command,), daemon=True)
        self.process_thread.start()
        self.after(120, self._poll_queue)

    def _run_process(self, command: List[str]) -> None:
        try:
            self.process = subprocess.Popen(
                command,
                cwd=PROJECT_ROOT,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
        except OSError as exc:
            self.output_queue.put(f"Failed to start process: {exc}\n")
            return

        assert self.process.stdout is not None
        for line in self.process.stdout:
            self.output_queue.put(line)
        self.process.wait()
        self.output_queue.put("Done.\n")
        self.output_queue.put(STATUS_DONE_SENTINEL)

    def _poll_queue(self) -> None:
        done_signaled = False

        while not self.output_queue.empty():
            entry = self.output_queue.get()
            if entry == STATUS_DONE_SENTINEL:
                done_signaled = True
            else:
                self.append_log(entry)

        if done_signaled:
            self._set_status("Done")
            self.tabview.set("Log")

        if self.process_thread and self.process_thread.is_alive():
            self.after(120, self._poll_queue)
        elif self.status_var.get() != "Done":
            self._set_status("Ready")

    def append_log(self, text: str) -> None:
        self.log_text.configure(state="normal")
        self.log_text.insert("end", text)
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def _set_status(self, state: str) -> None:
        palette = {
            "Ready": TEXT_SECONDARY,
            "Running...": "#FACC15",
            "Done": "#22C55E",
        }
        self.status_var.set(state)
        self.status_value_label.configure(text_color=palette.get(state, TEXT_SECONDARY))

        if state == "Running...":
            self.progress_bar.configure(mode="indeterminate")
            self.progress_bar.start()
        elif state == "Done":
            self.progress_bar.stop()
            self.progress_bar.configure(mode="determinate")
            self.progress_bar.set(1)
        else:
            self.progress_bar.stop()
            self.progress_bar.configure(mode="determinate")
            self.progress_bar.set(0)

    def on_close(self) -> None:
        if self.process and self.process.poll() is None:
            try:
                self.process.terminate()
            except Exception:
                pass
        self.destroy()


def main() -> None:
    app = ProcessInspectorGUI()
    app.mainloop()


if __name__ == "__main__":
    main()
