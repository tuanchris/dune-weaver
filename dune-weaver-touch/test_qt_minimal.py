#!/usr/bin/env python3
"""
Minimal Qt/QML test app for kiosk mode debugging
Tests basic Qt functionality without complex effects or image loading
"""
import sys
import os
from pathlib import Path
from PySide6.QtCore import QUrl
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine

def main():
    # Check for kiosk mode flag
    kiosk_mode = '--kiosk' in sys.argv or os.environ.get('KIOSK_MODE', '0') == '1'

    if kiosk_mode:
        # Set Qt platform for fullscreen framebuffer mode
        # Try linuxfb instead of eglfs (software rendering, no GPU)
        os.environ['QT_QPA_PLATFORM'] = 'linuxfb'
        os.environ['QT_QPA_FB_DRM'] = '0'  # Disable DRM
        print("🖥️  Running in KIOSK MODE (linuxfb - software rendering)")
    else:
        print("🪟 Running in WINDOWED MODE (development)")
        print("   Use --kiosk flag or set KIOSK_MODE=1 for fullscreen")

    app = QGuiApplication(sys.argv)

    # Load minimal QML
    engine = QQmlApplicationEngine()
    qml_file = Path(__file__).parent / "test_minimal.qml"
    engine.load(QUrl.fromLocalFile(str(qml_file)))

    if not engine.rootObjects():
        print("❌ Failed to load QML")
        return -1

    print("✅ Qt app started successfully")
    return app.exec()

if __name__ == "__main__":
    sys.exit(main())
