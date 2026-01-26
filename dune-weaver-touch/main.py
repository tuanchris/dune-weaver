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
import qasync

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

async def async_main(app):
    """Main async function that runs the Qt application.

    Uses qasync's event loop integration - do NOT call app.processEvents()
    manually as qasync handles Qt/asyncio integration automatically.
    """
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

    # Schedule startup tasks
    asyncio.create_task(startup_tasks())

    logger.info("✅ Qt application started successfully")

    # Create an asyncio event that will be set when the app quits
    # This is the proper way to wait - qasync handles event loop integration
    quit_event = asyncio.Event()
    app.aboutToQuit.connect(quit_event.set)

    # Wait for the app to quit
    # This properly yields to the event loop, allowing:
    # - Qt events to be processed (handled by qasync)
    # - Other async tasks (like aiohttp in Backend) to run
    # - No CPU spinning since we're awaiting an event, not polling
    await quit_event.wait()

    logger.info("🛑 Application shutdown complete")
    return 0

def main():
    # Enable virtual keyboard
    os.environ['QT_IM_MODULE'] = 'qtvirtualkeyboard'

    app = QGuiApplication(sys.argv)

    # Install first-touch filter to ignore wake-up touches
    first_touch_filter = FirstTouchFilter(idle_threshold_seconds=2.0)
    app.installEventFilter(first_touch_filter)
    logger.info("✅ First-touch filter installed on application")

    # Setup signal handlers for clean shutdown
    def signal_handler(signum, frame):
        logger.info("🛑 Received shutdown signal, exiting...")
        app.quit()

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Use qasync.run() to properly integrate Qt and asyncio event loops
    # qasync handles all event loop integration - we just await the quit signal
    try:
        qasync.run(async_main(app))
    except KeyboardInterrupt:
        logger.info("🛑 KeyboardInterrupt received")

    return 0

if __name__ == "__main__":
    sys.exit(main())
