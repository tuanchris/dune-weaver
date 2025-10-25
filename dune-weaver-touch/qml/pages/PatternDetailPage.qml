import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15
import "../components"
import "../components" as Components

Page {
    id: page
    property string patternName: ""
    property string patternPath: ""
    property string patternPreview: ""
    property var backend: null

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
}