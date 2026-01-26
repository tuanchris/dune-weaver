import sys
import os
import asyncio
import logging
import time
import signal
from pathlib import Path
from PySide6.QtCore import QUrl, QTimer, QObject, QEvent
from PySide6.QtGui import QGuiApplication, QTouchEvent, QMouseEvent
from PySide6.QtQml import QQmlApplicationEngine, qmlRegisterType, QQmlContext
from qasync import QEventLoop

# Load environment variables from .env file if it exists
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / ".env")

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

class FirstTouchFilter(QObject):
    """
    Event filter that ignores the first touch event after inactivity.
    Many capacitive touchscreens need the first touch to wake up or calibrate,
    and this touch often has incorrect coordinates.
    """
    def __init__(self, idle_threshold_seconds=2.0):
        super().__init__()
        self.idle_threshold = idle_threshold_seconds
        self.last_touch_time = 0
        self.ignore_next_touch = False
        logger.info(f"👆 First-touch filter initialized (idle threshold: {idle_threshold_seconds}s)")

    def eventFilter(self, obj, event):
        """Filter out the first touch after idle period"""
        try:
            event_type = event.type()

            # Handle touch events
            if event_type == QEvent.Type.TouchBegin:
                current_time = time.time()
                time_since_last_touch = current_time - self.last_touch_time

                # If it's been more than threshold since last touch, ignore this one
                if time_since_last_touch > self.idle_threshold:
                    logger.debug(f"👆 Ignoring wake-up touch (idle for {time_since_last_touch:.1f}s)")
                    self.last_touch_time = current_time
                    return True  # Filter out (ignore) this event

                self.last_touch_time = current_time

            elif event_type in (QEvent.Type.TouchUpdate, QEvent.Type.TouchEnd):
                # Update last touch time for any touch activity
                self.last_touch_time = time.time()

            # Pass through the event
            return False
        except KeyboardInterrupt:
            # Re-raise KeyboardInterrupt to allow clean shutdown
            raise
        except Exception as e:
            logger.error(f"Error in eventFilter: {e}")
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

def is_pi5():
    """Check if running on Raspberry Pi 5"""
    try:
        with open('/proc/device-tree/model', 'r') as f:
            model = f.read()
            return 'Pi 5' in model
    except:
        return False

def main():
    # Enable virtual keyboard
    os.environ['QT_IM_MODULE'] = 'qtvirtualkeyboard'

    app = QGuiApplication(sys.argv)

    # Install first-touch filter to ignore wake-up touches
    first_touch_filter = FirstTouchFilter(idle_threshold_seconds=2.0)
    app.installEventFilter(first_touch_filter)
    logger.info("✅ First-touch filter installed on application")

    # Setup async event loop using QEventLoop
    # This properly integrates Qt and asyncio, including QTimer callbacks
    loop = QEventLoop(app)
    asyncio.set_event_loop(loop)

    # Register types
    qmlRegisterType(Backend, "DuneWeaver", 1, 0, "Backend")
    qmlRegisterType(PatternModel, "DuneWeaver", 1, 0, "PatternModel")
    qmlRegisterType(PlaylistModel, "DuneWeaver", 1, 0, "PlaylistModel")

    # Load QML
    engine = QQmlApplicationEngine()

    # Set rotation flag for Pi 5 (display needs 180° rotation via QML)
    rotate_display = is_pi5()
    engine.rootContext().setContextProperty("rotateDisplay", rotate_display)
    if rotate_display:
        logger.info("🔄 Pi 5 detected - enabling QML rotation (180°)")

    qml_file = Path(__file__).parent / "qml" / "main.qml"
    engine.load(QUrl.fromLocalFile(str(qml_file)))

    if not engine.rootObjects():
        logger.error("❌ Failed to load QML - no root objects")
        return -1

    # Schedule startup tasks after event loop starts
    def schedule_startup():
        asyncio.create_task(startup_tasks())

    QTimer.singleShot(100, schedule_startup)

    # Setup signal handlers for clean shutdown
    def signal_handler(signum, frame):
        logger.info("🛑 Received shutdown signal, exiting...")
        loop.stop()
        app.quit()

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    logger.info("✅ Qt application started successfully")

    # Run the event loop
    # Using qasync 0.28.0 which should have CPU spin fixes
    try:
        with loop:
            loop.run_forever()
    except KeyboardInterrupt:
        logger.info("🛑 KeyboardInterrupt received, shutting down...")
    finally:
        loop.close()

    logger.info("🛑 Application shutdown complete")
    return 0

if __name__ == "__main__":
    sys.exit(main())
