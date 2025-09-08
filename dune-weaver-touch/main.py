import sys
import os
import asyncio
from pathlib import Path
from PySide6.QtCore import QUrl
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine, qmlRegisterType
from qasync import QEventLoop

from backend import Backend
from models.pattern_model import PatternModel
from models.playlist_model import PlaylistModel

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
    
    with loop:
        loop.run_forever()
    
    return 0

if __name__ == "__main__":
    sys.exit(main())