import sys
import os
import asyncio
import logging
from pathlib import Path
from PySide6.QtCore import QUrl
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
    
    # Run startup tasks in background
    asyncio.create_task(startup_tasks())
    
    # Load QML
    engine = QQmlApplicationEngine()
    qml_file = Path(__file__).parent / "qml" / "main.qml"
    engine.load(QUrl.fromLocalFile(str(qml_file)))
    
    if not engine.rootObjects():
        return -1
    
    with loop:
        loop.run_forever()
    
    return 0

if __name__ == "__main__":
    sys.exit(main())