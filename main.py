"""Entry point. Wires the controller to the UI and starts the Qt event loop.

Run with: python main.py
"""
import sys
import io
import warnings
warnings.filterwarnings("ignore")

from dotenv import load_dotenv

# Fix for Python 3.14 + Windows terminal unicode bug
sys.stdin = io.TextIOWrapper(sys.stdin.buffer, encoding="utf-8", errors="replace")

# Load .env before importing modules that read os.getenv at import time
# (the ElevenLabs client is constructed at import).
load_dotenv()

from PyQt6.QtWidgets import QApplication
from asytrator.controller import AppController
from asytrator.ui import MainWindow


def main():
    app = QApplication(sys.argv)

    controller = AppController()
    window = MainWindow(controller)

    controller.start()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
