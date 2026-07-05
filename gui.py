import sys
import os
import importlib
import logging
from pathlib import Path
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                             QHBoxLayout, QPushButton, QFileDialog,
                             QTextEdit, QLabel, QLineEdit, QCheckBox, QGroupBox)
from PyQt6.QtCore import Qt, QThread, pyqtSignal


class QtLogHandler(logging.Handler):
    def __init__(self, signal):
        super().__init__()
        self.signal = signal

    def emit(self, record):
        msg = self.format(record)
        self.signal.emit(msg)

class ModuleWorker(QThread):
    log_signal = pyqtSignal(str)
    finished_signal = pyqtSignal()

    def __init__(self, mod_name, args_list, output_dir=None):
        super().__init__()
        self.mod_name = mod_name
        self.args_list = args_list
        self.output_dir = output_dir

    def run(self):
        # Create QtLogHandler
        handler = QtLogHandler(self.log_signal)
        handler.setFormatter(logging.Formatter('%(levelname)s: %(message)s'))
        
        # Get the root logger and clear existing handlers to avoid duplicates
        # This ensures logs go to our QtLogHandler instead of default StreamHandlers
        root_logger = logging.getLogger()
        for h in root_logger.handlers[:]:
            root_logger.removeHandler(h)
        
        # Add our QtLogHandler to root logger
        root_logger.addHandler(handler)
        
        # Add file handler to write logs to execution_logs.txt in output directory
        file_handler = None
        if self.output_dir:
            try:
                log_file = os.path.join(self.output_dir, "execution_logs.txt")
                file_handler = logging.FileHandler(log_file, mode='w')
                file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
                root_logger.addHandler(file_handler)
            except Exception as e:
                self.log_signal.emit(f"Warning: Could not create log file: {e}")
        
        # Enable propagation for all existing loggers to ensure they send logs to root
        # This captures logs from named loggers like "Orchestrator", "TransformEngine", etc.
        logging.getLogger("Orchestrator").setLevel(logging.DEBUG)
        logging.getLogger("TransformEngine").setLevel(logging.DEBUG)
        logging.getLogger("PlanGenerator").setLevel(logging.DEBUG)
        logging.getLogger("BinaryPatcher").setLevel(logging.DEBUG)
        logging.getLogger("AssemblerBridge").setLevel(logging.DEBUG)
        logging.getLogger("EntryPointRandomizer").setLevel(logging.DEBUG)
        logging.getLogger("PEAnalyzer").setLevel(logging.DEBUG)
        
        # Also handle __name__ based loggers (like in cfg_permutator.py)
        for name in logging.Logger.manager.loggerDict:
            logger = logging.getLogger(name)
            logger.setLevel(logging.DEBUG)
            logger.propagate = True
        
        try:
            # Absolute import from the modules package
            module = importlib.import_module(f"modules.{self.mod_name}")
            # Ensure your module main(args_list=None) is ready
            module.main(self.args_list)
        except Exception as e:
            self.log_signal.emit(f"Critical Error: {str(e)}")
        finally:
            root_logger.removeHandler(handler)
            if file_handler:
                root_logger.removeHandler(file_handler)
                file_handler.close()
            self.finished_signal.emit()

class PolyMorphGUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PolyMorph Orchestrator")
        self.resize(1200, 800)
        self.active_inputs = {} # Stores values for current module
        self.path_buttons = {}  # Stores references to path buttons for resetting
        self.apply_theme()
        self.init_ui()

    def apply_theme(self):
        """Apply elegant enterprise-level theme with gradients and curves."""
        self.setStyleSheet("""
            QMainWindow {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #2b2b2b, stop:1 #1e1e1e);
            }
            QWidget {
                font-family: 'Segoe UI', 'Roboto', sans-serif;
                font-size: 14px;
                color: #e0e0e0;
            }
            QLabel {
                color: #ffffff;
                font-weight: 600;
            }
            QGroupBox {
                background-color: rgba(255, 255, 255, 0.05);
                border: 1px solid #444;
                border-radius: 15px;
                margin-top: 1.5em;
                padding: 15px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top left;
                padding: 0 10px;
                color: #00b4d8;
                font-weight: bold;
                background-color: transparent;
            }
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #3c3c3c, stop:1 #303030);
                border: 1px solid #555;
                border-radius: 18px;
                padding: 8px 16px;
                min-height: 32px;
                font-weight: 600;
                color: #e0e0e0;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #4a4a4a, stop:1 #3c3c3c);
                border-color: #00b4d8;
            }
            QPushButton:pressed {
                background-color: #222;
            }
            /* Primary Action Button */
            QPushButton#ExecuteButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #007bff, stop:1 #0056b3);
                color: white;
                border: none;
            }
            QPushButton#ExecuteButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #0069d9, stop:1 #004494);
            }
            /* Stop Button */
            QPushButton#StopButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #dc3545, stop:1 #c82333);
                color: white;
                border: none;
            }
            QPushButton#StopButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #c82333, stop:1 #bd2130);
            }
            QLineEdit {
                border: 1px solid #555;
                border-radius: 12px;
                padding: 8px;
                background-color: #2b2b2b;
                color: #e0e0e0;
            }
            QLineEdit:focus {
                border: 2px solid #00b4d8;
            }
            QCheckBox {
                spacing: 15px;
                padding: 12px 20px;
                background-color: rgba(255, 255, 255, 0.08);
                border-radius: 22px;
                color: #e0e0e0;
                border: 1px solid #555;
                font-weight: 500;
            }
            QCheckBox:hover {
                background-color: rgba(255, 255, 255, 0.12);
                border-color: #00b4d8;
            }
            QCheckBox::indicator {
                width: 24px;
                height: 24px;
                border-radius: 12px;
                border: 2px solid #888;
                background-color: rgba(0,0,0,0.3);
            }
            QCheckBox::indicator:checked {
                background-color: #00b4d8;
                border-color: #00b4d8;
                image: none;
            }
        """)

    def init_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QHBoxLayout(central)

        # --- Sidebar ---
        sidebar = QVBoxLayout()

        sidebar.addSpacing(20)
        sidebar.addWidget(QLabel("<b>INPUTS</b>"))
        
        self.fields_container = QVBoxLayout()
        sidebar.addLayout(self.fields_container)
        sidebar.addStretch()

        # Control Buttons Layout
        controls_layout = QHBoxLayout()

        self.reset_btn = QPushButton("RESET")
        self.reset_btn.clicked.connect(self.reset_fields)
        controls_layout.addWidget(self.reset_btn)

        self.stop_btn = QPushButton("STOP")
        self.stop_btn.setObjectName("StopButton")
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self.stop_process)
        controls_layout.addWidget(self.stop_btn)

        sidebar.addLayout(controls_layout)

        self.run_btn = QPushButton("EXECUTE")
        self.run_btn.setObjectName("ExecuteButton")
        self.run_btn.setFixedHeight(50)
        self.run_btn.clicked.connect(self.run_process)
        sidebar.addWidget(self.run_btn)

        # --- Console ---
        self.console = QTextEdit()
        self.console.setReadOnly(True)
        # Keep console theme as requested
        self.console.setStyleSheet("background-color: #1e1e1e; color: #00ff00; font-family: 'Consolas'; font-size: 11pt;")
        
        layout.addLayout(sidebar, 1)
        layout.addWidget(self.console, 3)

        self.build_orchestrator_fields()

    def build_orchestrator_fields(self):
        # Clear existing
        for i in reversed(range(self.fields_container.count())):
            item = self.fields_container.itemAt(i)
            if item.widget(): item.widget().setParent(None)
            elif item.layout(): self.clear_layout(item.layout())

        self.active_inputs = {}
        self.path_buttons = {}

        # Required paths
        required_group = QGroupBox("Inputs")
        required_layout = QVBoxLayout()
        required_group.setLayout(required_layout)
        self.fields_container.addWidget(required_group)

        # --input
        btn_input = QPushButton("Select Input Binary...")
        btn_input.clicked.connect(lambda: self.get_path("--input", "file", "Executable (*.exe *.dll)", btn_input))
        required_layout.addWidget(btn_input)
        self.path_buttons["--input"] = btn_input

        # --config
        btn_config = QPushButton("Select Config File...")
        btn_config.clicked.connect(lambda: self.get_path("--config", "file", "JSON files (*.json)", btn_config))
        required_layout.addWidget(btn_config)
        self.path_buttons["--config"] = btn_config

        # --output
        btn_output = QPushButton("Select Output Directory...")
        btn_output.clicked.connect(lambda: self.get_path("--output", "dir", "", btn_output))
        required_layout.addWidget(btn_output)
        self.path_buttons["--output"] = btn_output

        # Optional arguments
        optional_group = QGroupBox("Optional Parameters")
        optional_layout = QVBoxLayout()
        optional_group.setLayout(optional_layout)
        self.fields_container.addWidget(optional_group)

        # --count
        row = QHBoxLayout()
        row.addWidget(QLabel("Instruction Transform Count:"))
        edit = QLineEdit()
        row.addWidget(edit)
        optional_layout.addLayout(row)
        self.active_inputs["--count"] = edit

        # --cfg-count
        row = QHBoxLayout()
        row.addWidget(QLabel("CFG Swap Count:"))
        edit = QLineEdit()
        row.addWidget(edit)
        optional_layout.addLayout(row)
        self.active_inputs["--cfg-count"] = edit

        # --cfg-subset-pct
        row = QHBoxLayout()
        row.addWidget(QLabel("CFG Subset Pct (0.0-1.0):"))
        edit = QLineEdit()
        row.addWidget(edit)
        optional_layout.addLayout(row)
        self.active_inputs["--cfg-subset-pct"] = edit

        # --cfg-seed
        row = QHBoxLayout()
        row.addWidget(QLabel("CFG Seed:"))
        edit = QLineEdit()
        row.addWidget(edit)
        optional_layout.addLayout(row)
        self.active_inputs["--cfg-seed"] = edit

        # Flags
        flags_group = QGroupBox("Flags")
        flags_layout = QVBoxLayout()
        flags_group.setLayout(flags_layout)
        self.fields_container.addWidget(flags_group)

        # --cfg-enable-subset
        chk = QCheckBox("Enable CFG Subset Selection")
        chk.setCursor(Qt.CursorShape.PointingHandCursor)
        chk.setChecked(True)
        flags_layout.addWidget(chk)
        self.active_inputs["--cfg-enable-subset"] = chk

        # --divide-transform
        chk = QCheckBox("Enable Distribution Shuffling (Divide & Transform)")
        chk.setCursor(Qt.CursorShape.PointingHandCursor)
        flags_layout.addWidget(chk)
        self.active_inputs["--divide-transform"] = chk

        # --verbose
        chk = QCheckBox("Verbose Logging")
        chk.setCursor(Qt.CursorShape.PointingHandCursor)
        flags_layout.addWidget(chk)
        self.active_inputs["--verbose"] = chk

        # --quiet
        chk = QCheckBox("Quiet Mode")
        chk.setCursor(Qt.CursorShape.PointingHandCursor)
        flags_layout.addWidget(chk)
        self.active_inputs["--quiet"] = chk

    def clear_layout(self, layout):
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
            else:
                sub_layout = item.layout()
                if sub_layout:
                    self.clear_layout(sub_layout)

    def get_path(self, flag, path_type, ext, btn):
        if path_type == "file":
            path, _ = QFileDialog.getOpenFileName(self, f"Select {flag}", "", ext)
        else:
            path = QFileDialog.getExistingDirectory(self, f"Select {flag}")
        
        if path:
            self.active_inputs[flag] = path
            # Enterprise success style
            btn.setStyleSheet("border: 1px solid #28a745; background-color: #1e4d2b; color: #75b798; font-weight: bold; border-radius: 18px;")
            btn.setText(f"{os.path.basename(path)}")
            self.console.append(f"[SET] {flag} -> {os.path.basename(path)}")

    def reset_fields(self):
        """Reset all selections and inputs."""
        # Reset path buttons
        for flag, btn in self.path_buttons.items():
            if flag in self.active_inputs:
                del self.active_inputs[flag]
            # Revert to default style (empty stylesheet uses the global theme)
            btn.setStyleSheet("")
            if flag == "--input": btn.setText("Select Input Binary...")
            elif flag == "--config": btn.setText("Select Config File...")
            elif flag == "--output": btn.setText("Select Output Directory...")

        # Reset LineEdits and CheckBoxes
        for key, widget in self.active_inputs.items():
            if isinstance(widget, QLineEdit):
                widget.clear()
            elif isinstance(widget, QCheckBox):
                # Restore defaults
                if key == "--cfg-enable-subset":
                    widget.setChecked(True)
                else:
                    widget.setChecked(False)
        
        self.console.clear()
        self.console.append("[INFO] All fields reset.")

    def stop_process(self):
        """Stop the execution thread."""
        if hasattr(self, 'worker') and self.worker.isRunning():
            self.console.append("<b style='color:#d9534f;'>[!] Stopping execution...</b>")
            # Disconnect finished signal to avoid double calling execution_finished
            try:
                self.worker.finished_signal.disconnect(self.execution_finished)
            except TypeError:
                pass 
            
            self.worker.terminate()
            # Wait max 1 second for thread to clean up, then force UI update
            if not self.worker.wait(1000):
                self.console.append("Warning: Thread did not terminate gracefully.")
            
            self.console.append("<b style='color:#d9534f;'>[!] Execution STOPPED by user.</b>")
            self.execution_finished()

    def run_process(self):
        mod_name = "orchestrator"
        
        # Build Args List
        args_list = []
        
        # Required
        for flag in ["--input", "--config", "--output"]:
            val = self.active_inputs.get(flag)
            if not isinstance(val, str) or not val:
                self.console.append(f"<b style='color:red;'>[!] Error: {flag} is required.</b>")
                return
            args_list.extend([flag, val])
        
        # Optional with values
        for flag in ["--count", "--cfg-count", "--cfg-subset-pct", "--cfg-seed"]:
            widget = self.active_inputs.get(flag)
            if widget and widget.text():
                args_list.extend([flag, widget.text()])
        
        # Optional flags
        if self.active_inputs["--cfg-enable-subset"].isChecked():
            args_list.append("--cfg-enable-subset")
        else:
            args_list.append("--cfg-no-subset")

        if self.active_inputs["--divide-transform"].isChecked():
            args_list.append("--divide-transform")

        if self.active_inputs["--verbose"].isChecked():
            args_list.append("-v")

        if self.active_inputs["--quiet"].isChecked():
            args_list.append("-q")

        self.run_btn.setEnabled(False)
        self.reset_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        
        self.console.append(f"\n--- EXECUTION STARTED ---")
        output_dir = self.active_inputs["--output"]
        
        self.worker = ModuleWorker(mod_name, args_list, output_dir)
        self.worker.log_signal.connect(self.console.append)
        self.worker.finished_signal.connect(self.execution_finished)
        self.worker.start()

    def execution_finished(self):
        self.run_btn.setEnabled(True)
        self.reset_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = PolyMorphGUI()
    window.show()
    sys.exit(app.exec())