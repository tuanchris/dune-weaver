import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15
import QtQuick.Dialogs
import QtQuick.VirtualKeyboard 2.15
import DuneWeaver 1.0
import "components"
import "components" as Components

ApplicationWindow {
    id: window
    visible: true
    width: 800
    height: 480
    title: "Dune Weaver Touch"

    // Solid background color for ApplicationWindow
    color: Components.ThemeManager.backgroundColor

    property int currentPageIndex: 0
    property alias stackView: stackView
    property alias backend: backend
    property bool shouldNavigateToExecution: false
    property string currentPatternName: ""
    property string currentPatternPreview: ""

    // Property to force full repaint on linuxfb (toggle to trigger update)
    property bool forceRepaint: false

    onCurrentPageIndexChanged: {
        console.log("📱 currentPageIndex changed to:", currentPageIndex)
    }

    // Force full repaint function - call when screen wakes up
    // On linuxfb, we need to force Qt to redraw the ENTIRE scene graph,
    // not just individual components. The trick is to briefly hide/show
    // the content which forces Qt to mark everything as dirty.
    function triggerFullRepaint() {
        console.log("🔄 Triggering full repaint for linuxfb")
        forceRepaint = !forceRepaint
        fullScreenBackground.requestPaint()

        // Force entire scene graph repaint by toggling visibility
        // This marks all items as dirty and forces a complete redraw
        rotationContainer.visible = false
        repaintRestoreTimer.start()
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

            // Then navigate to ExecutionPage tab (index 4)
            console.log("🎯 Setting currentPageIndex to 4")
            currentPageIndex = 4
            shouldNavigateToExecution = false
        }
    }
    
    Backend {
        id: backend
        
        onExecutionStarted: function(patternName, patternPreview) {
            console.log("🎯 QML: ExecutionStarted signal received! patternName='" + patternName + "', preview='" + patternPreview + "'")
            console.log("🎯 Setting shouldNavigateToExecution = true")
            // Store pattern info for ExecutionPage
            window.currentPatternName = patternName
            window.currentPatternPreview = patternPreview
            // Navigate to Execution tab (index 3) instead of pushing page
            shouldNavigateToExecution = true
            console.log("🎯 shouldNavigateToExecution set to:", shouldNavigateToExecution)
        }
        
        onErrorOccurred: function(error) {
            // Use custom dialog on Pi 5 for proper rotation
            if (typeof rotateDisplay !== 'undefined' && rotateDisplay) {
                customErrorDialog.errorText = error
                customErrorDialog.open()
            } else {
                errorDialog.text = error
                errorDialog.open()
            }
        }
        
        onScreenStateChanged: function(isOn) {
            console.log("🖥️ Screen state changed:", isOn ? "ON" : "OFF")
            if (isOn) {
                // Force full repaint when screen wakes up on linuxfb
                // This is necessary because linuxfb doesn't automatically
                // redraw the entire framebuffer after unblank
                repaintTimer.start()
            }
        }
        
        onBackendConnectionChanged: function(connected) {
            console.log("🔗 Backend connection changed:", connected)
            if (connected && stackView.currentItem.toString().indexOf("ConnectionSplash") !== -1) {
                console.log("✅ Backend connected, switching to main view")
                stackView.replace(mainSwipeView)
            } else if (!connected && stackView.currentItem.toString().indexOf("ConnectionSplash") === -1) {
                console.log("❌ Backend disconnected, switching to splash screen")
                stackView.replace(connectionSplash)
            }
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

    // Timer to delay repaint slightly after screen wake (ensures framebuffer is ready)
    Timer {
        id: repaintTimer
        interval: 150  // 150ms delay for framebuffer to be ready
        repeat: false
        onTriggered: {
            window.triggerFullRepaint()
        }
    }

    // Timer to restore visibility after hiding (completes the force-repaint trick)
    Timer {
        id: repaintRestoreTimer
        interval: 50  // Brief 50ms hide
        repeat: false
        onTriggered: {
            rotationContainer.visible = true
            console.log("🎨 Full scene repaint completed")
        }
    }

    // Full-screen opaque background using Canvas for forced repaint capability
    // This is essential for linuxfb which doesn't have proper compositing
    // and shows the Linux console through transparent areas
    Canvas {
        id: fullScreenBackground
        anchors.fill: parent
        z: -1  // Behind everything else

        // Repaint when forceRepaint toggles or theme changes
        property color bgColor: Components.ThemeManager.backgroundColor
        property bool repaintTrigger: window.forceRepaint

        onBgColorChanged: requestPaint()
        onRepaintTriggerChanged: requestPaint()

        onPaint: {
            var ctx = getContext("2d")
            ctx.fillStyle = bgColor
            ctx.fillRect(0, 0, width, height)
            console.log("🎨 Full screen background painted:", width, "x", height)
        }

        Component.onCompleted: {
            // Force initial paint
            requestPaint()
        }
    }

    // Rotation container for Pi 5 linuxfb
    Item {
        id: rotationContainer
        anchors.fill: parent
        rotation: typeof rotateDisplay !== 'undefined' && rotateDisplay ? 180 : 0
        transformOrigin: Item.Center

    StackView {
        id: stackView
        anchors.fill: parent
        initialItem: backend.backendConnected ? mainSwipeView : connectionSplash
        
        Component {
            id: connectionSplash
            
            ConnectionSplash {
                statusText: backend.reconnectStatus
                showRetryButton: backend.reconnectStatus === "Cannot connect to backend"
                
                onRetryConnection: {
                    console.log("🔄 Manual retry requested")
                    backend.retryConnection()
                }
            }
        }
        
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

                    // LED Control Page (index 3)
                    Loader {
                        source: "pages/LedControlPage.qml"
                        onLoaded: {
                            item.backend = backend
                        }
                    }

                    // Execution Page (index 4)
                    Loader {
                        source: "pages/ExecutionPage.qml"
                        onLoaded: {
                            item.backend = backend
                            item.stackView = stackView
                            item.patternName = Qt.binding(function() { return window.currentPatternName })
                            item.patternPreview = Qt.binding(function() { return window.currentPatternPreview })
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
    } // End rotationContainer

    // Virtual Keyboard Support - outside rotation container for proper positioning
    InputPanel {
        id: inputPanel
        z: 99999
        y: window.height
        anchors.left: parent.left
        anchors.right: parent.right

        // Rotate keyboard for Pi 5
        rotation: typeof rotateDisplay !== 'undefined' && rotateDisplay ? 180 : 0
        transformOrigin: Item.Center

        states: State {
            name: "visible"
            when: inputPanel.active
            PropertyChanges {
                target: inputPanel
                y: typeof rotateDisplay !== 'undefined' && rotateDisplay ? 0 : window.height - inputPanel.height
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

    // Error dialog - note: MessageDialog is a system dialog, rotation may not work
    // If rotation doesn't work, we'll need to replace with a custom Dialog
    MessageDialog {
        id: errorDialog
        title: "Error"
        buttons: MessageDialog.Ok
    }

    // Custom error dialog as fallback for Pi 5 rotation
    Popup {
        id: customErrorDialog
        modal: true
        x: (window.width - width) / 2
        y: (window.height - height) / 2
        width: 320
        height: 180
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside

        property string errorText: ""

        background: Rectangle {
            color: "#2d2d2d"
            radius: 12
            border.color: "#404040"
            border.width: 1

            // Rotate the entire dialog content for Pi 5
            rotation: typeof rotateDisplay !== 'undefined' && rotateDisplay ? 180 : 0
            transformOrigin: Item.Center
        }

        contentItem: Item {
            rotation: typeof rotateDisplay !== 'undefined' && rotateDisplay ? 180 : 0
            transformOrigin: Item.Center

            Column {
                anchors.fill: parent
                anchors.margins: 20
                spacing: 15

                Label {
                    text: "Error"
                    font.pixelSize: 18
                    font.bold: true
                    color: "#ff6b6b"
                    anchors.horizontalCenter: parent.horizontalCenter
                }

                Label {
                    text: customErrorDialog.errorText
                    wrapMode: Text.WordWrap
                    width: parent.width
                    horizontalAlignment: Text.AlignHCenter
                    color: "#ffffff"
                    font.pixelSize: 14
                }

                Button {
                    text: "OK"
                    anchors.horizontalCenter: parent.horizontalCenter
                    onClicked: customErrorDialog.close()
                }
            }
        }
    }
}