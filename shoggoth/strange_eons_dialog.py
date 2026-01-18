"""
Strange Eons Converter Dialog
"""
import sys
import subprocess
from pathlib import Path

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLineEdit, QPushButton, QLabel, QFileDialog,
    QDialogButtonBox, QProgressDialog, QMessageBox,
    QPlainTextEdit
)
from PySide6.QtCore import Qt, QProcess, QTimer


class StrangeEonsConverterDialog(QDialog):
    """Dialog for converting Strange Eons projects"""

    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.setWindowTitle("Convert Strange Eons Project")
        self.setMinimumWidth(500)

        layout = QVBoxLayout(self)

        # Form layout for inputs
        form = QFormLayout()

        # Java path
        java_layout = QHBoxLayout()
        self.java_input = QLineEdit()
        self.java_input.setText(self.settings.get('java_path', 'java'))
        self.java_input.setPlaceholderText("java (uses system default if empty)")
        java_browse = QPushButton("Browse...")
        java_browse.clicked.connect(self._browse_java)
        java_layout.addWidget(self.java_input)
        java_layout.addWidget(java_browse)
        form.addRow("Java Path:", java_layout)

        # Strange Eons JAR path
        jar_layout = QHBoxLayout()
        self.jar_input = QLineEdit()
        self.jar_input.setText(self.settings.get('strange_eons_path', ''))
        self.jar_input.setPlaceholderText("Path to strange-eons.jar")
        jar_browse = QPushButton("Browse...")
        jar_browse.clicked.connect(self._browse_jar)
        jar_layout.addWidget(self.jar_input)
        jar_layout.addWidget(jar_browse)
        form.addRow("Strange Eons JAR:", jar_layout)

        # SE Project path
        project_layout = QHBoxLayout()
        self.project_input = QLineEdit()
        self.project_input.setPlaceholderText("Path to Strange Eons project folder")
        project_browse = QPushButton("Browse...")
        project_browse.clicked.connect(self._browse_project)
        project_layout.addWidget(self.project_input)
        project_layout.addWidget(project_browse)
        form.addRow("SE Project:", project_layout)

        # Output folder
        output_layout = QHBoxLayout()
        self.output_input = QLineEdit()
        self.output_input.setPlaceholderText("Output folder for converted project")
        output_browse = QPushButton("Browse...")
        output_browse.clicked.connect(self._browse_output)
        output_layout.addWidget(self.output_input)
        output_layout.addWidget(output_browse)
        form.addRow("Output Folder:", output_layout)

        layout.addLayout(form)

        # Info label
        info = QLabel(
            "<i>Note: The conversion process will run in a separate process. "
            "This may take a while depending on the project size.</i>"
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        # Buttons
        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(self._start_conversion)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _browse_java(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Java Executable",
            filter="Executables (*);;All Files (*)"
        )
        if path:
            self.java_input.setText(path)

    def _browse_jar(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Strange Eons JAR",
            filter="JAR Files (*.jar);;All Files (*)"
        )
        if path:
            self.jar_input.setText(path)

    def _browse_project(self):
        path = QFileDialog.getExistingDirectory(
            self, "Select Strange Eons Project Folder"
        )
        if path:
            self.project_input.setText(path)
            # Auto-fill output if empty
            if not self.output_input.text():
                project_path = Path(path)
                self.output_input.setText(str(project_path.parent / f"{project_path.name}_converted"))

    def _browse_output(self):
        path = QFileDialog.getExistingDirectory(
            self, "Select Output Folder"
        )
        if path:
            self.output_input.setText(path)

    def _validate(self):
        """Validate inputs"""
        if not self.jar_input.text():
            QMessageBox.warning(self, "Error", "Please specify the Strange Eons JAR path.")
            return False

        jar_path = Path(self.jar_input.text())
        if not jar_path.exists():
            QMessageBox.warning(self, "Error", f"Strange Eons JAR not found: {jar_path}")
            return False

        if not self.project_input.text():
            QMessageBox.warning(self, "Error", "Please specify the Strange Eons project folder.")
            return False

        project_path = Path(self.project_input.text())
        if not project_path.exists():
            QMessageBox.warning(self, "Error", f"Project folder not found: {project_path}")
            return False

        if not self.output_input.text():
            QMessageBox.warning(self, "Error", "Please specify the output folder.")
            return False

        return True

    def _start_conversion(self):
        """Start the conversion process"""
        if not self._validate():
            return

        # Save settings for future use
        self.settings['java_path'] = self.java_input.text()
        self.settings['strange_eons_path'] = self.jar_input.text()

        # Store paths for the caller
        self.java_path = self.java_input.text() or 'java'
        self.jar_path = self.jar_input.text()
        self.project_path = self.project_input.text()
        self.output_path = self.output_input.text()

        self.accept()


class ConversionProgressDialog(QDialog):
    """Progress dialog for the conversion process"""

    def __init__(self, java_path, jar_path, project_path, output_path, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Converting Project...")
        self.setMinimumSize(600, 400)
        self.setModal(True)

        # Don't allow closing while running
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowCloseButtonHint)

        self.output_path = output_path
        self.process = None
        self.success = False

        layout = QVBoxLayout(self)

        self.status_label = QLabel("Starting conversion...")
        layout.addWidget(self.status_label)

        # Log output area
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setLineWrapMode(QPlainTextEdit.NoWrap)
        layout.addWidget(self.log_view, 1)  # stretch factor 1

        # Cancel button
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.clicked.connect(self._cancel)
        layout.addWidget(self.cancel_btn)

        # Start the process
        QTimer.singleShot(100, lambda: self._run_conversion(
            java_path, jar_path, project_path, output_path
        ))

    def _run_conversion(self, java_path, jar_path, project_path, output_path):
        """Run the conversion in a subprocess"""
        # Log configuration
        self._append_log("=== Strange Eons Conversion ===")
        self._append_log(f"Java: {java_path}")
        self._append_log(f"JAR: {jar_path}")
        self._append_log(f"Project: {project_path}")
        self._append_log(f"Output: {output_path}")
        self._append_log(f"Python: {sys.executable}")
        self._append_log("")

        # Create a Python script to run the conversion
        script = f'''
import sys
sys.path.insert(0, {repr(str(Path(__file__).parent.parent))})
from shoggoth.strange_eons import run_conversion
run_conversion(
    {repr(java_path)},
    {repr(jar_path)},
    {repr(project_path)},
    {repr(output_path)}
)
'''

        self.process = QProcess(self)
        self.process.finished.connect(self._on_finished)
        self.process.readyReadStandardOutput.connect(self._on_stdout)
        self.process.readyReadStandardError.connect(self._on_stderr)
        self.process.errorOccurred.connect(self._on_error)

        self.status_label.setText("Converting... (this may take a while)")

        # Run Python with the conversion script
        self.process.start(sys.executable, ['-c', script])

    def _append_log(self, text):
        """Append text to log view and scroll to bottom"""
        self.log_view.appendPlainText(text.rstrip('\n'))
        # Scroll to bottom
        scrollbar = self.log_view.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def _on_stdout(self):
        if self.process:
            output = self.process.readAllStandardOutput().data().decode()
            if output:
                self._append_log(output)

    def _on_stderr(self):
        if self.process:
            output = self.process.readAllStandardError().data().decode()
            if output:
                self._append_log(output)

    def _on_error(self, error):
        self.status_label.setText(f"Process Error: {error}")
        self._append_log(f"\n=== Process Error: {error} ===")
        self.cancel_btn.setText("Close")
        # Re-enable close button
        self.setWindowFlags(self.windowFlags() | Qt.WindowCloseButtonHint)
        self.show()

    def _on_finished(self, exit_code, exit_status):
        self.process = None
        self._append_log(f"\n=== Process finished with exit code {exit_code} ===")

        # Check if output was created
        output_project = Path(self.output_path) / "cards.json"
        if output_project.exists():
            self._append_log(f"Success: {output_project}")
            self.success = True
            self.accept()
        else:
            self.status_label.setText("Conversion completed but no project was created.")
            self._append_log(f"Expected output: {output_project}")
            self.cancel_btn.setText("Close")
            # Re-enable close button
            self.setWindowFlags(self.windowFlags() | Qt.WindowCloseButtonHint)
            self.show()

    def _cancel(self):
        if self.process and self.process.state() == QProcess.Running:
            self.process.kill()
            self.process.waitForFinished(1000)
        self.reject()

    def closeEvent(self, event):
        if self.process and self.process.state() == QProcess.Running:
            event.ignore()
        else:
            super().closeEvent(event)


def run_strange_eons_conversion(settings, parent=None):
    """
    Run the complete Strange Eons conversion workflow.

    Returns the path to the converted project if successful, None otherwise.
    """
    # Step 1: Show converter dialog
    dialog = StrangeEonsConverterDialog(settings, parent)
    if dialog.exec() != QDialog.Accepted:
        return None

    # Step 2: Run conversion with progress
    progress = ConversionProgressDialog(
        dialog.java_path,
        dialog.jar_path,
        dialog.project_path,
        dialog.output_path,
        parent
    )

    if progress.exec() != QDialog.Accepted or not progress.success:
        return None

    # Return path to open directly
    output_project = Path(dialog.output_path) / "cards.json"
    return str(output_project)
