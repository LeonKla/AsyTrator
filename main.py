"""Entry point. Wires the controller to the UI and starts the Qt event loop.

Run with: python main.py
"""
import sys
import io
import os
import shutil
import warnings
warnings.filterwarnings("ignore")

from dotenv import load_dotenv

# Fix for Python 3.14 + Windows terminal unicode bug
sys.stdin = io.TextIOWrapper(sys.stdin.buffer, encoding="utf-8", errors="replace")

# Load .env before importing modules that read os.getenv at import time
# (the ElevenLabs client is constructed at import).
load_dotenv()


def _check_environment():
    """Warn early about missing dependencies so the user isn't surprised mid-use."""
    issues = []

    if not shutil.which("ffmpeg"):
        issues.append("ffmpeg is not installed or not on PATH — audio/video merging will fail.")

    if not os.getenv("ELEVENLABS_API_KEY"):
        issues.append("ELEVENLABS_API_KEY is not set — ElevenLabs dubbing will fail.")

    if not os.getenv("HEYGEN_API_KEY"):
        issues.append("HEYGEN_API_KEY is not set — HeyGen dubbing will fail.")

    return issues


from PyQt6.QtWidgets import QApplication, QMessageBox
from asytrator.controller import AppController
from asytrator.ui import MainWindow


def main():
    app = QApplication(sys.argv)

    warnings_list = _check_environment()
    if warnings_list:
        msg = QMessageBox()
        msg.setWindowTitle("AsyTrator — Setup Warnings")
        msg.setIcon(QMessageBox.Icon.Warning)
        msg.setText("Some features may not work:\n\n" + "\n".join(f"• {w}" for w in warnings_list))
        msg.exec()

    controller = AppController()
    window = MainWindow(controller)

    controller.start()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
