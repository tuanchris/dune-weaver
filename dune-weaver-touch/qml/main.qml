import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15
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

    onCurrentPageIndexChanged: {
    }

    onShouldNavigateToExecutionChanged: {
        if (shouldNavigateToExecution) {

            // If we're in a sub-page (like PatternDetailPage), pop back to main view first
            if (stackView.depth > 1) {
                stackView.pop()
            }

            // Then navigate to ExecutionPage tab (index 4)
            currentPageIndex = 4
            shouldNavigateToExecution = false
        }
    }
    
    Backend {
        id: backend
        
        onExecutionStarted: function(patternName, patternPreview) {
            // Store pattern info for ExecutionPage
            window.currentPatternName = patternName
            window.currentPatternPreview = patternPreview
            // Navigate to Execution tab (index 3) instead of pushing page
            shouldNavigateToExecution = true
        }

        // Preview rendered after the pattern started (it wasn't cached yet)
        onPatternPreviewReady: function(patternName, preview) {
            if (patternName === window.currentPatternName) {
                window.currentPatternPreview = preview
            }
        }
        
        onErrorOccurred: function(error) {
            // Always the in-scene themed dialog: the native MessageDialog
            // renders as an unreadable empty box on some platforms and can't
            // follow the Pi 5's 180° rotation.
            customErrorDialog.errorText = error
            customErrorDialog.open()
        }
        
        onScreenStateChanged: function(isOn) {
        }
    }
    
    // Global touch/mouse handler for activity tracking
    MouseArea {
        anchors.fill: parent
        acceptedButtons: Qt.NoButton  // Don't interfere with other mouse areas
        hoverEnabled: true
        propagateComposedEvents: true
        
        onPressed: {
            backend.resetActivityTimer()
        }
        
        onPositionChanged: {
            backend.resetActivityTimer()
        }
        
        onClicked: {
            backend.resetActivityTimer()
        }
    }
    
    PatternModel {
        id: patternModel
    }

    // Rotation container for Pi 5
    Item {
        id: rotationContainer
        anchors.fill: parent
        rotation: typeof rotateDisplay !== 'undefined' && rotateDisplay ? 180 : 0
        transformOrigin: Item.Center

    StackView {
        id: stackView
        anchors.fill: parent
        // The UI is always usable regardless of table reachability; the
        // per-page ConnectionStatus dot (green/red) reflects the link state
        // and Table Control handles picking/reconnecting a table.
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

    // Error dialog (in-scene so it themes and rotates with the UI)
    Popup {
        id: customErrorDialog
        modal: true
        x: (window.width - width) / 2
        y: (window.height - height) / 2
        width: 380
        height: Math.max(190, errorColumn.implicitHeight + 50)
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside

        property string errorText: ""

        background: Rectangle {
            color: Components.ThemeManager.surfaceColor
            radius: Components.ThemeManager.radiusMd
            border.color: Components.ThemeManager.borderColor
            border.width: 1

            // Rotate the entire dialog content for Pi 5
            rotation: typeof rotateDisplay !== 'undefined' && rotateDisplay ? 180 : 0
            transformOrigin: Item.Center
        }

        contentItem: Item {
            rotation: typeof rotateDisplay !== 'undefined' && rotateDisplay ? 180 : 0
            transformOrigin: Item.Center

            Column {
                id: errorColumn
                anchors.fill: parent
                anchors.margins: 20
                spacing: 15

                Label {
                    text: "Something went wrong"
                    font.family: Components.ThemeManager.fontDisplay
                    font.pixelSize: Components.ThemeManager.fontSizeTitle
                    color: Components.ThemeManager.danger
                    anchors.horizontalCenter: parent.horizontalCenter
                }

                Label {
                    text: customErrorDialog.errorText
                    wrapMode: Text.WordWrap
                    width: parent.width
                    horizontalAlignment: Text.AlignHCenter
                    color: Components.ThemeManager.textPrimary
                    font.family: Components.ThemeManager.fontBody
                    font.pixelSize: Components.ThemeManager.fontSizeBody
                }

                Components.ModernControlButton {
                    text: "OK"
                    width: 120
                    height: Components.ThemeManager.touchTarget
                    anchors.horizontalCenter: parent.horizontalCenter
                    onClicked: customErrorDialog.close()
                }
            }
        }
    }
}