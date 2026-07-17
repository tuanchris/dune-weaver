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
        if (existingPatterns.indexOf(patternName) !== -1) {
            return true
        }
        if (sessionAddedPatterns.indexOf(patternName) !== -1) {
            return true
        }
        return false
    }

    // Add pattern and track it for instant visual feedback
    function addPatternToPlaylist(patternName) {
        if (!isPatternInPlaylist(patternName) && backend) {
            backend.addPatternToPlaylist(playlistName, patternName)
            var temp = sessionAddedPatterns.slice()
            temp.push(patternName)
            sessionAddedPatterns = temp
        }
    }

    Rectangle {
        anchors.fill: parent
        color: Components.ThemeManager.backgroundColor
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: 0

        // Header with back button + search
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
                anchors.rightMargin: Components.ThemeManager.spaceMd
                spacing: Components.ThemeManager.spaceSm

                // Back button
                Rectangle {
                    Layout.preferredWidth: 44
                    Layout.preferredHeight: 44
                    radius: 22
                    color: backArea.pressed ? Components.ThemeManager.pressedColor : "transparent"
                    visible: !searchExpanded

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
                    text: "Add to \"" + playlistName + "\""
                    font.family: Components.ThemeManager.fontDisplay
                    font.pixelSize: Components.ThemeManager.fontSizeTitle
                    color: Components.ThemeManager.textPrimary
                    Layout.fillWidth: true
                    elide: Text.ElideRight
                    visible: !searchExpanded
                }

                Label {
                    text: patternCount + " patterns"
                    font.family: Components.ThemeManager.fontBody
                    font.pixelSize: Components.ThemeManager.fontSizeCaption
                    color: Components.ThemeManager.textTertiary
                    visible: !searchExpanded
                }

                // Expandable search pill (matching ModernPatternListPage)
                Rectangle {
                    Layout.fillWidth: searchExpanded
                    Layout.preferredWidth: searchExpanded ? parent.width - 60 : 130
                    Layout.preferredHeight: 40
                    radius: 20
                    color: Components.ThemeManager.backgroundColor
                    border.color: searchExpanded || searchField.hasUnappliedSearch
                                  ? Components.ThemeManager.accent
                                  : Components.ThemeManager.borderColor
                    border.width: 1

                    Behavior on Layout.preferredWidth {
                        NumberAnimation { duration: 200 }
                    }

                    RowLayout {
                        anchors.fill: parent
                        anchors.leftMargin: Components.ThemeManager.spaceMd
                        anchors.rightMargin: Components.ThemeManager.spaceMd
                        spacing: Components.ThemeManager.spaceSm

                        Components.Icon {
                            name: "search"
                            size: 17
                            color: searchExpanded ? Components.ThemeManager.accent
                                                  : Components.ThemeManager.textSecondary
                        }

                        TextField {
                            id: searchField
                            Layout.fillWidth: true
                            placeholderText: searchExpanded ? "Search patterns, then press Enter" : "Search"
                            placeholderTextColor: Components.ThemeManager.textTertiary
                            font.family: Components.ThemeManager.fontBody
                            font.pixelSize: Components.ThemeManager.fontSizeBody
                            color: Components.ThemeManager.textPrimary
                            visible: searchExpanded || text.length > 0

                            property string lastSearchText: ""
                            property bool hasUnappliedSearch: text !== lastSearchText && text.length > 0

                            background: Rectangle {
                                color: "transparent"
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
                            text: "Search"
                            font.family: Components.ThemeManager.fontBody
                            font.pixelSize: Components.ThemeManager.fontSizeCaption
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
                Rectangle {
                    Layout.preferredWidth: 40
                    Layout.preferredHeight: 40
                    radius: 20
                    visible: searchExpanded
                    color: searchCloseArea.pressed ? Components.ThemeManager.pressedColor : "transparent"

                    Components.Icon {
                        anchors.centerIn: parent
                        name: "close"
                        size: 20
                        color: Components.ThemeManager.textSecondary
                    }

                    MouseArea {
                        id: searchCloseArea
                        anchors.fill: parent
                        onClicked: {
                            searchExpanded = false
                            searchField.text = ""
                            searchField.lastSearchText = ""
                            searchField.focus = false
                            patternModel.filter("")
                        }
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
            visible: patternCount > 0
            reuseItems: true
            cacheBuffer: 440

            ScrollBar.vertical: ScrollBar {
                active: true
                policy: ScrollBar.AsNeeded
            }

            delegate: Item {
                width: gridView.cellWidth
                height: gridView.cellHeight

                // Check if pattern is already in playlist
                property bool isInPlaylist: isPatternInPlaylist(model.name)

                ModernPatternCard {
                    id: patternCard
                    anchors.centerIn: parent
                    width: gridView.cellWidth - 10
                    height: gridView.cellHeight - 10
                    name: model.name
                    preview: model.preview

                    onClicked: {
                        page.addPatternToPlaylist(model.name)
                    }
                }

                // Selection ring + badge for patterns already in the playlist
                Rectangle {
                    anchors.fill: patternCard
                    color: "transparent"
                    border.color: isInPlaylist ? Components.ThemeManager.accent : "transparent"
                    border.width: isInPlaylist ? 2 : 0
                    radius: Components.ThemeManager.radiusMd

                    Rectangle {
                        visible: isInPlaylist
                        anchors.top: parent.top
                        anchors.right: parent.right
                        anchors.topMargin: Components.ThemeManager.spaceSm
                        anchors.rightMargin: Components.ThemeManager.spaceSm
                        width: 28
                        height: 28
                        radius: 14
                        color: Components.ThemeManager.accent

                        Components.Icon {
                            anchors.centerIn: parent
                            name: "check"
                            size: 16
                            color: Components.ThemeManager.onAccent
                        }
                    }
                }
            }

            add: Transition {
                NumberAnimation { property: "opacity"; from: 0; to: 1; duration: 300 }
                NumberAnimation { property: "scale"; from: 0.8; to: 1; duration: 300 }
            }
        }

        // Empty state when searching
        Item {
            Layout.fillWidth: true
            Layout.fillHeight: true
            visible: patternCount === 0

            Column {
                anchors.centerIn: parent
                spacing: Components.ThemeManager.spaceLg

                Components.Icon {
                    name: "search"
                    size: 44
                    anchors.horizontalCenter: parent.horizontalCenter
                    color: Components.ThemeManager.textTertiary
                }

                Label {
                    text: "No patterns found"
                    anchors.horizontalCenter: parent.horizontalCenter
                    color: Components.ThemeManager.textSecondary
                    font.family: Components.ThemeManager.fontDisplay
                    font.pixelSize: Components.ThemeManager.fontSizeTitle
                }

                Label {
                    text: "Try a different search term"
                    anchors.horizontalCenter: parent.horizontalCenter
                    color: Components.ThemeManager.textTertiary
                    font.family: Components.ThemeManager.fontBody
                    font.pixelSize: Components.ThemeManager.fontSizeBody
                }
            }
        }
    }
}
