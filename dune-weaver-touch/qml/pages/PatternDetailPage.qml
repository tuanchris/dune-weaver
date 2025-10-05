import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15
import "../components"

Page {
    id: page
    property string patternName: ""
    property string patternPath: ""
    property string patternPreview: ""
    property var backend: null
    
    Rectangle {
        anchors.fill: parent
        color: "#f5f5f5"
    }
    
    ColumnLayout {
        anchors.fill: parent
        spacing: 0
        
        // Header
        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 50
            color: "white"
            
            // Bottom border
            Rectangle {
                anchors.bottom: parent.bottom
                width: parent.width
                height: 1
                color: "#e5e7eb"
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
                }
                
                Label {
                    text: patternName
                    Layout.fillWidth: true
                    elide: Label.ElideRight
                    font.pixelSize: 16
                    font.bold: true
                    color: "#333"
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
                    color: "#ffffff"
                
                Image {
                    anchors.fill: parent
                    anchors.margins: 10
                    source: "" // Disabled to prevent WebP decoding errors on touch display
                    fillMode: Image.PreserveAspectFit
                    
                    Rectangle {
                        anchors.fill: parent
                        color: "#f0f0f0"
                        visible: parent.status === Image.Error || parent.source == ""
                        
                        Column {
                            anchors.centerIn: parent
                            spacing: 10
                            
                            Text {
                                text: "○"
                                font.pixelSize: 48
                                color: "#ccc"
                                anchors.horizontalCenter: parent.horizontalCenter
                            }
                            
                            Text {
                                text: "No Preview Available"
                                color: "#999"
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
                    color: "#e5e7eb"
                }
                
                // Right side - Controls (40% of width)
                Rectangle {
                    width: parent.width * 0.4 - 1
                    height: parent.height
                    color: "white"
                
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
                        color: "#f8f9fa"
                        border.color: "#e5e7eb"
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
                                color: "#333"
                            }
                            
                            RadioButton {
                                id: adaptiveRadio
                                text: "Adaptive"
                                checked: true
                                font.pixelSize: 10
                            }
                            
                            RadioButton {
                                id: centerRadio
                                text: "Clear Center"
                                font.pixelSize: 10
                            }
                            
                            RadioButton {
                                id: perimeterRadio
                                text: "Clear Edge"
                                font.pixelSize: 10
                            }
                            
                            RadioButton {
                                id: noneRadio
                                text: "None"
                                font.pixelSize: 10
                            }
                        }
                    }
                    
                    // Pattern Info
                    Rectangle {
                        width: parent.width
                        height: 80
                        radius: 8
                        color: "#f8f9fa"
                        border.color: "#e5e7eb"
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
                                color: "#333"
                            }
                            
                            Label {
                                text: "Name: " + patternName
                                font.pixelSize: 11
                                color: "#666"
                                elide: Text.ElideRight
                                width: parent.width
                            }
                            
                            Label {
                                text: "Type: Sand Pattern"
                                font.pixelSize: 11
                                color: "#666"
                            }
                        }
                    }
                }
            }
            }
        }
    }
}