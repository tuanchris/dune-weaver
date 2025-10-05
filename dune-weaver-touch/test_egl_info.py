#!/usr/bin/env python3
import sys
import os

# Set kiosk environment
os.environ['QT_QPA_PLATFORM'] = 'eglfs'
os.environ['QT_DEBUG_PLUGINS'] = '1'
os.environ['QT_LOGGING_RULES'] = 'qt.qpa.*=true'

from PySide6.QtGui import QGuiApplication

app = QGuiApplication(sys.argv)
print("✅ Qt app created successfully")
print(f"Platform: {app.platformName()}")

# Try to get screen info
screens = app.screens()
print(f"Number of screens: {len(screens)}")
for i, screen in enumerate(screens):
    print(f"Screen {i}: {screen.size().width()}x{screen.size().height()}")
    
sys.exit(0)
