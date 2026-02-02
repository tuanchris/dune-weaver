import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15
import DuneWeaver 1.0
import "../components"
import "../components" as Components

Page {
    id: page

    property var backend: null
    property var stackView: null
    property string playlistName: ""
    property var existingPatterns: []  // Raw pattern names already in playlist

    // Track patterns added in this session for immediate visual feedback
    property var sessionAddedPatterns: []

    // Local pattern model for this page
    PatternModel {
        id: patternModel
    }

    // Search state
    property bool searchExpanded: false
    property int patternCount: patternModel ? patternModel.rowCount() : 0

    // Update pattern count when model resets
    Connections {
        target: patternModel
        function onModelReset() {
            patternCount = patternModel.rowCount()
        }
    }

    // Check if a pattern is already in the playlist
    function isPatternInPlaylist(patternName) {
        // Check original existing patterns
        if (existingPatterns.indexOf(patternName) !== -1) {
            return true
        }
        // Check patterns added during this session
        if (sessionAddedPatterns.indexOf(patternName) !== -1) {
            return true
        }
        return false
    }

    Rectangle {
        anchors.fill: parent
        color: Components.ThemeManager.backgroundColor
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: 0

        // Header with back button
        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 50
            color: Components.ThemeManager.surfaceColor

            // Bottom border
            Rectangle {
                anchors.bottom: parent.bottom
                width: parent.width
                height: 1
                color: Components.ThemeManager.borderColor
            }

            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: 15
                anchors.rightMargin: 10
                spacing: 10

                // Back button
                Button {
                    text: "← Back"
                    font.pixelSize: 14
                    flat: true
                    visible: !searchExpanded
                    onClicked: stackView.pop()

                    contentItem: Text {
                        text: parent.text
                        font: parent.font
                        color: Components.ThemeManager.textPrimary
                        horizontalAlignment: Text.AlignHCenter
                        verticalAlignment: Text.AlignVCenter
                    }
                }

                // Title
                Label {
                    text: "Add to \"" + playlistName + "\""
                    font.pixelSize: 16
                    font.bold: true
                    color: Components.ThemeManager.textPrimary
                    Layout.fillWidth: true
                    elide: Text.ElideRight
                    visible: !searchExpanded
                }

                // Pattern count
                Label {
                    text: patternCount + " patterns"
                    font.pixelSize: 12
                    color: Components.ThemeManager.textTertiary
                    visible: !searchExpanded
                }

                Item {
                    Layout.fillWidth: true
                    visible: !searchExpanded
                }

                // Expandable search (matching ModernPatternListPage)
                Rectangle {
                    Layout.fillWidth: searchExpanded
                    Layout.preferredWidth: searchExpanded ? parent.width - 60 : 120
                    Layout.preferredHeight: 32
                    radius: 16
                    color: searchExpanded ? Components.ThemeManager.surfaceColor : Components.ThemeManager.cardColor
                    border.color: searchExpanded ? "#2563eb" : Components.ThemeManager.borderColor
                    border.width: 1

                    Behavior on Layout.preferredWidth {
                        NumberAnimation { duration: 200 }
                    }

                    RowLayout {
                        anchors.fill: parent
                        anchors.leftMargin: 10
                        anchors.rightMargin: 10
                        spacing: 5

                        Text {
                            text: "⌕"
                            font.pixelSize: 16
                            font.family: "sans-serif"
                            color: searchExpanded ? "#2563eb" : Components.ThemeManager.textSecondary
                        }

                        TextField {
                            id: searchField
                            Layout.fillWidth: true
                            placeholderText: searchExpanded ? "Search patterns... (press Enter)" : "Search"
                            placeholderTextColor: Components.ThemeManager.textTertiary
                            font.pixelSize: 14
                            color: Components.ThemeManager.textPrimary
                            visible: searchExpanded || text.length > 0

                            property string lastSearchText: ""
                            property bool hasUnappliedSearch: text !== lastSearchText && text.length > 0

                            background: Rectangle {
                                color: "transparent"
                                border.color: searchField.hasUnappliedSearch ? "#f59e0b" : "transparent"
                                border.width: searchField.hasUnappliedSearch ? 1 : 0
                                radius: 4
                            }

                            onAccepted: {
                                patternModel.filter(text)
                                lastSearchText = text
                                Qt.inputMethod.hide()
                                focus = false
                            }

                            activeFocusOnPress: true
                            selectByMouse: true
                            inputMethodHints: Qt.ImhNoPredictiveText

                            MouseArea {
                                anchors.fill: parent
                                onPressed: {
                                    searchField.forceActiveFocus()
                                    Qt.inputMethod.show()
                                    mouse.accepted = false
                                }
                            }

                            onActiveFocusChanged: {
                                if (activeFocus) {
                                    searchExpanded = true
                                    Qt.inputMethod.show()
                                } else {
                                    if (text !== lastSearchText) {
                                        patternModel.filter(text)
                                        lastSearchText = text
                                    }
                                }
                            }

                            Keys.onReturnPressed: {
                                Qt.inputMethod.hide()
                                focus = false
                            }

                            Keys.onEscapePressed: {
                                text = ""
                                lastSearchText = ""
                                patternModel.filter("")
                                Qt.inputMethod.hide()
                                focus = false
                            }
                        }

                        Text {
                            text: searchExpanded || searchField.text.length > 0 ? "Search" : ""
                            font.pixelSize: 12
                            color: Components.ThemeManager.textTertiary
                            visible: !searchExpanded && searchField.text.length === 0
                        }
                    }

                    MouseArea {
                        anchors.fill: parent
                        enabled: !searchExpanded
                        onClicked: {
                            searchExpanded = true
                            searchField.forceActiveFocus()
                            Qt.inputMethod.show()
                        }
                    }
                }

                // Close button when search expanded
                Button {
                    id: searchCloseBtn
                    flat: true
                    visible: searchExpanded
                    Layout.preferredWidth: 32
                    Layout.preferredHeight: 32
                    onClicked: {
                        searchExpanded = false
                        searchField.text = ""
                        searchField.lastSearchText = ""
                        searchField.focus = false
                        patternModel.filter("")
                    }
                    contentItem: Text {
                        text: "✕"
                        font.pixelSize: 18
                        color: Components.ThemeManager.textSecondary
                        horizontalAlignment: Text.AlignHCenter
                        verticalAlignment: Text.AlignVCenter
                    }
                    background: Rectangle {
                        color: searchCloseBtn.pressed ? Components.ThemeManager.buttonBackgroundHover : "transparent"
                        radius: 4
                    }
                }
            }
        }

        // Pattern Grid
        GridView {
            id: gridView
            Layout.fillWidth: true
            Layout.fillHeight: true
            cellWidth: 200
            cellHeight: 220
            model: patternModel
            clip: true

            ScrollBar.vertical: ScrollBar {
                active: true
                policy: ScrollBar.AsNeeded
            }

            delegate: Item {
                width: gridView.cellWidth - 10
                height: gridView.cellHeight - 10

                // Check if pattern is already in playlist
                property bool isInPlaylist: isPatternInPlaylist(model.name)

                ModernPatternCard {
                    id: patternCard
                    anchors.fill: parent
                    name: model.name
                    preview: model.preview

                    onClicked: {
                        // Use the tracking function for immediate visual feedback
                        page.addPatternToPlaylist(model.name)
                    }
                }

                // Selection overlay for patterns already in playlist
                Rectangle {
                    anchors.fill: parent
                    color: "transparent"
                    border.color: isInPlaylist ? "#2563eb" : "transparent"
                    border.width: isInPlaylist ? 3 : 0
                    radius: 12

                    // Checkmark badge for selected patterns
                    Rectangle {
                        visible: isInPlaylist
                        anchors.top: parent.top
                        anchors.right: parent.right
                        anchors.topMargin: 12
                        anchors.rightMargin: 12
                        width: 28
                        height: 28
                        radius: 14
                        color: "#2563eb"

                        Text {
                            anchors.centerIn: parent
                            text: "✓"
                            font.pixelSize: 16
                            font.bold: true
                            color: "white"
                        }
                    }
                }
            }

            // Add scroll animations
            add: Transition {
                NumberAnimation { property: "opacity"; from: 0; to: 1; duration: 300 }
                NumberAnimation { property: "scale"; from: 0.8; to: 1; duration: 300 }
            }
        }

        // Empty state when searching
        Item {
            Layout.fillWidth: true
            Layout.fillHeight: true
            visible: patternCount === 0 && searchField.text !== ""

            Column {
                anchors.centerIn: parent
                spacing: 20

                Text {
                    text: "⌕"
                    font.pixelSize: 48
                    anchors.horizontalCenter: parent.horizontalCenter
                    color: Components.ThemeManager.placeholderText
                }

                Label {
                    text: "No patterns found"
                    anchors.horizontalCenter: parent.horizontalCenter
                    color: Components.ThemeManager.textSecondary
                    font.pixelSize: 18
                }

                Label {
                    text: "Try a different search term"
                    anchors.horizontalCenter: parent.horizontalCenter
                    color: Components.ThemeManager.textTertiary
                    font.pixelSize: 14
                }
            }
        }
    }

    // Handle pattern added signal for live updates
    Connections {
        target: backend

        function onPatternAddedToPlaylist(success, message) {
            if (success) {
                // Extract the pattern name from the message if possible
                // The message format is typically "Pattern added to playlist"
                // We'll track additions in sessionAddedPatterns instead

                // Re-trigger binding evaluation by updating the array reference
                var temp = sessionAddedPatterns.slice()
                // Try to extract pattern name from recent action
                // Since we don't get the pattern name directly, we need another approach
                sessionAddedPatterns = temp
            }
        }
    }

    // Track which pattern was last clicked for visual feedback
    property string lastClickedPattern: ""

    // Override the click handler to track additions
    Component.onCompleted: {
    }

    // Function to add pattern and track it
    function addPatternToPlaylist(patternName) {
        if (!isPatternInPlaylist(patternName) && backend) {
            backend.addPatternToPlaylist(playlistName, patternName)
            // Immediately add to session tracking for instant visual feedback
            var temp = sessionAddedPatterns.slice()
            temp.push(patternName)
            sessionAddedPatterns = temp
        }
    }
}
