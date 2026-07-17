import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15
import "../components"
import "../components" as Components

Page {
    id: page

    property var patternModel
    property var backend
    property var stackView
    property bool searchExpanded: false
    property bool isRefreshing: false
    property int patternCount: patternModel ? patternModel.rowCount() : 0

    // Handle pattern refresh completion from backend
    Connections {
        target: backend
        function onPatternsRefreshCompleted(success, message) {
            if (patternModel) {
                patternModel.refresh()
            }
            isRefreshing = false
        }
    }

    // Update pattern count when model resets (rowCount() is not reactive)
    Connections {
        target: patternModel
        function onModelReset() {
            patternCount = patternModel.rowCount()
        }
    }

    Rectangle {
        anchors.fill: parent
        color: Components.ThemeManager.backgroundColor
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: 0

        // Header with integrated search
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
                anchors.leftMargin: Components.ThemeManager.spaceLg
                anchors.rightMargin: Components.ThemeManager.spaceMd
                spacing: Components.ThemeManager.spaceSm

                ConnectionStatus {
                    backend: page.backend
                    visible: !searchExpanded
                }

                Label {
                    text: "Browse"
                    font.family: Components.ThemeManager.fontDisplay
                    font.pixelSize: Components.ThemeManager.fontSizeTitle
                    color: Components.ThemeManager.textPrimary
                    visible: !searchExpanded
                }

                Label {
                    text: patternCount + " patterns"
                    font.family: Components.ThemeManager.fontBody
                    font.pixelSize: Components.ThemeManager.fontSizeCaption
                    color: Components.ThemeManager.textTertiary
                    visible: !searchExpanded
                }

                // Refresh button
                Rectangle {
                    Layout.preferredWidth: 40
                    Layout.preferredHeight: 40
                    radius: 20
                    color: refreshMouseArea.pressed ? Components.ThemeManager.pressedColor : "transparent"
                    visible: !searchExpanded

                    Components.Icon {
                        id: refreshIcon
                        anchors.centerIn: parent
                        name: "refresh"
                        size: 20
                        color: isRefreshing ? Components.ThemeManager.accent
                                            : Components.ThemeManager.textSecondary

                        SequentialAnimation on opacity {
                            running: isRefreshing
                            loops: Animation.Infinite
                            NumberAnimation { to: 0.4; duration: 500 }
                            NumberAnimation { to: 1.0; duration: 500 }
                        }
                    }

                    MouseArea {
                        id: refreshMouseArea
                        anchors.fill: parent
                        enabled: !isRefreshing
                        onClicked: {
                            if (backend) {
                                isRefreshing = true
                                backend.refreshPatterns()
                            }
                        }
                    }
                }

                Item {
                    Layout.fillWidth: true
                    visible: !searchExpanded
                }

                // Expandable search pill
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

                            // Only filter when user presses Enter or field loses focus
                            onAccepted: {
                                patternModel.filter(text)
                                lastSearchText = text
                                Qt.inputMethod.hide()
                                focus = false
                            }

                            // Enable virtual keyboard
                            activeFocusOnPress: true
                            selectByMouse: true
                            inputMethodHints: Qt.ImhNoPredictiveText

                            // Direct MouseArea for touch events
                            MouseArea {
                                anchors.fill: parent
                                onPressed: {
                                    searchField.forceActiveFocus()
                                    Qt.inputMethod.show()
                                    mouse.accepted = false // Pass through to TextField
                                }
                            }

                            onActiveFocusChanged: {
                                if (activeFocus) {
                                    searchExpanded = true
                                    // Force virtual keyboard to show
                                    Qt.inputMethod.show()
                                } else {
                                    // Apply search when focus is lost
                                    if (text !== lastSearchText) {
                                        patternModel.filter(text)
                                        lastSearchText = text
                                    }
                                }
                            }

                            Keys.onReturnPressed: {
                                // onAccepted runs; just hide keyboard and unfocus
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

                // Close button when expanded
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

        // Content - Pattern Grid
        GridView {
            id: gridView
            Layout.fillWidth: true
            Layout.fillHeight: true
            cellWidth: 200
            cellHeight: 220
            model: patternModel
            clip: true
            visible: patternCount > 0
            // Recycle delegates and pre-build the next rows: creating a card
            // mid-flick is the other half of the scroll stutter.
            reuseItems: true
            cacheBuffer: 440

            ScrollBar.vertical: ScrollBar {
                active: true
                policy: ScrollBar.AsNeeded
            }

            delegate: Item {
                width: gridView.cellWidth
                height: gridView.cellHeight

                ModernPatternCard {
                    anchors.centerIn: parent
                    width: gridView.cellWidth - 10
                    height: gridView.cellHeight - 10
                    name: model.name
                    preview: model.preview

                    onClicked: {
                        if (stackView && backend) {
                            stackView.push("PatternDetailPage.qml", {
                                patternName: model.name,
                                patternPath: model.path,
                                patternPreview: model.preview,
                                backend: backend
                            })
                        }
                    }
                }
            }

            add: Transition {
                NumberAnimation { property: "opacity"; from: 0; to: 1; duration: 300 }
                NumberAnimation { property: "scale"; from: 0.8; to: 1; duration: 300 }
            }
        }

        // Empty state — no search results, or no patterns at all
        Item {
            Layout.fillWidth: true
            Layout.fillHeight: true
            visible: patternCount === 0

            property bool searching: searchField.text !== ""

            Column {
                anchors.centerIn: parent
                spacing: Components.ThemeManager.spaceLg

                Components.Icon {
                    name: parent.parent.searching ? "search" : "radio_unchecked"
                    size: 44
                    anchors.horizontalCenter: parent.horizontalCenter
                    color: Components.ThemeManager.textTertiary
                }

                Label {
                    text: parent.parent.searching ? "No patterns found" : "No patterns yet"
                    anchors.horizontalCenter: parent.horizontalCenter
                    color: Components.ThemeManager.textSecondary
                    font.family: Components.ThemeManager.fontDisplay
                    font.pixelSize: Components.ThemeManager.fontSizeTitle
                }

                Label {
                    text: parent.parent.searching
                          ? "Try a different search term"
                          : "Connect to a table on the Control page to load its patterns"
                    anchors.horizontalCenter: parent.horizontalCenter
                    color: Components.ThemeManager.textTertiary
                    font.family: Components.ThemeManager.fontBody
                    font.pixelSize: Components.ThemeManager.fontSizeBody
                    horizontalAlignment: Text.AlignHCenter
                }
            }
        }
    }
}
