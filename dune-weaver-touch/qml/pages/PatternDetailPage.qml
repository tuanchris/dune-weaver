import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15
import DuneWeaver 1.0
import "../components"
import "../components" as Components

Page {
    id: page
    property string patternName: ""
    property string patternPath: ""
    property string patternPreview: ""
    property var backend: null
    property bool showAddedFeedback: false

    // Playlist model for selecting which playlist to add to
    PlaylistModel {
        id: playlistModel
    }

    Rectangle {
        anchors.fill: parent
        color: Components.ThemeManager.backgroundColor
    }
    
    ColumnLayout {
        anchors.fill: parent
        spacing: 0
        
        // Header
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
                anchors.margins: 10
                
                ConnectionStatus {
                    backend: page.backend
                    Layout.rightMargin: 8
                }
                
                Button {
                    text: "← Back"
                    font.pixelSize: 14
                    flat: true
                    onClicked: stackView.pop()

                    contentItem: Text {
                        text: parent.text
                        font: parent.font
                        color: Components.ThemeManager.textPrimary
                        horizontalAlignment: Text.AlignHCenter
                        verticalAlignment: Text.AlignVCenter
                    }
                }
                
                Label {
                    text: patternName
                    Layout.fillWidth: true
                    elide: Label.ElideRight
                    font.pixelSize: 16
                    font.bold: true
                    color: Components.ThemeManager.textPrimary
                }
            }
        }
        
        // Content - Side by side layout
        Item {
            Layout.fillWidth: true
            Layout.fillHeight: true
            
            Row {
                anchors.fill: parent
                spacing: 0
                
                // Left side - Pattern Preview (60% of width)
                Rectangle {
                    width: parent.width * 0.6
                    height: parent.height
                    color: Components.ThemeManager.previewBackground

                Image {
                    anchors.fill: parent
                    anchors.margins: 10
                    source: patternPreview ? "file:///" + patternPreview : ""
                    fillMode: Image.PreserveAspectFit

                    Rectangle {
                        anchors.fill: parent
                        color: Components.ThemeManager.placeholderBackground
                        visible: parent.status === Image.Error || parent.source == ""

                        Column {
                            anchors.centerIn: parent
                            spacing: 10

                            Text {
                                text: "○"
                                font.pixelSize: 48
                                color: Components.ThemeManager.placeholderText
                                anchors.horizontalCenter: parent.horizontalCenter
                            }

                            Text {
                                text: "No Preview Available"
                                color: Components.ThemeManager.textSecondary
                                font.pixelSize: 14
                                anchors.horizontalCenter: parent.horizontalCenter
                            }
                        }
                    }
                }
            }
                
                // Divider
                Rectangle {
                    width: 1
                    height: parent.height
                    color: Components.ThemeManager.borderColor
                }

                // Right side - Controls (40% of width)
                Rectangle {
                    width: parent.width * 0.4 - 1
                    height: parent.height
                    color: Components.ThemeManager.surfaceColor
                
                Column {
                    anchors.fill: parent
                    anchors.margins: 10
                    spacing: 15
                    
                    // Play Button - FIRST AND PROMINENT
                    Rectangle {
                        width: parent.width
                        height: 50
                        radius: 8
                        color: playMouseArea.pressed ? "#1e40af" : (backend ? "#2563eb" : "#9ca3af")

                        Text {
                            anchors.centerIn: parent
                            text: "▶ Play Pattern"
                            color: "white"
                            font.pixelSize: 16
                            font.bold: true
                        }

                        MouseArea {
                            id: playMouseArea
                            anchors.fill: parent
                            enabled: backend !== null
                            onClicked: {
                                if (backend) {
                                    var preExecution = "adaptive"
                                    if (centerRadio.checked) preExecution = "clear_center"
                                    else if (perimeterRadio.checked) preExecution = "clear_perimeter"
                                    else if (noneRadio.checked) preExecution = "none"

                                    backend.executePattern(patternName, preExecution)
                                }
                            }
                        }
                    }

                    // Add to Playlist Button
                    Rectangle {
                        width: parent.width
                        height: 45
                        radius: 8
                        color: addToPlaylistArea.pressed ? "#065f46" : "#059669"

                        Row {
                            anchors.centerIn: parent
                            spacing: 8

                            Text {
                                text: showAddedFeedback ? "✓" : "♪"
                                font.pixelSize: 16
                                color: "white"
                            }

                            Text {
                                text: showAddedFeedback ? "Added!" : "Add to Playlist"
                                color: "white"
                                font.pixelSize: 14
                                font.bold: true
                            }
                        }

                        MouseArea {
                            id: addToPlaylistArea
                            anchors.fill: parent
                            enabled: backend !== null && !showAddedFeedback
                            onClicked: {
                                playlistModel.refresh()  // Refresh playlist list
                                playlistSelectorPopup.open()
                            }
                        }
                    }

                    // Pre-Execution Options
                    Rectangle {
                        width: parent.width
                        height: 160  // Increased height to fit all options
                        radius: 8
                        color: Components.ThemeManager.cardColor
                        border.color: Components.ThemeManager.borderColor
                        border.width: 1

                        Column {
                            id: preExecColumn
                            anchors.left: parent.left
                            anchors.right: parent.right
                            anchors.top: parent.top
                            anchors.margins: 8  // Reduced margins to save space
                            spacing: 6  // Reduced spacing

                            Label {
                                text: "Pre-Execution"
                                font.pixelSize: 12
                                font.bold: true
                                color: Components.ThemeManager.textPrimary
                            }
                            
                            RadioButton {
                                id: adaptiveRadio
                                text: "Adaptive"
                                checked: true
                                font.pixelSize: 10

                                contentItem: Text {
                                    text: parent.text
                                    font: parent.font
                                    color: Components.ThemeManager.textPrimary
                                    verticalAlignment: Text.AlignVCenter
                                    leftPadding: parent.indicator.width + parent.spacing
                                }
                            }

                            RadioButton {
                                id: centerRadio
                                text: "Clear Center"
                                font.pixelSize: 10

                                contentItem: Text {
                                    text: parent.text
                                    font: parent.font
                                    color: Components.ThemeManager.textPrimary
                                    verticalAlignment: Text.AlignVCenter
                                    leftPadding: parent.indicator.width + parent.spacing
                                }
                            }

                            RadioButton {
                                id: perimeterRadio
                                text: "Clear Edge"
                                font.pixelSize: 10

                                contentItem: Text {
                                    text: parent.text
                                    font: parent.font
                                    color: Components.ThemeManager.textPrimary
                                    verticalAlignment: Text.AlignVCenter
                                    leftPadding: parent.indicator.width + parent.spacing
                                }
                            }

                            RadioButton {
                                id: noneRadio
                                text: "None"
                                font.pixelSize: 10

                                contentItem: Text {
                                    text: parent.text
                                    font: parent.font
                                    color: Components.ThemeManager.textPrimary
                                    verticalAlignment: Text.AlignVCenter
                                    leftPadding: parent.indicator.width + parent.spacing
                                }
                            }
                        }
                    }
                    
                    // Pattern Info
                    Rectangle {
                        width: parent.width
                        height: 80
                        radius: 8
                        color: Components.ThemeManager.cardColor
                        border.color: Components.ThemeManager.borderColor
                        border.width: 1

                        Column {
                            id: infoColumn
                            anchors.left: parent.left
                            anchors.right: parent.right
                            anchors.top: parent.top
                            anchors.margins: 10
                            spacing: 6

                            Label {
                                text: "Pattern Info"
                                font.pixelSize: 14
                                font.bold: true
                                color: Components.ThemeManager.textPrimary
                            }

                            Label {
                                text: "Name: " + patternName
                                font.pixelSize: 11
                                color: Components.ThemeManager.textSecondary
                                elide: Text.ElideRight
                                width: parent.width
                            }

                            Label {
                                text: "Type: Sand Pattern"
                                font.pixelSize: 11
                                color: Components.ThemeManager.textSecondary
                            }
                        }
                    }
                }
            }
            }
        }
    }

    // ==================== Playlist Selector Popup ====================

    Popup {
        id: playlistSelectorPopup
        modal: true
        x: (parent.width - width) / 2
        y: (parent.height - height) / 2
        width: 320
        height: Math.min(400, 120 + playlistModel.rowCount() * 50)
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside

        background: Rectangle {
            color: Components.ThemeManager.surfaceColor
            radius: 16
            border.color: Components.ThemeManager.borderColor
            border.width: 1
        }

        contentItem: ColumnLayout {
            anchors.fill: parent
            anchors.margins: 15
            spacing: 10

            Label {
                text: "Add to Playlist"
                font.pixelSize: 18
                font.bold: true
                color: Components.ThemeManager.textPrimary
                Layout.alignment: Qt.AlignHCenter
            }

            // Playlist list
            ListView {
                Layout.fillWidth: true
                Layout.fillHeight: true
                clip: true
                model: playlistModel
                spacing: 6

                delegate: Rectangle {
                    width: ListView.view.width
                    height: 45
                    radius: 8
                    color: playlistItemArea.pressed ? Components.ThemeManager.selectedBackground : Components.ThemeManager.cardColor
                    border.color: Components.ThemeManager.borderColor
                    border.width: 1

                    RowLayout {
                        anchors.fill: parent
                        anchors.margins: 12
                        spacing: 10

                        Text {
                            text: "♪"
                            font.pixelSize: 16
                            color: "#2196F3"
                        }

                        Label {
                            text: model.name
                            font.pixelSize: 14
                            color: Components.ThemeManager.textPrimary
                            Layout.fillWidth: true
                            elide: Text.ElideRight
                        }

                        Label {
                            text: model.itemCount + " patterns"
                            font.pixelSize: 11
                            color: Components.ThemeManager.textTertiary
                        }
                    }

                    MouseArea {
                        id: playlistItemArea
                        anchors.fill: parent
                        onClicked: {
                            if (backend) {
                                backend.addPatternToPlaylist(model.name, patternName)
                            }
                            playlistSelectorPopup.close()
                        }
                    }
                }
            }

            // Empty state
            Column {
                Layout.fillWidth: true
                Layout.fillHeight: true
                spacing: 10
                visible: playlistModel.rowCount() === 0

                Item { Layout.fillHeight: true }

                Text {
                    text: "♪"
                    font.pixelSize: 32
                    color: Components.ThemeManager.placeholderText
                    anchors.horizontalCenter: parent.horizontalCenter
                }

                Label {
                    text: "No playlists yet"
                    anchors.horizontalCenter: parent.horizontalCenter
                    color: Components.ThemeManager.textSecondary
                    font.pixelSize: 14
                }

                Label {
                    text: "Create a playlist first"
                    anchors.horizontalCenter: parent.horizontalCenter
                    color: Components.ThemeManager.textTertiary
                    font.pixelSize: 12
                }

                Item { Layout.fillHeight: true }
            }

            // Cancel button
            Rectangle {
                Layout.fillWidth: true
                Layout.preferredHeight: 40
                radius: 8
                color: cancelArea.pressed ? Components.ThemeManager.buttonBackgroundHover : Components.ThemeManager.cardColor
                border.color: Components.ThemeManager.borderColor
                border.width: 1

                Text {
                    anchors.centerIn: parent
                    text: "Cancel"
                    color: Components.ThemeManager.textPrimary
                    font.pixelSize: 14
                }

                MouseArea {
                    id: cancelArea
                    anchors.fill: parent
                    onClicked: playlistSelectorPopup.close()
                }
            }
        }
    }

    // ==================== Backend Signal Handlers ====================

    Connections {
        target: backend

        function onPatternAddedToPlaylist(success, message) {
            if (success) {
                // Show feedback
                showAddedFeedback = true
                feedbackTimer.start()
            }
        }
    }

    Timer {
        id: feedbackTimer
        interval: 2000  // Show "Added!" for 2 seconds
        onTriggered: showAddedFeedback = false
    }
}