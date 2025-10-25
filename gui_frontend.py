"""
CustomTkinter GUI front-end for the Process Data Inspector project.

This layer wraps the existing CLI tool without replacing any behavior.
"""
from __future__ import annotations

import queue
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
        self.geometry("1200x780")
        self.minsize(1100, 700)
        self.protocol("WM_DELETE_WINDOW", self.on_close)

        self.output_queue: queue.Queue[str] = queue.Queue()
        self.process_thread: Optional[threading.Thread] = None
        self.process: Optional[subprocess.Popen] = None

        self._init_variables()
        self._build_layout()

    # ------------------------------------------------------------------ UI setup
    def _init_variables(self) -> None:
        self.pid_var = ctk.StringVar()
        self.mock_var = ctk.BooleanVar(value=False)
        self.dynamic_var = ctk.BooleanVar(value=True)
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
        self.grid_columnconfigure(0, weight=0)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        controls = ctk.CTkScrollableFrame(self, width=380, label_text="Scan Configuration")
        controls.grid(row=0, column=0, sticky="nsw", padx=16, pady=16)

        output_frame = ctk.CTkFrame(self)
        output_frame.grid(row=0, column=1, sticky="nsew", padx=(0, 16), pady=16)
        output_frame.grid_rowconfigure(1, weight=1)
        output_frame.grid_columnconfigure(0, weight=1)

        # --- Controls content
        row = 0
        def add_row(widget):
            nonlocal row
            widget.grid(row=row, column=0, pady=(0, 8), sticky="we")
            row += 1

        add_row(ctk.CTkLabel(controls, text="Process Settings", font=ctk.CTkFont(size=16, weight="bold")))
        pid_entry = ctk.CTkEntry(controls, placeholder_text="PID (optional)", textvariable=self.pid_var)
        add_row(pid_entry)
        add_row(ctk.CTkCheckBox(controls, text="Use mock mode", variable=self.mock_var))

        add_row(ctk.CTkLabel(controls, text="Scan Mode", font=ctk.CTkFont(size=16, weight="bold")))
        add_row(ctk.CTkCheckBox(controls, text="Dynamic scan (recommended)", variable=self.dynamic_var))
        add_row(
            ctk.CTkEntry(
                controls,
                placeholder_text="Max steps (dynamic)",
                textvariable=self.max_steps_var,
            )
        )
        add_row(
            ctk.CTkOptionMenu(
                controls,
                values=["int32", "int64", "float", "double"],
                variable=self.value_kind_var,
            )
        )

        add_row(ctk.CTkLabel(controls, text="Manual Scan Overrides", font=ctk.CTkFont(size=16, weight="bold")))
        add_row(
            ctk.CTkOptionMenu(
                controls,
                values=MANUAL_VALUE_TYPES,
                variable=self.value_type_var,
            )
        )
        add_row(ctk.CTkEntry(controls, placeholder_text="Manual value", textvariable=self.manual_value_var))
        add_row(ctk.CTkCheckBox(controls, text="Allow rescan", variable=self.allow_rescan_var))
        add_row(ctk.CTkEntry(controls, placeholder_text="Reference depth", textvariable=self.reference_depth_var))
        add_row(ctk.CTkEntry(controls, placeholder_text="Chunk size", textvariable=self.chunk_size_var))

        # --- Addon options
        add_row(ctk.CTkLabel(controls, text="Addon (Autopatch)", font=ctk.CTkFont(size=16, weight="bold")))
        add_row(ctk.CTkCheckBox(controls, text="Enable addon autopatch", variable=self.addon_enable_var))
        add_row(ctk.CTkEntry(controls, placeholder_text="Patch value", textvariable=self.patch_value_var))
        add_row(
            ctk.CTkOptionMenu(
                controls,
                values=["int32", "int64", "float", "double"],
                variable=self.patch_type_var,
            )
        )
        add_row(ctk.CTkEntry(controls, placeholder_text="Auto threshold", textvariable=self.auto_threshold_var))
        add_row(ctk.CTkEntry(controls, placeholder_text="Enforce interval (s)", textvariable=self.enforce_interval_var))
        add_row(ctk.CTkCheckBox(controls, text="Addon dry-run (no writes)", variable=self.addon_dry_run_var))

        config_frame = ctk.CTkFrame(controls)
        config_frame.grid_columnconfigure(0, weight=1)
        config_frame.grid(row=row, column=0, pady=(0, 8), sticky="we")
        ctk.CTkEntry(config_frame, textvariable=self.addon_config_var, placeholder_text="addon_config.json").grid(
            row=0, column=0, padx=(0, 6), sticky="we"
        )
        ctk.CTkButton(config_frame, text="Browse", width=80, command=self.browse_config).grid(row=0, column=1)
        row += 1

        # Action buttons
        ctk.CTkButton(controls, text="Run Scan", command=self.start_scan, height=40).grid(
            row=row, column=0, pady=(8, 4), sticky="we"
        )
        row += 1
        ctk.CTkButton(
            controls,
            text="Stop Process",
            command=self.stop_process,
            fg_color="#4a4a4a",
            hover_color="#5c5c5c",
        ).grid(row=row, column=0, pady=(0, 16), sticky="we")

        # --- Output area
        ctk.CTkLabel(
            output_frame,
            text="Command Output",
            font=ctk.CTkFont(size=18, weight="bold"),
        ).grid(row=0, column=0, sticky="w", padx=12, pady=(12, 6))

        self.output_text = ctk.CTkTextbox(output_frame, wrap="word", activate_scrollbars=True)
        self.output_text.grid(row=1, column=0, sticky="nsew", padx=12, pady=6)

        controls_tip = (
            "This GUI wraps process_inspector.py. "
            "Use responsibly for offline/singleplayer titles that you own."
        )
        ctk.CTkLabel(
            output_frame,
            text=controls_tip,
            wraplength=700,
            font=ctk.CTkFont(size=13),
        ).grid(row=2, column=0, sticky="we", padx=12, pady=(0, 12))

        self.progress = ctk.CTkProgressBar(output_frame, mode="indeterminate")
        self.progress.grid(row=3, column=0, sticky="we", padx=12, pady=(0, 12))

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
        self.progress.start()
        self.process_thread = threading.Thread(
            target=self._run_process, args=(command,), daemon=True
        )
        self.process_thread.start()
        self.after(100, self._poll_queue)

    def stop_process(self) -> None:
        if self.process and self.process.poll() is None:
            self.process.terminate()
            self.append_output("\nProcess terminated by user.\n")

    def browse_config(self) -> None:
        file_path = filedialog.askopenfilename(
            initialdir=PROJECT_ROOT,
            title="Select addon_config.json",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
        )
        if file_path:
            self.addon_config_var.set(file_path)

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
            self.progress.stop()

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


def main() -> None:
    app = InspectorGUI()
    app.mainloop()


if __name__ == "__main__":
    main()
