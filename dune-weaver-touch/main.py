import sys
import os
import asyncio
import logging
from pathlib import Path
from PySide6.QtCore import QUrl, QTimer
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
    # Enable virtual keyboard
    os.environ['QT_IM_MODULE'] = 'qtvirtualkeyboard'
    
    app = QGuiApplication(sys.argv)
    
    # Setup async event loop
    loop = QEventLoop(app)
    asyncio.set_event_loop(loop)
    
    # Register types
    qmlRegisterType(Backend, "DuneWeaver", 1, 0, "Backend")
    qmlRegisterType(PatternModel, "DuneWeaver", 1, 0, "PatternModel")
    qmlRegisterType(PlaylistModel, "DuneWeaver", 1, 0, "PlaylistModel")
    
    # Load QML
    engine = QQmlApplicationEngine()
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