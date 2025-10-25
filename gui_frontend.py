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
from typing import List, Optional

try:
    import customtkinter as ctk
    from tkinter import filedialog, messagebox
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
            "bg": "#0f172a",
            "panel": "#111c34",
            "panel_alt": "#14203d",
            "accent": "#38bdf8",
            "accent_alt": "#818cf8",
            "text_primary": "#f8fafc",
            "text_muted": "#94a3b8",
            "chip_bg": "#1e293b",
        }

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

    def _build_layout(self) -> None:
        self.configure(fg_color=self.theme["bg"])
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        # --- Header
        header = ctk.CTkFrame(self, fg_color=self.theme["panel"], corner_radius=0)
        header.grid(row=0, column=0, sticky="ew")
        header.grid_columnconfigure(0, weight=1)
        header.grid_columnconfigure(1, weight=0)

        title = ctk.CTkLabel(
            header,
            text="Process Data Inspector",
            font=ctk.CTkFont(size=26, weight="bold"),
            text_color=self.theme["text_primary"],
        )
        title.grid(row=0, column=0, sticky="w", padx=24, pady=(18, 4))

        subtitle = ctk.CTkLabel(
            header,
            text="Curate scan strategies with realtime feedback.",
            font=ctk.CTkFont(size=14),
            text_color=self.theme["text_muted"],
        )
        subtitle.grid(row=1, column=0, sticky="w", padx=24, pady=(0, 12))

        self.status_chip = ctk.CTkLabel(
            header,
            text="Idle",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=self.theme["accent"],
            fg_color=self.theme["chip_bg"],
            corner_radius=12,
            padx=16,
            pady=8,
        )
        self.status_chip.grid(row=0, column=1, padx=24, pady=(18, 4))

        self.header_glow = ctk.CTkFrame(header, fg_color=self.theme["accent"], height=4, corner_radius=0)
        self.header_glow.grid(row=2, column=0, columnspan=2, sticky="ew")

        # --- Main body
        body = ctk.CTkFrame(self, fg_color="transparent")
        body.grid(row=1, column=0, sticky="nsew", padx=24, pady=(18, 24))
        body.grid_rowconfigure(0, weight=1)
        body.grid_columnconfigure(0, weight=0)
        body.grid_columnconfigure(1, weight=1)

        self.controls_panel = ctk.CTkScrollableFrame(
            body,
            width=420,
            fg_color=self.theme["panel_alt"],
            corner_radius=18,
            label_text="Scan Configuration",
            label_font=ctk.CTkFont(size=18, weight="bold"),
        )
        self.controls_panel.grid(row=0, column=0, sticky="nsw", padx=(0, 24))
        self.controls_panel.grid_columnconfigure(0, weight=1)

        self._section_row = 0
        self._build_process_section()
        self._build_scan_section()
        self._build_manual_section()
        self._build_addon_section()
        self._build_action_section()

        # --- Output area
        self.output_card = ctk.CTkFrame(body, fg_color=self.theme["panel"], corner_radius=22)
        self.output_card.grid(row=0, column=1, sticky="nsew")
        self.output_card.grid_columnconfigure(0, weight=1)
        self.output_card.grid_rowconfigure(2, weight=1)

        ctk.CTkLabel(
            self.output_card,
            text="Command Output",
            font=ctk.CTkFont(size=22, weight="bold"),
            text_color=self.theme["text_primary"],
        ).grid(row=0, column=0, sticky="w", padx=24, pady=(24, 6))

        self.notification_label = ctk.CTkLabel(
            self.output_card,
            text="Ready to orchestrate your scans.",
            text_color=self.theme["text_muted"],
            font=ctk.CTkFont(size=14),
        )
        self.notification_label.grid(row=1, column=0, sticky="w", padx=24, pady=(0, 12))

        self.output_text = ctk.CTkTextbox(
            self.output_card,
            wrap="word",
            activate_scrollbars=True,
            corner_radius=16,
            fg_color=self.theme["panel_alt"],
            text_color=self.theme["text_primary"],
        )
        self.output_text.grid(row=2, column=0, sticky="nsew", padx=24, pady=(0, 18))

        controls_tip = (
            "This interface wraps process_inspector.py. "
            "Operate responsibly on single-player experiences you own."
        )
        ctk.CTkLabel(
            self.output_card,
            text=controls_tip,
            wraplength=720,
            text_color=self.theme["text_muted"],
            font=ctk.CTkFont(size=13),
        ).grid(row=3, column=0, sticky="we", padx=24, pady=(0, 12))

        self.progress = ctk.CTkProgressBar(
            self.output_card,
            mode="indeterminate",
            corner_radius=10,
            determinate_speed=1.8,
        )
        self.progress.grid(row=4, column=0, sticky="we", padx=24, pady=(0, 24))
        self.progress.grid_remove()

    # ------------------------------------------------------------------ Section builders
    def _add_section(self, title: str, description: str | None = None) -> ctk.CTkFrame:
        section = ctk.CTkFrame(self.controls_panel, fg_color=self.theme["panel"], corner_radius=18)
        section.grid(row=self._section_row, column=0, sticky="we", padx=18, pady=(18 if self._section_row == 0 else 12, 0))
        section.grid_columnconfigure(0, weight=1)
        self._section_row += 1

        ctk.CTkLabel(
            section,
            text=title,
            text_color=self.theme["text_primary"],
            font=ctk.CTkFont(size=18, weight="bold"),
        ).grid(row=0, column=0, sticky="w", padx=18, pady=(18, 4))

        if description:
            ctk.CTkLabel(
                section,
                text=description,
                text_color=self.theme["text_muted"],
                font=ctk.CTkFont(size=13),
                wraplength=360,
                justify="left",
            ).grid(row=1, column=0, sticky="we", padx=18, pady=(0, 12))
            row = 2
        else:
            row = 1

        spacer = ctk.CTkFrame(section, fg_color="transparent", height=2)
        spacer.grid(row=row, column=0, sticky="we", padx=18, pady=(0, 10))
        section.rowconfigure(row, minsize=2)
        return section

    def _build_process_section(self) -> None:
        section = self._add_section(
            "Target Process",
            "Connect to a running process using its PID or experiment with the mock mode for demos.",
        )

        ctk.CTkEntry(
            section,
            placeholder_text="PID (optional)",
            textvariable=self.pid_var,
        ).grid(row=2, column=0, sticky="we", padx=18, pady=(0, 10))

        ctk.CTkSwitch(
            section,
            text="Use mock process data",
            variable=self.mock_var,
        ).grid(row=3, column=0, sticky="we", padx=18, pady=(0, 12))

    def _build_scan_section(self) -> None:
        section = self._add_section(
            "Scan Strategy",
            "Toggle between dynamic smart scanning and manual targeting depending on your workflow.",
        )

        segmented = ctk.CTkSegmentedButton(
            section,
            values=["Dynamic", "Manual"],
            command=self._on_scan_mode_change,
            variable=self.scan_mode_var,
        )
        segmented.grid(row=2, column=0, sticky="we", padx=18, pady=(0, 12))
        segmented.set("Dynamic" if self.dynamic_var.get() else "Manual")

        self.dynamic_frame = ctk.CTkFrame(section, fg_color="transparent")
        self.dynamic_frame.grid(row=3, column=0, sticky="we", padx=18)
        self.dynamic_frame.grid_columnconfigure(0, weight=1)

        ctk.CTkEntry(
            self.dynamic_frame,
            placeholder_text="Max steps",
            textvariable=self.max_steps_var,
        ).grid(row=0, column=0, sticky="we", pady=(0, 10))

        ctk.CTkOptionMenu(
            self.dynamic_frame,
            values=["int32", "int64", "float", "double"],
            variable=self.value_kind_var,
        ).grid(row=1, column=0, sticky="we", pady=(0, 10))

        ctk.CTkEntry(
            self.dynamic_frame,
            placeholder_text="Chunk size",
            textvariable=self.chunk_size_var,
        ).grid(row=2, column=0, sticky="we", pady=(0, 10))

    def _build_manual_section(self) -> None:
        section = self._add_section(
            "Manual Overrides",
            "Fine tune scan values and thresholds when you know exactly what to look for.",
        )

        self.manual_frame = ctk.CTkFrame(section, fg_color="transparent")
        self.manual_frame.grid(row=2, column=0, sticky="we", padx=18)
        self.manual_frame.grid_columnconfigure(0, weight=1)

        ctk.CTkOptionMenu(
            self.manual_frame,
            values=MANUAL_VALUE_TYPES,
            variable=self.value_type_var,
        ).grid(row=0, column=0, sticky="we", pady=(0, 10))

        ctk.CTkEntry(
            self.manual_frame,
            placeholder_text="Manual value",
            textvariable=self.manual_value_var,
        ).grid(row=1, column=0, sticky="we", pady=(0, 10))

        ctk.CTkSwitch(
            self.manual_frame,
            text="Allow rescan",
            variable=self.allow_rescan_var,
        ).grid(row=2, column=0, sticky="we", pady=(0, 10))

        ctk.CTkEntry(
            self.manual_frame,
            placeholder_text="Reference depth",
            textvariable=self.reference_depth_var,
        ).grid(row=3, column=0, sticky="we", pady=(0, 10))

    def _build_addon_section(self) -> None:
        section = self._add_section(
            "Addon Autopatch",
            "Push discovered values to your addon configuration when you are ready to automate patches.",
        )

        ctk.CTkSwitch(
            section,
            text="Enable addon autopatch",
            variable=self.addon_enable_var,
        ).grid(row=2, column=0, sticky="we", padx=18, pady=(0, 12))

        form = ctk.CTkFrame(section, fg_color="transparent")
        form.grid(row=3, column=0, sticky="we", padx=18)
        form.grid_columnconfigure(0, weight=1)

        ctk.CTkEntry(form, placeholder_text="Patch value", textvariable=self.patch_value_var).grid(
            row=0, column=0, sticky="we", pady=(0, 10)
        )

        ctk.CTkOptionMenu(
            form,
            values=["int32", "int64", "float", "double"],
            variable=self.patch_type_var,
        ).grid(row=1, column=0, sticky="we", pady=(0, 10))

        ctk.CTkEntry(form, placeholder_text="Auto threshold", textvariable=self.auto_threshold_var).grid(
            row=2, column=0, sticky="we", pady=(0, 10)
        )

        ctk.CTkEntry(form, placeholder_text="Enforce interval (s)", textvariable=self.enforce_interval_var).grid(
            row=3, column=0, sticky="we", pady=(0, 10)
        )

        ctk.CTkSwitch(
            form,
            text="Dry run (no writes)",
            variable=self.addon_dry_run_var,
        ).grid(row=4, column=0, sticky="we", pady=(0, 12))

        config_row = ctk.CTkFrame(form, fg_color="transparent")
        config_row.grid(row=5, column=0, sticky="we")
        config_row.grid_columnconfigure(0, weight=1)

        ctk.CTkEntry(config_row, textvariable=self.addon_config_var, placeholder_text="addon_config.json").grid(
            row=0, column=0, sticky="we", pady=(0, 12)
        )
        ctk.CTkButton(config_row, text="Browse", width=100, command=self.browse_config).grid(
            row=0, column=1, padx=(12, 0)
        )

    def _build_action_section(self) -> None:
        section = self._add_section("Controls", "Ready when you are.")

        button_row = ctk.CTkFrame(section, fg_color="transparent")
        button_row.grid(row=2, column=0, sticky="we", padx=18, pady=(0, 12))
        button_row.grid_columnconfigure((0, 1), weight=1)

        ctk.CTkButton(
            button_row,
            text="Run Scan",
            command=self.start_scan,
            height=48,
            fg_color=self.theme["accent"],
            hover_color=self.theme["accent_alt"],
            font=ctk.CTkFont(size=16, weight="bold"),
        ).grid(row=0, column=0, sticky="we", padx=(0, 10))

        ctk.CTkButton(
            button_row,
            text="Stop",
            command=self.stop_process,
            height=48,
            fg_color="#1f2937",
            hover_color="#293548",
            font=ctk.CTkFont(size=16, weight="bold"),
        ).grid(row=0, column=1, sticky="we")

        ctk.CTkLabel(
            section,
            text="Scans run through Python, mirroring the CLI experience with richer feedback.",
            text_color=self.theme["text_muted"],
            font=ctk.CTkFont(size=12),
            wraplength=360,
            justify="left",
        ).grid(row=3, column=0, sticky="we", padx=18, pady=(0, 18))

        preview_card = ctk.CTkFrame(section, fg_color=self.theme["panel"], corner_radius=16)
        preview_card.grid(row=4, column=0, sticky="we", padx=18, pady=(0, 18))
        preview_card.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            preview_card,
            text="Command preview",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=self.theme["text_primary"],
        ).grid(row=0, column=0, sticky="w", padx=16, pady=(16, 6))

        self.command_preview = ctk.CTkTextbox(
            preview_card,
            height=72,
            wrap="word",
            corner_radius=12,
            fg_color=self.theme["panel_alt"],
            text_color=self.theme["text_primary"],
            activate_scrollbars=False,
        )
        self.command_preview.grid(row=1, column=0, sticky="we", padx=16)
        self.command_preview.configure(state="disabled")

        ctk.CTkButton(
            preview_card,
            text="Copy to clipboard",
            command=self._copy_command_to_clipboard,
            fg_color=self.theme["accent"],
            hover_color=self.theme["accent_alt"],
            height=36,
            font=ctk.CTkFont(size=14, weight="bold"),
        ).grid(row=2, column=0, sticky="e", padx=16, pady=(12, 16))

        self._update_mode_visibility()

    # ------------------------------------------------------------------ UI helpers
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

    def _set_status(self, text: str, running: bool) -> None:
        self.status_chip.configure(
            text=text,
            text_color=self.theme["accent"] if running else self.theme["text_muted"],
            fg_color="#1b2c4b" if running else self.theme["chip_bg"],
        )
        if running and not self._status_animation_running:
            self.progress.grid()
            self.progress.start()
            self._status_animation_running = True
            self._schedule_status_pulse()
        elif not running and self._status_animation_running:
            self.progress.stop()
            self.progress.grid_remove()
            self._status_animation_running = False
            self._cancel_status_pulse()

    def _animate_header_glow(self) -> None:
        self._pulse_phase = (self._pulse_phase + 0.12) % (2 * math.pi)
        blend = (math.sin(self._pulse_phase) + 1) / 2
        color = self._blend_colors(self.theme["accent"], self.theme["accent_alt"], blend)
        self.header_glow.configure(fg_color=color)
        self.after(80, self._animate_header_glow)

    def _schedule_status_pulse(self) -> None:
        if self._status_pulse_job is None:
            self._status_pulse_job = self.after(90, self._animate_status_chip)

    def _cancel_status_pulse(self) -> None:
        if self._status_pulse_job is not None:
            self.after_cancel(self._status_pulse_job)
            self._status_pulse_job = None
            self.status_chip.configure(fg_color="#1b2c4b")

    def _animate_status_chip(self) -> None:
        self._status_pulse_phase = (self._status_pulse_phase + 0.18) % (2 * math.pi)
        glow = (math.sin(self._status_pulse_phase) + 1) / 2
        color = self._blend_colors("#2563eb", "#38bdf8", glow)
        self.status_chip.configure(fg_color=color)
        if self._status_animation_running:
            self._status_pulse_job = self.after(90, self._animate_status_chip)
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
        ):
            var.trace_add("write", self._refresh_command_preview)
        self._refresh_command_preview()


def main() -> None:
    app = InspectorGUI()
    app.mainloop()


if __name__ == "__main__":
    main()
