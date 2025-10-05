import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15
import QtQuick.Dialogs
import QtQuick.VirtualKeyboard 2.15
import DuneWeaver 1.0
import "components"

ApplicationWindow {
    id: window
    visible: true
    width: 800
    height: 480
    title: "Dune Weaver Touch"

    // Auto-detect kiosk mode from environment or platform
    // EGLFS platform automatically goes fullscreen, but we can also set visibility
    Component.onCompleted: {
        // Check if we're running in kiosk mode (eglfs platform)
        var isKiosk = Qt.platform.pluginName === "eglfs" || Qt.platform.pluginName === "linuxfb"
        if (isKiosk) {
            console.log("🖥️  Kiosk mode detected - platform:", Qt.platform.pluginName)
            visibility = Window.FullScreen
        } else {
            console.log("🪟 Desktop mode - platform:", Qt.platform.pluginName)
        }
    }
    
    property int currentPageIndex: 0
    property alias stackView: stackView
    property alias backend: backend
    property bool shouldNavigateToExecution: false
    
    onCurrentPageIndexChanged: {
        console.log("📱 currentPageIndex changed to:", currentPageIndex)
    }
    
    onShouldNavigateToExecutionChanged: {
        if (shouldNavigateToExecution) {
            console.log("🎯 Navigating to execution page")
            console.log("🎯 Current stack depth:", stackView.depth)
            
            // If we're in a sub-page (like PatternDetailPage), pop back to main view first
            if (stackView.depth > 1) {
                console.log("🎯 Popping back to main view first")
                stackView.pop()
            }
            
            // Then navigate to ExecutionPage tab
            console.log("🎯 Setting currentPageIndex to 3")
            currentPageIndex = 3
            shouldNavigateToExecution = false
        }
    }
    
    Backend {
        id: backend
        
        onExecutionStarted: function(patternName, patternPreview) {
            console.log("🎯 QML: ExecutionStarted signal received! patternName='" + patternName + "', preview='" + patternPreview + "'")
            console.log("🎯 Setting shouldNavigateToExecution = true")
            // Navigate to Execution tab (index 3) instead of pushing page
            shouldNavigateToExecution = true
            console.log("🎯 shouldNavigateToExecution set to:", shouldNavigateToExecution)
        }
        
        onErrorOccurred: function(error) {
            errorDialog.text = error
            errorDialog.open()
        }
        
        onScreenStateChanged: function(isOn) {
            console.log("🖥️ Screen state changed:", isOn ? "ON" : "OFF")
        }
    }
    
    // Global touch/mouse handler for activity tracking
    MouseArea {
        anchors.fill: parent
        acceptedButtons: Qt.NoButton  // Don't interfere with other mouse areas
        hoverEnabled: true
        propagateComposedEvents: true
        
        onPressed: {
            console.log("🖥️ QML: Touch/press detected - resetting activity timer")
            backend.resetActivityTimer()
        }
        
        onPositionChanged: {
            console.log("🖥️ QML: Mouse movement detected - resetting activity timer")
            backend.resetActivityTimer()
        }
        
        onClicked: {
            console.log("🖥️ QML: Click detected - resetting activity timer")
            backend.resetActivityTimer()
        }
    }
    
    PatternModel {
        id: patternModel
    }
    
    StackView {
        id: stackView
        anchors.fill: parent
        initialItem: mainSwipeView
        
        Component {
            id: mainSwipeView
            
            Item {
                // Main content area
                StackLayout {
                    id: stackLayout
                    anchors.top: parent.top
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.bottom: bottomNav.top
                    currentIndex: window.currentPageIndex
                    
                    Component.onCompleted: {
                        console.log("📱 StackLayout created with currentIndex:", currentIndex, "bound to window.currentPageIndex:", window.currentPageIndex)
                    }
                    
                    // Patterns Page
                    Loader {
                        source: "pages/ModernPatternListPage.qml"
                        onLoaded: {
                            item.patternModel = patternModel
                            item.backend = backend
                            item.stackView = stackView
                        }
                    }
                    
                    // Playlists Page  
                    Loader {
                        source: "pages/ModernPlaylistPage.qml"
                        onLoaded: {
                            item.backend = backend
                            item.stackView = stackView
                            item.mainWindow = window
                        }
                    }
                    
                    // Control Page
                    Loader {
                        source: "pages/TableControlPage.qml"
                        onLoaded: {
                            item.backend = backend
                        }
                    }
                    
                    // Execution Page
                    Loader {
                        source: "pages/ExecutionPage.qml"
                        onLoaded: {
                            item.backend = backend
                            item.stackView = stackView
                        }
                    }
                }
                
                // Bottom Navigation
                BottomNavigation {
                    id: bottomNav
                    anchors.bottom: parent.bottom
                    anchors.left: parent.left
                    anchors.right: parent.right
                    currentIndex: window.currentPageIndex
                    
                    onTabClicked: function(index) {
                        console.log("📱 Tab clicked:", index)
                        window.currentPageIndex = index
                    }
                }
            }
        }
    }
    
    MessageDialog {
        id: errorDialog
        title: "Error"
        buttons: MessageDialog.Ok
    }
    
    // Virtual Keyboard Support
    InputPanel {
        id: inputPanel
        z: 99999
        y: window.height
        anchors.left: parent.left
        anchors.right: parent.right
        
        states: State {
            name: "visible"
            when: inputPanel.active
            PropertyChanges {
                target: inputPanel
                y: window.height - inputPanel.height
            }
        }
        
        transitions: Transition {
            from: ""
            to: "visible"
            reversible: true
            ParallelAnimation {
                NumberAnimation {
                    target: inputPanel
                    property: "y"
                    duration: 250
                    easing.type: Easing.InOutQuad
                }
            }
        }
    }
}