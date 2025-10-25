"""
CustomTkinter GUI front-end for the Process Data Inspector project.

This layer wraps the existing CLI tool without replacing any behavior.
"""
from __future__ import annotations

import math
import queue
import shlex
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    import customtkinter as ctk
    from tkinter import TclError, filedialog, messagebox
except ImportError as exc:  # pragma: no cover
    raise SystemExit(
        "CustomTkinter is required for the GUI. Install it via 'pip install customtkinter'."
    ) from exc


PROJECT_ROOT = Path(__file__).resolve().parent
SCRIPT_PATH = PROJECT_ROOT / "process_inspector.py"


MANUAL_VALUE_TYPES = ["int32", "uint32", "int64", "uint64", "float", "double"]


class InspectorGUI(ctk.CTk):
    """Main application window."""

    def __init__(self) -> None:
        super().__init__()
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self.title("Process Data Inspector - GUI")
        self.geometry("1280x820")
        self.minsize(1180, 760)
        self.protocol("WM_DELETE_WINDOW", self.on_close)

        self.output_queue: queue.Queue[str] = queue.Queue()
        self.process_thread: Optional[threading.Thread] = None
        self.process: Optional[subprocess.Popen] = None

        self.theme = {
            "bg": "#0d101a",
            "panel": "#141a27",
            "panel_alt": "#1a2132",
            "surface": "#1f2739",
            "surface_alt": "#252f45",
            "toolbar": "#1b2335",
            "accent": "#0a84ff",
            "accent_alt": "#3c9dff",
            "accent_soft": "#1f4fa3",
            "text_primary": "#f5f7ff",
            "text_muted": "#9aa7c4",
            "text_subtle": "#7f8bad",
            "chip_bg": "#1b2435",
            "status_bg": "#161d2b",
            "status_active": "#162642",
            "status_idle_badge": "#232f45",
            "outline": "#1f2739",
            "outline_subtle": "#1a2232",
            "button_secondary": "#273252",
            "button_secondary_hover": "#2f3c63",
        }

        self.font_title = ctk.CTkFont(size=28, weight="bold")
        self.font_heading = ctk.CTkFont(size=17, weight="bold")
        self.font_body = ctk.CTkFont(size=13)
        self.font_small = ctk.CTkFont(size=12)
        self.font_caption = ctk.CTkFont(size=11, weight="bold")

        self._pulse_phase = 0.0
        self._status_pulse_phase = 0.0
        self._status_animation_running = False
        self._status_pulse_job: Optional[str] = None

        self._init_variables()
        self._build_layout()
        self._set_status("Idle", False)
        self._animate_header_glow()
        self._setup_preview_traces()

    # ------------------------------------------------------------------ UI setup
    def _init_variables(self) -> None:
        self.pid_var = ctk.StringVar()
        self.mock_var = ctk.BooleanVar(value=False)
        self.dynamic_var = ctk.BooleanVar(value=True)
        self.scan_mode_var = ctk.StringVar(value="Dynamic")
        self.scan_preset_var = ctk.StringVar(value="Balanced")
        self.max_steps_var = ctk.StringVar(value="4")
        self.value_type_var = ctk.StringVar(value="float")
        self.manual_value_var = ctk.StringVar()
        self.allow_rescan_var = ctk.BooleanVar(value=False)
        self.reference_depth_var = ctk.StringVar(value="3")
        self.chunk_size_var = ctk.StringVar(value="16384")
        self.value_kind_var = ctk.StringVar(value="int32")
        self.addon_enable_var = ctk.BooleanVar(value=False)
        self.patch_value_var = ctk.StringVar()
        self.patch_type_var = ctk.StringVar(value="int32")
        self.auto_threshold_var = ctk.StringVar(value="3")
        self.enforce_interval_var = ctk.StringVar()
        self.addon_dry_run_var = ctk.BooleanVar(value=True)
        self.addon_config_var = ctk.StringVar()
        self.save_path_var = ctk.StringVar(value="scan_results.json")
        self.load_path_var = ctk.StringVar()
        self.auto_scroll_var = ctk.BooleanVar(value=True)
        self.appearance_var = ctk.StringVar(value="Dark")

    def _build_layout(self) -> None:
        self.configure(fg_color=self.theme["bg"])
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        # --- Header
        header = ctk.CTkFrame(
            self,
            fg_color=self.theme["panel"],
            corner_radius=0,
            border_width=0,
        )
        header.grid(row=0, column=0, sticky="ew")
        header.grid_columnconfigure(0, weight=1)
        header.grid_columnconfigure(1, weight=0)
        header.grid_columnconfigure(2, weight=0)

        title_stack = ctk.CTkFrame(header, fg_color="transparent")
        title_stack.grid(row=0, column=0, sticky="w", padx=32, pady=(26, 12))
        title_stack.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            title_stack,
            text="Process Data Inspector",
            font=self.font_title,
            text_color=self.theme["text_primary"],
        ).grid(row=0, column=0, sticky="w")

        ctk.CTkLabel(
            title_stack,
            text="Curate scan strategies with live metrics and carefully tuned presets.",
            font=self.font_body,
            text_color=self.theme["text_muted"],
            wraplength=520,
        ).grid(row=1, column=0, sticky="w", pady=(6, 0))

        self.status_card = ctk.CTkFrame(
            header,
            fg_color=self.theme["status_bg"],
            corner_radius=18,
            border_width=1,
            border_color=self.theme["outline"],
        )
        self.status_card.grid(row=0, column=1, rowspan=2, sticky="ne", padx=(0, 24), pady=24)
        self.status_card.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            self.status_card,
            text="STATUS",
            font=self.font_caption,
            text_color=self.theme["text_subtle"],
        ).grid(row=0, column=0, sticky="w", padx=20, pady=(18, 6))

        self.status_chip = ctk.CTkLabel(
            self.status_card,
            text="Idle",
            font=ctk.CTkFont(size=18, weight="bold"),
            text_color=self.theme["accent"],
            fg_color=self.theme["status_idle_badge"],
            corner_radius=14,
            padx=22,
            pady=12,
        )
        self.status_chip.grid(row=1, column=0, sticky="we", padx=16)

        self.status_caption = ctk.CTkLabel(
            self.status_card,
            text="Standing by",
            font=self.font_small,
            text_color=self.theme["text_muted"],
        )
        self.status_caption.grid(row=2, column=0, sticky="w", padx=20, pady=(8, 18))

        actions_stack = ctk.CTkFrame(header, fg_color="transparent")
        actions_stack.grid(row=0, column=2, rowspan=2, sticky="ne", padx=(0, 32), pady=24)
        actions_stack.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            actions_stack,
            text="APPEARANCE",
            font=self.font_caption,
            text_color=self.theme["text_subtle"],
        ).grid(row=0, column=0, sticky="e")

        self.appearance_control = ctk.CTkSegmentedButton(
            actions_stack,
            values=["Light", "Dark", "System"],
            variable=self.appearance_var,
            command=self._change_appearance,
            unselected_color=self.theme["chip_bg"],
            selected_color=self.theme["accent"],
            selected_hover_color=self.theme["accent_alt"],
            text_color=self.theme["text_primary"],
        )
        self.appearance_control.grid(row=1, column=0, sticky="e", pady=(4, 0))
        self.appearance_control.set(self.appearance_var.get())

        help_button = ctk.CTkButton(
            actions_stack,
            text="Quick tour",
            command=self._show_help,
            fg_color=self.theme["button_secondary"],
            hover_color=self.theme["button_secondary_hover"],
            height=40,
            corner_radius=14,
            font=self.font_body,
            text_color=self.theme["text_primary"],
        )
        help_button.grid(row=2, column=0, sticky="e", pady=(16, 0))

        self.header_glow = ctk.CTkFrame(header, fg_color=self.theme["accent"], height=3, corner_radius=0)
        self.header_glow.grid(row=2, column=0, columnspan=3, sticky="ew")

        # --- Main body
        body = ctk.CTkFrame(self, fg_color="transparent")
        body.grid(row=1, column=0, sticky="nsew", padx=32, pady=(24, 32))
        body.grid_rowconfigure(0, weight=1)
        body.grid_columnconfigure(0, weight=0)
        body.grid_columnconfigure(1, weight=1)

        controls_shell = ctk.CTkFrame(
            body,
            fg_color=self.theme["panel"],
            corner_radius=26,
            border_width=1,
            border_color=self.theme["outline"],
        )
        controls_shell.grid(row=0, column=0, sticky="nsw")
        controls_shell.grid_rowconfigure(1, weight=1)
        controls_shell.grid_columnconfigure(0, weight=1)

        controls_header = ctk.CTkFrame(controls_shell, fg_color="transparent")
        controls_header.grid(row=0, column=0, sticky="we", padx=28, pady=(26, 16))
        controls_header.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            controls_header,
            text="Scan Studio",
            font=ctk.CTkFont(size=20, weight="bold"),
            text_color=self.theme["text_primary"],
        ).grid(row=0, column=0, sticky="w")

        ctk.CTkLabel(
            controls_header,
            text="Craft an inspection profile and orchestrate runs from one refined console.",
            font=self.font_small,
            text_color=self.theme["text_muted"],
            wraplength=320,
            justify="left",
        ).grid(row=1, column=0, sticky="w", pady=(6, 0))

        self.controls_panel = ctk.CTkScrollableFrame(
            controls_shell,
            width=420,
            fg_color="transparent",
        )
        self.controls_panel.grid(row=1, column=0, sticky="nsew", padx=16, pady=(0, 24))
        self.controls_panel.grid_columnconfigure(0, weight=1)

        self._section_row = 0
        self._build_process_section()
        self._build_scan_section()
        self._build_manual_section()
        self._build_persistence_section()
        self._build_addon_section()
        self._build_action_section()

        # --- Output area
        self.output_card = ctk.CTkFrame(
            body,
            fg_color=self.theme["panel"],
            corner_radius=28,
            border_width=1,
            border_color=self.theme["outline"],
        )
        self.output_card.grid(row=0, column=1, sticky="nsew", padx=(28, 0))
        self.output_card.grid_columnconfigure(0, weight=1)
        self.output_card.grid_rowconfigure(2, weight=1)

        output_header = ctk.CTkFrame(self.output_card, fg_color="transparent")
        output_header.grid(row=0, column=0, sticky="we", padx=32, pady=(30, 12))
        output_header.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            output_header,
            text="Command Output",
            font=ctk.CTkFont(size=22, weight="bold"),
            text_color=self.theme["text_primary"],
        ).grid(row=0, column=0, sticky="w")

        ctk.CTkLabel(
            output_header,
            text="Live logs from process_inspector.py appear here during each run.",
            font=self.font_small,
            text_color=self.theme["text_muted"],
        ).grid(row=1, column=0, sticky="w", pady=(6, 0))

        toolbar = ctk.CTkFrame(
            self.output_card,
            fg_color=self.theme["toolbar"],
            corner_radius=18,
        )
        toolbar.grid(row=1, column=0, sticky="we", padx=32, pady=(0, 16))
        toolbar.grid_columnconfigure(0, weight=1)
        toolbar.grid_columnconfigure(1, weight=0)
        toolbar.grid_columnconfigure(2, weight=0)

        self.notification_label = ctk.CTkLabel(
            toolbar,
            text="Ready when you are.",
            text_color=self.theme["text_muted"],
            font=self.font_body,
        )
        self.notification_label.grid(row=0, column=0, sticky="w", padx=20, pady=14)

        auto_scroll_switch = ctk.CTkSwitch(
            toolbar,
            text="Auto-scroll",
            variable=self.auto_scroll_var,
        )
        auto_scroll_switch.grid(row=0, column=1, padx=16, pady=14)

        clear_button = ctk.CTkButton(
            toolbar,
            text="Clear log",
            width=120,
            command=self._clear_output,
            fg_color=self.theme["button_secondary"],
            hover_color=self.theme["button_secondary_hover"],
            font=self.font_body,
            corner_radius=14,
        )
        clear_button.grid(row=0, column=2, padx=(0, 20), pady=14)

        self.output_text = ctk.CTkTextbox(
            self.output_card,
            wrap="word",
            activate_scrollbars=True,
            corner_radius=20,
            fg_color=self.theme["surface_alt"],
            text_color=self.theme["text_primary"],
        )
        self.output_text.grid(row=2, column=0, sticky="nsew", padx=32, pady=(0, 18))

        controls_tip = (
            "Process Data Inspector drives process_inspector.py. "
            "Operate responsibly on single-player experiences you own."
        )
        ctk.CTkLabel(
            self.output_card,
            text=controls_tip,
            wraplength=760,
            text_color=self.theme["text_muted"],
            font=self.font_body,
        ).grid(row=3, column=0, sticky="we", padx=32, pady=(0, 8))

        self.progress = ctk.CTkProgressBar(
            self.output_card,
            mode="indeterminate",
            corner_radius=12,
            determinate_speed=1.8,
            progress_color=self.theme["accent"],
        )
        self.progress.grid(row=4, column=0, sticky="we", padx=32, pady=(0, 32))
        self.progress.grid_remove()

    # ------------------------------------------------------------------ Section builders
    def _add_section(
        self, title: str, description: str | None = None
    ) -> Tuple[ctk.CTkFrame, int]:
        section = ctk.CTkFrame(
            self.controls_panel,
            fg_color=self.theme["surface"],
            corner_radius=20,
            border_width=1,
            border_color=self.theme["outline_subtle"],
        )
        section.grid(
            row=self._section_row,
            column=0,
            sticky="we",
            padx=12,
            pady=(12 if self._section_row == 0 else 18, 0),
        )
        section.grid_columnconfigure(0, weight=1)
        self._section_row += 1

        header = ctk.CTkFrame(section, fg_color="transparent")
        header.grid(row=0, column=0, sticky="we", padx=20, pady=(20, 10))
        header.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            header,
            text="",
            width=10,
            height=10,
            corner_radius=5,
            fg_color=self.theme["accent"],
        ).grid(row=0, column=0, padx=(0, 12))

        ctk.CTkLabel(
            header,
            text=title,
            text_color=self.theme["text_primary"],
            font=self.font_heading,
        ).grid(row=0, column=1, sticky="w")

        next_row = 1
        if description:
            ctk.CTkLabel(
                section,
                text=description,
                text_color=self.theme["text_muted"],
                font=self.font_body,
                wraplength=340,
                justify="left",
            ).grid(row=next_row, column=0, sticky="we", padx=20, pady=(0, 12))
            next_row += 1

        divider = ctk.CTkFrame(
            section,
            fg_color=self.theme["outline_subtle"],
            height=1,
            corner_radius=1,
        )
        divider.grid(row=next_row, column=0, sticky="we", padx=20, pady=(0, 18))
        section.rowconfigure(next_row, minsize=1)

        return section, next_row + 1

    def _build_process_section(self) -> None:
        section, row = self._add_section(
            "Target Process",
            "Connect to a running process using its PID or experiment with the mock mode for demos.",
        )

        ctk.CTkEntry(
            section,
            placeholder_text="PID (optional)",
            textvariable=self.pid_var,
            corner_radius=12,
            border_width=1,
        ).grid(row=row, column=0, sticky="we", padx=20, pady=(0, 12))

        ctk.CTkSwitch(
            section,
            text="Use mock process data",
            variable=self.mock_var,
        ).grid(row=row + 1, column=0, sticky="we", padx=20, pady=(0, 4))

    def _build_scan_section(self) -> None:
        section, row = self._add_section(
            "Scan Strategy",
            "Toggle between dynamic smart scanning and manual targeting depending on your workflow.",
        )

        segmented = ctk.CTkSegmentedButton(
            section,
            values=["Dynamic", "Manual"],
            command=self._on_scan_mode_change,
            variable=self.scan_mode_var,
            unselected_color=self.theme["panel_alt"],
            selected_color=self.theme["accent"],
            selected_hover_color=self.theme["accent_alt"],
        )
        segmented.grid(row=row, column=0, sticky="we", padx=20, pady=(0, 12))
        segmented.set("Dynamic" if self.dynamic_var.get() else "Manual")

        preset_row = ctk.CTkFrame(section, fg_color="transparent")
        preset_row.grid(row=row + 1, column=0, sticky="we", padx=20, pady=(0, 12))
        preset_row.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(
            preset_row,
            text="Preset",
            font=self.font_body,
            text_color=self.theme["text_muted"],
        ).grid(row=0, column=0, sticky="w")
        preset_menu = ctk.CTkOptionMenu(
            preset_row,
            values=["Balanced", "Fast sweep", "Deep dive"],
            variable=self.scan_preset_var,
            command=self._apply_scan_preset,
        )
        preset_menu.grid(row=0, column=1, sticky="we")
        self._style_dropdown(preset_menu)

        self.dynamic_frame = ctk.CTkFrame(section, fg_color="transparent")
        self.dynamic_frame.grid(row=row + 2, column=0, sticky="we", padx=20, pady=(0, 4))
        self.dynamic_frame.grid_columnconfigure(0, weight=1)

        ctk.CTkEntry(
            self.dynamic_frame,
            placeholder_text="Max steps",
            textvariable=self.max_steps_var,
            corner_radius=12,
            border_width=1,
        ).grid(row=0, column=0, sticky="we", pady=(0, 12))

        value_kind_combo = ctk.CTkComboBox(
            self.dynamic_frame,
            values=["int32", "int64", "float", "double"],
            variable=self.value_kind_var,
        )
        value_kind_combo.grid(row=1, column=0, sticky="we", pady=(0, 12))
        self._style_dropdown(value_kind_combo)

        ctk.CTkEntry(
            self.dynamic_frame,
            placeholder_text="Chunk size",
            textvariable=self.chunk_size_var,
            corner_radius=12,
            border_width=1,
        ).grid(row=2, column=0, sticky="we", pady=(0, 12))

    def _build_manual_section(self) -> None:
        section, row = self._add_section(
            "Manual Overrides",
            "Fine tune scan values and thresholds when you know exactly what to look for.",
        )

        self.manual_frame = ctk.CTkFrame(section, fg_color="transparent")
        self.manual_frame.grid(row=row, column=0, sticky="we", padx=20, pady=(0, 4))
        self.manual_frame.grid_columnconfigure(0, weight=1)

        manual_type_combo = ctk.CTkComboBox(
            self.manual_frame,
            values=MANUAL_VALUE_TYPES,
            variable=self.value_type_var,
        )
        manual_type_combo.grid(row=0, column=0, sticky="we", pady=(0, 12))
        self._style_dropdown(manual_type_combo)

        ctk.CTkEntry(
            self.manual_frame,
            placeholder_text="Manual value",
            textvariable=self.manual_value_var,
            corner_radius=12,
            border_width=1,
        ).grid(row=1, column=0, sticky="we", pady=(0, 12))

        ctk.CTkSwitch(
            self.manual_frame,
            text="Allow rescan",
            variable=self.allow_rescan_var,
        ).grid(row=2, column=0, sticky="we", pady=(0, 12))

        ctk.CTkEntry(
            self.manual_frame,
            placeholder_text="Reference depth",
            textvariable=self.reference_depth_var,
            corner_radius=12,
            border_width=1,
        ).grid(row=3, column=0, sticky="we", pady=(0, 12))

    def _build_persistence_section(self) -> None:
        section, row = self._add_section(
            "Sessions & History",
            "Save new results or reload a previous capture without leaving the app.",
        )

        save_row = ctk.CTkFrame(section, fg_color="transparent")
        save_row.grid(row=row, column=0, sticky="we", padx=20, pady=(0, 12))
        save_row.grid_columnconfigure(0, weight=1)
        ctk.CTkEntry(
            save_row,
            placeholder_text="scan_results.json",
            textvariable=self.save_path_var,
            corner_radius=12,
            border_width=1,
        ).grid(row=0, column=0, sticky="we")
        ctk.CTkButton(
            save_row,
            text="Save as…",
            width=110,
            command=self.browse_save_path,
            fg_color=self.theme["button_secondary"],
            hover_color=self.theme["button_secondary_hover"],
            font=self.font_body,
            corner_radius=14,
        ).grid(row=0, column=1, padx=(12, 0))

        load_row = ctk.CTkFrame(section, fg_color="transparent")
        load_row.grid(row=row + 1, column=0, sticky="we", padx=20)
        load_row.grid_columnconfigure(0, weight=1)
        ctk.CTkEntry(
            load_row,
            placeholder_text="Load previous scan (optional)",
            textvariable=self.load_path_var,
            corner_radius=12,
            border_width=1,
        ).grid(row=0, column=0, sticky="we")
        ctk.CTkButton(
            load_row,
            text="Browse",
            width=110,
            command=self.browse_load_path,
            fg_color=self.theme["button_secondary"],
            hover_color=self.theme["button_secondary_hover"],
            font=self.font_body,
            corner_radius=14,
        ).grid(row=0, column=1, padx=(12, 0))

    def _build_addon_section(self) -> None:
        section, row = self._add_section(
            "Addon Autopatch",
            "Push discovered values to your addon configuration when you are ready to automate patches.",
        )

        ctk.CTkSwitch(
            section,
            text="Enable addon autopatch",
            variable=self.addon_enable_var,
        ).grid(row=row, column=0, sticky="we", padx=20, pady=(0, 12))

        form = ctk.CTkFrame(section, fg_color="transparent")
        form.grid(row=row + 1, column=0, sticky="we", padx=20, pady=(0, 4))
        form.grid_columnconfigure(0, weight=1)

        ctk.CTkEntry(
            form,
            placeholder_text="Patch value",
            textvariable=self.patch_value_var,
            corner_radius=12,
            border_width=1,
        ).grid(row=0, column=0, sticky="we", pady=(0, 12))

        patch_type_combo = ctk.CTkComboBox(
            form,
            values=["int32", "int64", "float", "double"],
            variable=self.patch_type_var,
        )
        patch_type_combo.grid(row=1, column=0, sticky="we", pady=(0, 12))
        self._style_dropdown(patch_type_combo)

        ctk.CTkEntry(
            form,
            placeholder_text="Auto threshold",
            textvariable=self.auto_threshold_var,
            corner_radius=12,
            border_width=1,
        ).grid(row=2, column=0, sticky="we", pady=(0, 12))

        ctk.CTkEntry(
            form,
            placeholder_text="Enforce interval (s)",
            textvariable=self.enforce_interval_var,
            corner_radius=12,
            border_width=1,
        ).grid(row=3, column=0, sticky="we", pady=(0, 12))

        ctk.CTkSwitch(
            form,
            text="Dry run (no writes)",
            variable=self.addon_dry_run_var,
        ).grid(row=4, column=0, sticky="we", pady=(0, 12))

        config_row = ctk.CTkFrame(form, fg_color="transparent")
        config_row.grid(row=5, column=0, sticky="we")
        config_row.grid_columnconfigure(0, weight=1)

        ctk.CTkEntry(
            config_row,
            textvariable=self.addon_config_var,
            placeholder_text="addon_config.json",
            corner_radius=12,
            border_width=1,
        ).grid(row=0, column=0, sticky="we", pady=(0, 12))
        ctk.CTkButton(
            config_row,
            text="Browse",
            width=100,
            command=self.browse_config,
            fg_color=self.theme["button_secondary"],
            hover_color=self.theme["button_secondary_hover"],
            font=self.font_body,
            corner_radius=14,
        ).grid(row=0, column=1, padx=(12, 0))

    def _build_action_section(self) -> None:
        section, row = self._add_section("Controls", "Ready when you are.")

        button_row = ctk.CTkFrame(section, fg_color="transparent")
        button_row.grid(row=row, column=0, sticky="we", padx=20, pady=(0, 16))
        button_row.grid_columnconfigure((0, 1), weight=1)

        ctk.CTkButton(
            button_row,
            text="Run Scan",
            command=self.start_scan,
            height=48,
            fg_color=self.theme["accent"],
            hover_color=self.theme["accent_alt"],
            font=ctk.CTkFont(size=16, weight="bold"),
            corner_radius=18,
        ).grid(row=0, column=0, sticky="we", padx=(0, 10))

        ctk.CTkButton(
            button_row,
            text="Stop",
            command=self.stop_process,
            height=48,
            fg_color=self.theme["button_secondary"],
            hover_color=self.theme["button_secondary_hover"],
            font=ctk.CTkFont(size=16, weight="bold"),
            corner_radius=18,
        ).grid(row=0, column=1, sticky="we")

        ctk.CTkLabel(
            section,
            text="Scans run through Python, mirroring the CLI experience with richer feedback.",
            text_color=self.theme["text_muted"],
            font=self.font_small,
            wraplength=360,
            justify="left",
        ).grid(row=row + 1, column=0, sticky="we", padx=20, pady=(0, 18))

        preview_card = ctk.CTkFrame(
            section,
            fg_color=self.theme["surface_alt"],
            corner_radius=18,
            border_width=1,
            border_color=self.theme["outline_subtle"],
        )
        preview_card.grid(row=row + 2, column=0, sticky="we", padx=20, pady=(0, 18))
        preview_card.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            preview_card,
            text="Command preview",
            font=self.font_body,
            text_color=self.theme["text_primary"],
        ).grid(row=0, column=0, sticky="w", padx=20, pady=(18, 6))

        self.command_preview = ctk.CTkTextbox(
            preview_card,
            height=72,
            wrap="word",
            corner_radius=14,
            fg_color=self.theme["panel"],
            text_color=self.theme["text_primary"],
            activate_scrollbars=False,
        )
        self.command_preview.grid(row=1, column=0, sticky="we", padx=20)
        self.command_preview.configure(state="disabled")

        ctk.CTkButton(
            preview_card,
            text="Copy to clipboard",
            command=self._copy_command_to_clipboard,
            fg_color=self.theme["accent"],
            hover_color=self.theme["accent_alt"],
            height=36,
            font=ctk.CTkFont(size=14, weight="bold"),
            corner_radius=14,
        ).grid(row=2, column=0, sticky="e", padx=20, pady=(14, 20))

        self._update_mode_visibility()

    # ------------------------------------------------------------------ UI helpers
    def _style_dropdown(self, widget: Any) -> None:
        options: Dict[str, object] = {
            "fg_color": self.theme["panel"],
            "text_color": self.theme["text_primary"],
            "button_color": self.theme["accent"],
            "button_hover_color": self.theme["accent_alt"],
            "dropdown_fg_color": self.theme["surface_alt"],
            "dropdown_hover_color": self.theme["accent_soft"],
            "corner_radius": 12,
        }
        for key, value in options.items():
            try:
                widget.configure(**{key: value})
            except (TclError, AttributeError, ValueError):
                continue

    def _on_scan_mode_change(self, value: str) -> None:
        self.scan_mode_var.set(value)
        self.dynamic_var.set(value == "Dynamic")
        self._update_mode_visibility()

    def _update_mode_visibility(self) -> None:
        if self.dynamic_var.get():
            self.dynamic_frame.grid()
            self.manual_frame.grid_remove()
            if hasattr(self, "notification_label"):
                self.notification_label.configure(
                    text="Dynamic scanning will probe smartly for likely matches."
                )
        else:
            self.manual_frame.grid()
            self.dynamic_frame.grid_remove()
            if hasattr(self, "notification_label"):
                self.notification_label.configure(
                    text="Manual mode will use the parameters you specify below."
                )

    def _apply_scan_preset(self, preset: str) -> None:
        presets: Dict[str, Dict[str, str]] = {
            "Balanced": {"max_steps": "4", "chunk_size": "16384", "value_kind": "int32"},
            "Fast sweep": {"max_steps": "3", "chunk_size": "12288", "value_kind": "float"},
            "Deep dive": {"max_steps": "7", "chunk_size": "24576", "value_kind": "int64"},
        }
        settings = presets.get(preset)
        if not settings:
            return
        self.max_steps_var.set(settings["max_steps"])
        self.chunk_size_var.set(settings["chunk_size"])
        self.value_kind_var.set(settings["value_kind"])
        self.notification_label.configure(text=f"Preset '{preset}' applied to the dynamic scanner.")

    def _set_status(self, text: str, running: bool) -> None:
        self.status_chip.configure(
            text=text,
            text_color=self.theme["text_primary"] if running else self.theme["accent"],
        )
        if running:
            self.status_card.configure(
                fg_color=self.theme["status_active"],
                border_color=self.theme["accent"],
            )
            self.status_caption.configure(text="Processing live output")
            self.status_chip.configure(fg_color=self.theme["accent"])
            if not self._status_animation_running:
                self.progress.grid()
                self.progress.start()
                self._status_animation_running = True
                self._schedule_status_pulse()
        else:
            self.status_card.configure(
                fg_color=self.theme["status_bg"],
                border_color=self.theme["outline"],
            )
            lowered = text.lower()
            if "stop" in lowered:
                caption = "Session halted by user"
            elif "error" in lowered:
                caption = "Attention required"
            elif "idle" in lowered:
                caption = "Standing by"
            else:
                caption = "Awaiting next scan"
            self.status_caption.configure(text=caption)
            self.status_chip.configure(fg_color=self.theme["status_idle_badge"])
            if self._status_animation_running:
                self.progress.stop()
                self.progress.grid_remove()
                self._status_animation_running = False
                self._cancel_status_pulse()

    def _animate_header_glow(self) -> None:
        self._pulse_phase = (self._pulse_phase + 0.06) % (2 * math.pi)
        blend = (1 - math.cos(self._pulse_phase)) / 2
        color = self._blend_colors(self.theme["accent"], self.theme["accent_alt"], blend)
        self.header_glow.configure(fg_color=color)
        self.after(40, self._animate_header_glow)

    def _schedule_status_pulse(self) -> None:
        if self._status_pulse_job is None:
            self._status_pulse_job = self.after(60, self._animate_status_chip)

    def _cancel_status_pulse(self) -> None:
        if self._status_pulse_job is not None:
            self.after_cancel(self._status_pulse_job)
            self._status_pulse_job = None
            self.status_chip.configure(fg_color=self.theme["status_idle_badge"])

    def _animate_status_chip(self) -> None:
        self._status_pulse_phase = (self._status_pulse_phase + 0.12) % (2 * math.pi)
        glow = (1 - math.cos(self._status_pulse_phase)) / 2
        color = self._blend_colors(self.theme["accent"], self.theme["accent_alt"], glow)
        self.status_chip.configure(fg_color=color)
        if self._status_animation_running:
            self._status_pulse_job = self.after(60, self._animate_status_chip)
        else:
            self._status_pulse_job = None

    @staticmethod
    def _blend_colors(color_a: str, color_b: str, amount: float) -> str:
        amount = max(0.0, min(1.0, amount))

        def to_rgb(hex_color: str) -> tuple[int, int, int]:
            hex_color = hex_color.lstrip("#")
            return tuple(int(hex_color[i : i + 2], 16) for i in (0, 2, 4))

        def to_hex(rgb_color: tuple[int, int, int]) -> str:
            return "#" + "".join(f"{component:02x}" for component in rgb_color)

        r1, g1, b1 = to_rgb(color_a)
        r2, g2, b2 = to_rgb(color_b)
        blended = (
            int(r1 + (r2 - r1) * amount),
            int(g1 + (g2 - g1) * amount),
            int(b1 + (b2 - b1) * amount),
        )
        return to_hex(blended)

    def _change_appearance(self, value: str) -> None:
        self.appearance_var.set(value)
        ctk.set_appearance_mode(value)
        self.notification_label.configure(text=f"Switched to {value.lower()} appearance.")

    def _show_help(self) -> None:
        message = (
            "Need a refresher?\n\n"
            "1. Choose Dynamic or Manual scanning.\n"
            "2. Apply a preset or tweak individual inputs.\n"
            "3. Optional: save new results or reload a previous JSON.\n"
            "4. Press Run Scan and watch the live output panel."
        )
        messagebox.showinfo("Quick tour", message)

    def _clear_output(self) -> None:
        self.output_text.configure(state="normal")
        self.output_text.delete("1.0", "end")
        self.output_text.configure(state="disabled")
        self.notification_label.configure(text="Console cleared. Ready for the next run.")

    def browse_save_path(self) -> None:
        file_path = filedialog.asksaveasfilename(
            initialdir=PROJECT_ROOT,
            title="Save scan results",
            defaultextension=".json",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
        )
        if file_path:
            self.save_path_var.set(file_path)

    def browse_load_path(self) -> None:
        file_path = filedialog.askopenfilename(
            initialdir=PROJECT_ROOT,
            title="Load existing scan",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
        )
        if file_path:
            self.load_path_var.set(file_path)

    # ------------------------------------------------------------------ Command construction
    def build_command(self) -> List[str]:
        cmd = [sys.executable, str(SCRIPT_PATH)]
        if pid := self.pid_var.get().strip():
            cmd += ["--pid", pid]
        if self.mock_var.get():
            cmd.append("--mock")

        if self.dynamic_var.get():
            cmd.append("--dynamic")
            if (steps := self.max_steps_var.get().strip()).isdigit():
                cmd += ["--max-steps", steps]
            if (chunk := self.chunk_size_var.get().strip()).isdigit():
                cmd += ["--chunk-size", chunk]
            if value_kind := self.value_kind_var.get().strip():
                cmd += ["--type", value_kind]
        else:
            cmd += ["--value-type", self.value_type_var.get()]
            if value := self.manual_value_var.get().strip():
                cmd += ["--value", value]

        if self.allow_rescan_var.get():
            cmd.append("--allow-rescan")
        if depth := self.reference_depth_var.get().strip():
            cmd += ["--reference-depth", depth]

        if self.addon_enable_var.get():
            cmd.append("--use-addon")
            if patch_value := self.patch_value_var.get().strip():
                cmd += ["--patch-value", patch_value]
            if patch_type := self.patch_type_var.get().strip():
                cmd += ["--patch-type", patch_type]
            if auto_thresh := self.auto_threshold_var.get().strip():
                cmd += ["--auto-threshold", auto_thresh]
            if interval := self.enforce_interval_var.get().strip():
                cmd += ["--enforce-interval", interval]
            if self.addon_dry_run_var.get():
                cmd.append("--dry-run")
            else:
                cmd.append("--patch-live")
            if config_path := self.addon_config_var.get().strip():
                cmd += ["--addon-config", config_path]
        if save_path := self.save_path_var.get().strip():
            cmd += ["--save", save_path]
        if load_path := self.load_path_var.get().strip():
            cmd += ["--load", load_path]
        return cmd

    def _refresh_command_preview(self, *args: object) -> None:
        if not hasattr(self, "command_preview"):
            return
        command = self.build_command()
        formatted = self._wrap_command(command) if command else "$"

        self.command_preview.configure(state="normal")
        self.command_preview.delete("1.0", "end")
        self.command_preview.insert("end", formatted)
        self.command_preview.configure(state="disabled")

    def _wrap_command(self, command: List[str]) -> str:
        quoted = [shlex.quote(part) for part in command]
        lines: List[str] = []
        current = "$"
        for piece in quoted:
            candidate = f"{current} {piece}" if current else piece
            if len(candidate) > 72:
                lines.append(current)
                current = "  " + piece
            else:
                current = candidate
        if current:
            lines.append(current)
        return "\n".join(lines)

    # ------------------------------------------------------------------ Actions
    def start_scan(self) -> None:
        if self.process_thread and self.process_thread.is_alive():
            messagebox.showinfo("Process running", "A scan is already in progress.")
            return
        if not SCRIPT_PATH.exists():
            messagebox.showerror("Missing script", f"Could not find {SCRIPT_PATH}")
            return

        command = self.build_command()
        self.append_output(f"\nLaunching: {' '.join(command)}\n", banner=True)
        self._set_status("Running…", True)
        self.notification_label.configure(text="Scan in progress. Watch the console for live updates.")
        self.process_thread = threading.Thread(
            target=self._run_process, args=(command,), daemon=True
        )
        self.process_thread.start()
        self.after(100, self._poll_queue)

    def stop_process(self) -> None:
        if self.process and self.process.poll() is None:
            self.process.terminate()
            self.append_output("\nProcess terminated by user.\n")
            self._set_status("Stopped", False)
            self.notification_label.configure(text="Scan halted. Adjust settings or run again when ready.")
        else:
            self._set_status("Idle", False)
            self.notification_label.configure(text="No scan active. Use Run Scan to get started.")

    def browse_config(self) -> None:
        file_path = filedialog.askopenfilename(
            initialdir=PROJECT_ROOT,
            title="Select addon_config.json",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
        )
        if file_path:
            self.addon_config_var.set(file_path)

    def _copy_command_to_clipboard(self) -> None:
        command = self.build_command()
        formatted = " ".join(shlex.quote(part) for part in command)
        self.clipboard_clear()
        self.clipboard_append(formatted)
        self.notification_label.configure(text="Command copied. Paste in a terminal to run manually.")

    # ------------------------------------------------------------------ Subprocess handling
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
        except FileNotFoundError:
            self.output_queue.put("Python executable not found.\n")
            self.process = None
            return

        assert self.process.stdout is not None
        for line in self.process.stdout:
            self.output_queue.put(line)
        self.process.wait()
        self.output_queue.put("\nProcess finished.\n")

    def _poll_queue(self) -> None:
        while not self.output_queue.empty():
            self.append_output(self.output_queue.get())
        if self.process_thread and self.process_thread.is_alive():
            self.after(100, self._poll_queue)
        else:
            self._set_status("Idle", False)
            self.notification_label.configure(text="Ready for the next scan. Adjust options on the left.")

    def append_output(self, text: str, banner: bool = False) -> None:
        self.output_text.configure(state="normal")
        if banner:
            self.output_text.insert("end", "-" * 60 + "\n")
        self.output_text.insert("end", text)
        if banner:
            self.output_text.insert("end", "-" * 60 + "\n")
        if self.auto_scroll_var.get():
            self.output_text.see("end")
        self.output_text.configure(state="disabled")

    def on_close(self) -> None:
        self.stop_process()
        self.destroy()

    def _setup_preview_traces(self) -> None:
        for var in (
            self.pid_var,
            self.mock_var,
            self.dynamic_var,
            self.scan_mode_var,
            self.max_steps_var,
            self.value_type_var,
            self.manual_value_var,
            self.allow_rescan_var,
            self.reference_depth_var,
            self.chunk_size_var,
            self.value_kind_var,
            self.addon_enable_var,
            self.patch_value_var,
            self.patch_type_var,
            self.auto_threshold_var,
            self.enforce_interval_var,
            self.addon_dry_run_var,
            self.addon_config_var,
            self.save_path_var,
            self.load_path_var,
        ):
            var.trace_add("write", self._refresh_command_preview)
        self._refresh_command_preview()


def main() -> None:
    app = InspectorGUI()
    app.mainloop()


if __name__ == "__main__":
    main()
