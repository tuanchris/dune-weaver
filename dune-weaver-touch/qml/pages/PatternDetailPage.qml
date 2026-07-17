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

    // Selected clear mode ("adaptive" | "clear_center" | "clear_perimeter" | "none")
    property string clearMode: "adaptive"

    property string cleanName: {
        var parts = patternName.split('/')
        return parts[parts.length - 1].replace('.thr', '')
    }

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
            Layout.preferredHeight: Components.ThemeManager.headerHeight
            color: Components.ThemeManager.surfaceColor

            Rectangle {
                anchors.bottom: parent.bottom
                width: parent.width
                height: 1
                color: Components.ThemeManager.borderColor
            }

            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: Components.ThemeManager.spaceSm
                anchors.rightMargin: Components.ThemeManager.spaceLg
                spacing: Components.ThemeManager.spaceSm

                // Back button
                Rectangle {
                    Layout.preferredWidth: 44
                    Layout.preferredHeight: 44
                    radius: 22
                    color: backArea.pressed ? Components.ThemeManager.pressedColor : "transparent"

                    Components.Icon {
                        anchors.centerIn: parent
                        name: "arrow_back"
                        size: 20
                        color: Components.ThemeManager.textPrimary
                    }

                    MouseArea {
                        id: backArea
                        anchors.fill: parent
                        onClicked: stackView.pop()
                    }
                }

                Label {
                    text: cleanName
                    Layout.fillWidth: true
                    elide: Label.ElideRight
                    font.family: Components.ThemeManager.fontDisplay
                    font.pixelSize: Components.ThemeManager.fontSizeTitle
                    color: Components.ThemeManager.textPrimary
                }

                ConnectionStatus {
                    backend: page.backend
                }
            }
        }

        // Content
        RowLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: 0

            // ---- Left: circular preview ----
            Item {
                Layout.fillHeight: true
                Layout.preferredWidth: page.width * 0.55

                Image {
                    id: previewImage
                    anchors.centerIn: parent
                    width: Math.min(parent.width, parent.height) - 2 * Components.ThemeManager.spaceXl
                    height: width
                    source: patternPreview ? "file:///" + patternPreview : ""
                    fillMode: Image.PreserveAspectFit
                    asynchronous: true
                }

                // Empty dish placeholder
                Rectangle {
                    anchors.centerIn: parent
                    width: previewImage.width
                    height: width
                    radius: width / 2
                    color: Components.ThemeManager.surfaceColor
                    border.width: 1
                    border.color: Components.ThemeManager.borderColor
                    visible: previewImage.status === Image.Error || previewImage.source == ""

                    Column {
                        anchors.centerIn: parent
                        spacing: Components.ThemeManager.spaceSm

                        Components.Icon {
                            name: "radio_unchecked"
                            size: 34
                            color: Components.ThemeManager.textTertiary
                            anchors.horizontalCenter: parent.horizontalCenter
                        }

                        Label {
                            text: "No preview yet"
                            color: Components.ThemeManager.textSecondary
                            font.family: Components.ThemeManager.fontMedium
                            font.pixelSize: Components.ThemeManager.fontSizeBody
                            anchors.horizontalCenter: parent.horizontalCenter
                        }
                    }
                }
            }

            // ---- Right: actions ----
            Rectangle {
                Layout.fillHeight: true
                Layout.fillWidth: true
                color: Components.ThemeManager.surfaceColor

                Rectangle {
                    anchors.left: parent.left
                    width: 1
                    height: parent.height
                    color: Components.ThemeManager.borderColor
                }

                ColumnLayout {
                    anchors.fill: parent
                    anchors.margins: Components.ThemeManager.spaceXl
                    spacing: 0

                    Label {
                        text: "Before weaving"
                        font.family: Components.ThemeManager.fontDisplay
                        font.pixelSize: 11
                        font.letterSpacing: 1.4
                        font.capitalization: Font.AllUppercase
                        color: Components.ThemeManager.textTertiary
                    }

                    // Clear-mode chips
                    GridLayout {
                        Layout.fillWidth: true
                        Layout.topMargin: Components.ThemeManager.spaceSm
                        columns: 2
                        rowSpacing: Components.ThemeManager.spaceSm
                        columnSpacing: Components.ThemeManager.spaceSm

                        Repeater {
                            model: [
                                { label: "Adaptive clear", value: "adaptive" },
                                { label: "Clear from center", value: "clear_center" },
                                { label: "Clear from edge", value: "clear_perimeter" },
                                { label: "Keep the sand", value: "none" }
                            ]

                            ChoiceChip {
                                required property var modelData

                                Layout.fillWidth: true
                                Layout.preferredHeight: Components.ThemeManager.touchTarget
                                label: modelData.label
                                selected: page.clearMode === modelData.value

                                onClicked: page.clearMode = modelData.value
                            }
                        }
                    }

                    Item { Layout.fillHeight: true }

                    // Play — the one thing this page is for
                    ModernControlButton {
                        Layout.fillWidth: true
                        Layout.preferredHeight: Components.ThemeManager.controlHeight
                        icon: "play_arrow"
                        text: "Weave this pattern"
                        buttonColor: Components.ThemeManager.accent
                        enabled: backend !== null
                        onClicked: {
                            if (backend) backend.executePattern(patternName, page.clearMode)
                        }
                    }

                    ModernControlButton {
                        Layout.fillWidth: true
                        Layout.topMargin: Components.ThemeManager.spaceSm
                        Layout.preferredHeight: Components.ThemeManager.touchTarget
                        icon: showAddedFeedback ? "check" : "queue_music"
                        text: showAddedFeedback ? "Added" : "Add to playlist"
                        outlined: true
                        buttonColor: showAddedFeedback ? Components.ThemeManager.ok
                                                       : Components.ThemeManager.accent
                        enabled: backend !== null && !showAddedFeedback
                        onClicked: {
                            playlistModel.refresh()
                            playlistSelectorPopup.open()
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
        width: 340
        // ListView.count is reactive; rowCount() would only evaluate once
        // (at creation, before playlists have loaded).
        height: Math.min(400, 130 + playlistSelectorList.count * 62)
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside

        background: Rectangle {
            color: Components.ThemeManager.surfaceColor
            radius: Components.ThemeManager.radiusMd
            border.color: Components.ThemeManager.borderColor
            border.width: 1
        }

        contentItem: ColumnLayout {
            anchors.fill: parent
            anchors.margins: Components.ThemeManager.spaceLg
            spacing: Components.ThemeManager.spaceMd

            Label {
                text: "Add to playlist"
                font.family: Components.ThemeManager.fontDisplay
                font.pixelSize: Components.ThemeManager.fontSizeTitle
                color: Components.ThemeManager.textPrimary
                Layout.alignment: Qt.AlignHCenter
            }

            // Playlist list
            ListView {
                id: playlistSelectorList
                Layout.fillWidth: true
                Layout.fillHeight: true
                clip: true
                model: playlistModel
                spacing: Components.ThemeManager.spaceSm

                delegate: Rectangle {
                    width: ListView.view.width
                    height: 56
                    radius: Components.ThemeManager.radiusSm
                    color: playlistItemArea.pressed ? Components.ThemeManager.pressedColor
                                                    : Components.ThemeManager.cardColor
                    border.color: Components.ThemeManager.borderColor
                    border.width: 1

                    RowLayout {
                        anchors.fill: parent
                        anchors.margins: Components.ThemeManager.spaceMd
                        spacing: Components.ThemeManager.spaceMd

                        Components.Icon {
                            name: "queue_music"
                            size: 18
                            color: Components.ThemeManager.accent
                        }

                        Label {
                            text: model.name
                            font.family: Components.ThemeManager.fontMedium
                            font.pixelSize: Components.ThemeManager.fontSizeBody
                            color: Components.ThemeManager.textPrimary
                            Layout.fillWidth: true
                            elide: Text.ElideRight
                        }

                        Label {
                            text: model.itemCount + " patterns"
                            font.family: Components.ThemeManager.fontBody
                            font.pixelSize: Components.ThemeManager.fontSizeCaption
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
                spacing: Components.ThemeManager.spaceSm
                visible: playlistSelectorList.count === 0

                Item { height: Components.ThemeManager.spaceSm; width: 1 }

                Components.Icon {
                    name: "queue_music"
                    size: 30
                    color: Components.ThemeManager.textTertiary
                    anchors.horizontalCenter: parent.horizontalCenter
                }

                Label {
                    text: "No playlists yet"
                    anchors.horizontalCenter: parent.horizontalCenter
                    color: Components.ThemeManager.textSecondary
                    font.family: Components.ThemeManager.fontMedium
                    font.pixelSize: Components.ThemeManager.fontSizeBody
                }

                Label {
                    text: "Create one on the Playlists page first"
                    anchors.horizontalCenter: parent.horizontalCenter
                    color: Components.ThemeManager.textTertiary
                    font.family: Components.ThemeManager.fontBody
                    font.pixelSize: Components.ThemeManager.fontSizeCaption
                }
            }

            ModernControlButton {
                Layout.fillWidth: true
                Layout.preferredHeight: Components.ThemeManager.touchTarget
                text: "Cancel"
                outlined: true
                buttonColor: Components.ThemeManager.textSecondary
                onClicked: playlistSelectorPopup.close()
            }
        }
    }

    // ==================== Backend Signal Handlers ====================

    Connections {
        target: backend

        function onPatternAddedToPlaylist(success, message) {
            if (success) {
                showAddedFeedback = true
                feedbackTimer.start()
            }
        }
    }

    Timer {
        id: feedbackTimer
        interval: 2000  // Show "Added" for 2 seconds
        onTriggered: showAddedFeedback = false
    }
}
