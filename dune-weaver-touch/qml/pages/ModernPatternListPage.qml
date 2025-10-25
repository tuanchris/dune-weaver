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

                ConnectionStatus {
                    backend: page.backend
                    Layout.rightMargin: 8
                    visible: !searchExpanded
                }

                Label {
                    text: "Browse Patterns"
                    font.pixelSize: 18
                    font.bold: true
                    color: Components.ThemeManager.textPrimary
                    visible: !searchExpanded
                }

                // Pattern count
                Label {
                    text: patternModel.rowCount() + " patterns"
                    font.pixelSize: 12
                    color: Components.ThemeManager.textTertiary
                    visible: !searchExpanded
                }
                
                Item { 
                    Layout.fillWidth: true 
                    visible: !searchExpanded
                }
                
                // Expandable search
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
                            
                            // Remove automatic filtering on text change
                            // onTextChanged: patternModel.filter(text)
                            
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
                            
                            // Handle Enter key - triggers onAccepted
                            Keys.onReturnPressed: {
                                // onAccepted will be called automatically
                                // Just hide keyboard and unfocus
                                Qt.inputMethod.hide()
                                focus = false
                            }
                            
                            Keys.onEscapePressed: {
                                // Clear search and hide keyboard
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
                
                // Close button when expanded
                Button {
                    text: "✕"
                    font.pixelSize: 18
                    flat: true
                    visible: searchExpanded
                    Layout.preferredWidth: 32
                    Layout.preferredHeight: 32
                    onClicked: {
                        searchExpanded = false
                        searchField.text = ""
                        searchField.lastSearchText = ""
                        searchField.focus = false
                        // Clear the filter when closing search
                        patternModel.filter("")
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
            
            // Add smooth scrolling
            ScrollBar.vertical: ScrollBar {
                active: true
                policy: ScrollBar.AsNeeded
            }
            
            delegate: ModernPatternCard {
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
            
            // Add scroll animations
            add: Transition {
                NumberAnimation { property: "opacity"; from: 0; to: 1; duration: 300 }
                NumberAnimation { property: "scale"; from: 0.8; to: 1; duration: 300 }
            }
        }
        
        // Empty state
        Item {
            Layout.fillWidth: true
            Layout.fillHeight: true
            visible: patternModel.rowCount() === 0 && searchField.text !== ""

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
}