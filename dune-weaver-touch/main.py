import sys
import os
import asyncio
import logging
from pathlib import Path
from PySide6.QtCore import QUrl, QTimer, QObject, QEvent, Slot
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine, qmlRegisterType
from qasync import QEventLoop

from backend import Backend
from models.pattern_model import PatternModel
from models.playlist_model import PlaylistModel
from png_cache_manager import ensure_png_cache_startup

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class ActivityEventFilter(QObject):
    """Event filter to track user activity for screen timeout (linuxfb compatible)"""

    def __init__(self):
        super().__init__()
        self.backend = None  # Will be set after QML loads
        self.activity_events = {
            QEvent.MouseButtonPress,
            QEvent.MouseButtonRelease,
            QEvent.MouseMove,
            QEvent.TouchBegin,
            QEvent.TouchUpdate,
            QEvent.TouchEnd,
            QEvent.KeyPress,
            QEvent.KeyRelease
        }

    @Slot(QObject)
    def set_backend(self, backend):
        """Set the backend instance after QML loads"""
        self.backend = backend
        logger.info("📡 Backend connected to activity event filter")

    def eventFilter(self, obj, event):
        """Filter events and reset activity timer on user interaction"""
        if self.backend and event.type() in self.activity_events:
            # Check if screen is currently off
            try:
                screen_was_off = not self.backend.property("screenOn")

                # Reset activity timer (will turn screen on if needed)
                self.backend.resetActivityTimer()

                # If screen was off, consume this event (don't let it through)
                # This prevents the wake-up touch from clicking buttons
                if screen_was_off:
                    logger.info("🖥️ Screen wake event consumed (not passed to UI)")
                    return True  # Consume the event

            except Exception as e:
                logger.error(f"Failed to reset activity timer: {e}")

        # Return False to let event propagate normally when screen is on
        return False

async def startup_tasks():
    """Run async startup tasks"""
    logger.info("🚀 Starting dune-weaver-touch async initialization...")

    # Ensure PNG cache is available for all WebP previews
    try:
        logger.info("🎨 Checking PNG preview cache...")
        png_cache_success = await ensure_png_cache_startup()
        if png_cache_success:
            logger.info("✅ PNG cache check completed successfully")
        else:
            logger.warning("⚠️ PNG cache check completed with warnings")
    except Exception as e:
        logger.error(f"❌ PNG cache check failed: {e}")

    logger.info("✨ dune-weaver-touch startup tasks completed")

def main():
    # Set Qt platform to linuxfb for Raspberry Pi compatibility (Linux only)
    # This must be set before QGuiApplication is created
    # Note: Startup scripts may have already set QT_QPA_PLATFORM with rotation parameters
    if 'QT_QPA_PLATFORM' not in os.environ:
        # Only use linuxfb on Linux systems (Raspberry Pi)
        # On macOS, let Qt use the native cocoa platform
        if sys.platform.startswith('linux'):
            # Default linuxfb (rotation handled by QML transform in main.qml)
            os.environ['QT_QPA_PLATFORM'] = 'linuxfb:fb=/dev/fb0'
            os.environ['QT_QPA_FONTDIR'] = '/usr/share/fonts'

            # Enable virtual keyboard on Linux kiosk
            os.environ['QT_IM_MODULE'] = 'qtvirtualkeyboard'
        else:
            logger.info(f"🖥️ Running on {sys.platform} - using native Qt platform")
    else:
        logger.info(f"🖥️ Using QT_QPA_PLATFORM from environment: {os.environ['QT_QPA_PLATFORM']}")

    app = QGuiApplication(sys.argv)

    # Setup async event loop
    loop = QEventLoop(app)
    asyncio.set_event_loop(loop)

    # Install global event filter for activity tracking (linuxfb compatible)
    # Create it early so it's ready when backend is created
    event_filter = ActivityEventFilter()
    app.installEventFilter(event_filter)
    logger.info("📡 Activity event filter installed")

    # Register types
    qmlRegisterType(Backend, "DuneWeaver", 1, 0, "Backend")
    qmlRegisterType(PatternModel, "DuneWeaver", 1, 0, "PatternModel")
    qmlRegisterType(PlaylistModel, "DuneWeaver", 1, 0, "PlaylistModel")

    # Load QML
    engine = QQmlApplicationEngine()

    # Store event filter reference so QML can access it
    engine.rootContext().setContextProperty("activityFilter", event_filter)

    qml_file = Path(__file__).parent / "qml" / "main.qml"
    engine.load(QUrl.fromLocalFile(str(qml_file)))

    if not engine.rootObjects():
        return -1
    
    # Schedule startup tasks after a brief delay to ensure event loop is running
    def schedule_startup():
        try:
            # Check if we're in an event loop context
            current_loop = asyncio.get_running_loop()
            current_loop.create_task(startup_tasks())
        except RuntimeError:
            # No running loop, create task directly
            asyncio.create_task(startup_tasks())
    
    # Use QTimer to delay startup tasks
    startup_timer = QTimer()
    startup_timer.timeout.connect(schedule_startup)
    startup_timer.setSingleShot(True)
    startup_timer.start(100)  # 100ms delay
    
    with loop:
        loop.run_forever()
    
    return 0

if __name__ == "__main__":
    sys.exit(main())