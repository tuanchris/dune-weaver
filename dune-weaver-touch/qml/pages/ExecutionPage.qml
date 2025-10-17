import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15
import Qt.labs.folderlistmodel 2.15
import "../components"

Page {
    id: page
    property var backend: null
    property var stackView: null
    property string patternName: ""
    property string patternPreview: ""  // Backend provides this via executionStarted signal
    
    // Debug backend connection
    onBackendChanged: {
        console.log("ExecutionPage: backend changed to", backend)
        if (backend) {
            console.log("ExecutionPage: backend.serialConnected =", backend.serialConnected)
            console.log("ExecutionPage: backend.isConnected =", backend.isConnected)
        }
    }
    
    Component.onCompleted: {
        console.log("ExecutionPage: Component completed, backend =", backend)
        if (backend) {
            console.log("ExecutionPage: initial serialConnected =", backend.serialConnected)
        }
    }
    
    // Direct connection to backend signals
    Connections {
        target: backend

        function onSerialConnectionChanged(connected) {
            console.log("ExecutionPage: received serialConnectionChanged signal:", connected)
        }

        function onConnectionChanged() {
            console.log("ExecutionPage: received connectionChanged signal")
            if (backend) {
                console.log("ExecutionPage: after connectionChanged, serialConnected =", backend.serialConnected)
            }
        }

        function onExecutionStarted(fileName, preview) {
            console.log("🎯 ExecutionPage: executionStarted signal received!")
            console.log("🎯 Pattern:", fileName)
            console.log("🎯 Preview path:", preview)
            // Update preview directly from backend signal
            patternName = fileName
            patternPreview = preview
        }
    }
    
    
    Rectangle {
        anchors.fill: parent
        color: "#f5f5f5"
    }
    
    ColumnLayout {
        anchors.fill: parent
        spacing: 0
        
        // Header (consistent with other pages)
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
                anchors.leftMargin: 15
                anchors.rightMargin: 10
                
                ConnectionStatus {
                    backend: page.backend
                    Layout.rightMargin: 8
                }
                
                Label {
                    text: "Pattern Execution"
                    font.pixelSize: 18
                    font.bold: true
                    color: "#333"
                }
                
                Item { 
                    Layout.fillWidth: true 
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
                        source: {
                            var finalSource = ""

                            // Trust the backend's preview path - it already has recursive search
                            if (patternPreview) {
                                // Backend returns absolute path, just add file:// prefix
                                finalSource = "file://" + patternPreview
                                console.log("🖼️ Using backend patternPreview:", finalSource)
                            } else {
                                console.log("🖼️ No preview from backend")
                            }

                            return finalSource
                        }
                        fillMode: Image.PreserveAspectFit

                        onStatusChanged: {
                            console.log("📷 Image status:", status, "for source:", source)
                            if (status === Image.Error) {
                                console.log("❌ Image failed to load:", source)
                            } else if (status === Image.Ready) {
                                console.log("✅ Image loaded successfully:", source)
                            } else if (status === Image.Loading) {
                                console.log("🔄 Image loading:", source)
                            }
                        }

                        onSourceChanged: {
                            console.log("🔄 Image source changed to:", source)
                        }
                        
                        Rectangle {
                            anchors.fill: parent
                            color: "#f0f0f0"
                            visible: parent.status === Image.Error || parent.source == ""
                            
                            Column {
                                anchors.centerIn: parent
                                spacing: 10
                                
                                Text {
                                    text: "⚙"
                                    font.pixelSize: 48
                                    color: "#ccc"
                                    anchors.horizontalCenter: parent.horizontalCenter
                                }
                                
                                Text {
                                    text: "Pattern Preview"
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
                    
                    ScrollView {
                        anchors.fill: parent
                        anchors.margins: 10
                        clip: true
                        contentWidth: availableWidth
                        
                        Column {
                            width: parent.width
                            spacing: 8
                        
                        // Pattern Name
                        Rectangle {
                            width: parent.width
                            height: 50
                            radius: 8
                            color: "#f8f9fa"
                            border.color: "#e5e7eb"
                            border.width: 1
                            
                            Column {
                                anchors.centerIn: parent
                                spacing: 4
                                
                                Label {
                                    text: "Current Pattern"
                                    font.pixelSize: 10
                                    color: "#666"
                                    anchors.horizontalCenter: parent.horizontalCenter
                                }
                                
                                Label {
                                    text: {
                                        // Use WebSocket current pattern first, then fallback to passed parameter
                                        var displayName = ""
                                        if (backend && backend.currentFile) displayName = backend.currentFile
                                        else if (patternName) displayName = patternName
                                        else return "No pattern running"
                                        
                                        // Clean up the name for display
                                        var parts = displayName.split('/')
                                        displayName = parts[parts.length - 1]
                                        displayName = displayName.replace('.thr', '')
                                        return displayName
                                    }
                                    font.pixelSize: 12
                                    font.bold: true
                                    color: "#333"
                                    anchors.horizontalCenter: parent.horizontalCenter
                                    width: parent.parent.width - 20
                                    elide: Text.ElideMiddle
                                    horizontalAlignment: Text.AlignHCenter
                                }
                            }
                        }
                        
                        // Progress
                        Rectangle {
                            width: parent.width
                            height: 70
                            radius: 8
                            color: "#f8f9fa"
                            border.color: "#e5e7eb"
                            border.width: 1
                            
                            Column {
                                anchors.fill: parent
                                anchors.margins: 10
                                spacing: 8
                                
                                Label {
                                    text: "Progress"
                                    font.pixelSize: 12
                                    font.bold: true
                                    color: "#333"
                                }
                                
                                ProgressBar {
                                    width: parent.width
                                    height: 8
                                    value: backend ? backend.progress / 100 : 0
                                }
                                
                                Label {
                                    text: backend ? Math.round(backend.progress) + "%" : "0%"
                                    anchors.horizontalCenter: parent.horizontalCenter
                                    font.pixelSize: 14
                                    font.bold: true
                                    color: "#333"
                                }
                            }
                        }
                        
                        // Control Buttons
                        Rectangle {
                            width: parent.width
                            height: 90
                            radius: 8
                            color: "#f8f9fa"
                            border.color: "#e5e7eb"
                            border.width: 1
                            
                            Column {
                                anchors.fill: parent
                                anchors.margins: 10
                                spacing: 10
                                
                                Label {
                                    text: "Controls"
                                    font.pixelSize: 12
                                    font.bold: true
                                    color: "#333"
                                }
                                
                                // Control buttons row
                                Row {
                                    width: parent.width
                                    height: 35
                                    spacing: 8
                                    
                                    // Pause/Resume button
                                    Rectangle {
                                        width: (parent.width - 16) / 3  // Divide width evenly with spacing
                                        height: parent.height
                                        radius: 6
                                        color: pauseMouseArea.pressed ? "#1e40af" : (backend && backend.currentFile !== "" ? "#2563eb" : "#9ca3af")
                                        
                                        Text {
                                            anchors.centerIn: parent
                                            text: (backend && backend.isRunning) ? "||" : "▶"
                                            color: "white"
                                            font.pixelSize: 14
                                            font.bold: true
                                        }
                                        
                                        MouseArea {
                                            id: pauseMouseArea
                                            anchors.fill: parent
                                            enabled: backend && backend.currentFile !== ""
                                            onClicked: {
                                                if (backend) {
                                                    if (backend.isRunning) {
                                                        backend.pauseExecution()
                                                    } else {
                                                        backend.resumeExecution()
                                                    }
                                                }
                                            }
                                        }
                                    }
                                    
                                    // Stop button
                                    Rectangle {
                                        width: (parent.width - 16) / 3
                                        height: parent.height
                                        radius: 6
                                        color: stopMouseArea.pressed ? "#b91c1c" : (backend && backend.currentFile !== "" ? "#dc2626" : "#9ca3af")
                                        
                                        Text {
                                            anchors.centerIn: parent
                                            text: "■"
                                            color: "white"
                                            font.pixelSize: 14
                                            font.bold: true
                                        }
                                        
                                        MouseArea {
                                            id: stopMouseArea
                                            anchors.fill: parent
                                            enabled: backend
                                            onClicked: {
                                                if (backend) {
                                                    backend.stopExecution()
                                                }
                                            }
                                        }
                                    }
                                    
                                    // Skip button
                                    Rectangle {
                                        width: (parent.width - 16) / 3
                                        height: parent.height
                                        radius: 6
                                        color: skipMouseArea.pressed ? "#525252" : (backend && backend.currentFile !== "" ? "#6b7280" : "#9ca3af")
                                        
                                        Text {
                                            anchors.centerIn: parent
                                            text: "▶▶"
                                            color: "white"
                                            font.pixelSize: 14
                                            font.bold: true
                                        }
                                        
                                        MouseArea {
                                            id: skipMouseArea
                                            anchors.fill: parent
                                            enabled: backend && backend.currentFile !== ""
                                            onClicked: {
                                                if (backend) {
                                                    backend.skipPattern()
                                                }
                                            }
                                        }
                                    }
                                }
                            }
                        }
                        
                        // Speed Control Section
                        Rectangle {
                            width: parent.width
                            height: 120
                            radius: 8
                            color: "#f8f9fa"
                            border.color: "#e5e7eb"
                            border.width: 1
                            
                            Column {
                                anchors.fill: parent
                                anchors.margins: 10
                                spacing: 10
                                
                                Label {
                                    text: "Speed"
                                    font.pixelSize: 12
                                    font.bold: true
                                    color: "#333"
                                }
                                
                                // Touch-friendly button row for speed options
                                Row {
                                    id: speedControlRow
                                    width: parent.width
                                    spacing: 8
                                    
                                    property string currentSelection: backend ? backend.getCurrentSpeedOption() : "200"
                                    
                                    // Speed buttons
                                    Repeater {
                                        model: ["50", "100", "200", "300", "500"]
                                        
                                        Rectangle {
                                            width: (speedControlRow.width - 32) / 5  // Distribute evenly with spacing
                                            height: 50
                                            color: speedControlRow.currentSelection === modelData ? "#2196F3" : "#f0f0f0"
                                            border.color: speedControlRow.currentSelection === modelData ? "#1976D2" : "#ccc"
                                            border.width: 2
                                            radius: 8
                                            
                                            Label {
                                                anchors.centerIn: parent
                                                text: modelData
                                                font.pixelSize: 12
                                                font.bold: true
                                                color: speedControlRow.currentSelection === modelData ? "white" : "#333"
                                            }
                                            
                                            MouseArea {
                                                anchors.fill: parent
                                                onClicked: {
                                                    if (backend) {
                                                        backend.setSpeedByOption(modelData)
                                                        speedControlRow.currentSelection = modelData
                                                    }
                                                }
                                            }
                                        }
                                    }
                                    
                                    // Update selection when backend changes
                                    Connections {
                                        target: backend
                                        function onSpeedChanged(speed) {
                                            if (backend) {
                                                speedControlRow.currentSelection = backend.getCurrentSpeedOption()
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }
            }
        }
    }
}