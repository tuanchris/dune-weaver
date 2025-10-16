import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15
import QtQuick.Effects
import "../components"

Page {
    id: page
    property var backend: null
    property var serialPorts: []
    property string selectedPort: ""
    property bool isSerialConnected: false
    property bool autoPlayOnBoot: false
    
    // Backend signal connections
    Connections {
        target: backend
        
        function onSerialPortsUpdated(ports) {
            console.log("Serial ports updated:", ports)
            serialPorts = ports
        }
        
        function onSerialConnectionChanged(connected) {
            console.log("Serial connection changed:", connected)
            isSerialConnected = connected
        }
        
        function onCurrentPortChanged(port) {
            console.log("Current port changed:", port)
            if (port) {
                selectedPort = port
            }
        }
        
        
        function onSettingsLoaded() {
            console.log("Settings loaded")
            if (backend) {
                autoPlayOnBoot = backend.autoPlayOnBoot
                isSerialConnected = backend.serialConnected
                // Screen timeout is now managed by button selection, no need to convert
                if (backend.currentPort) {
                    selectedPort = backend.currentPort
                }
            }
        }
    }
    
    // Refresh serial ports on page load
    Component.onCompleted: {
        refreshSerialPorts()
        loadSettings()
    }
    
    function refreshSerialPorts() {
        if (backend) {
            backend.refreshSerialPorts()
        }
    }
    
    function loadSettings() {
        if (backend) {
            backend.loadControlSettings()
        }
    }
    
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
                    text: "Table Control"
                    font.pixelSize: 18
                    font.bold: true
                    color: "#333"
                }
                
                Item { 
                    Layout.fillWidth: true 
                }
            }
        }
        
        // Main Content
        ScrollView {
            Layout.fillWidth: true
            Layout.fillHeight: true
            contentWidth: availableWidth
            
            ColumnLayout {
                width: parent.width
                anchors.margins: 5
                spacing: 2
                
                // Serial Connection Section
                Rectangle {
                    Layout.fillWidth: true
                    Layout.preferredHeight: 160
                    Layout.margins: 5
                    radius: 8
                    color: "white"
                    
                    ColumnLayout {
                        anchors.fill: parent
                        anchors.margins: 15
                        spacing: 10
                        
                        Label {
                            text: "Serial Connection"
                            font.pixelSize: 14
                            font.bold: true
                            color: "#333"
                        }
                        
                        RowLayout {
                            Layout.fillWidth: true
                            spacing: 10
                            
                            Rectangle {
                                Layout.fillWidth: true
                                Layout.preferredHeight: 40
                                radius: 6
                                color: isSerialConnected ? "#e8f5e8" : "#f8f9fa"
                                border.color: isSerialConnected ? "#4CAF50" : "#e5e7eb"
                                border.width: 1
                                
                                RowLayout {
                                    anchors.fill: parent
                                    anchors.margins: 8
                                    
                                    Label {
                                        text: isSerialConnected ? 
                                              (selectedPort ? `Connected: ${selectedPort}` : "Connected") :
                                              (selectedPort || "No port selected")
                                        color: isSerialConnected ? "#2e7d32" : (selectedPort ? "#333" : "#999")
                                        font.pixelSize: 12
                                        font.bold: isSerialConnected
                                        Layout.fillWidth: true
                                    }
                                    
                                    Text {
                                        text: "▼"
                                        color: "#666"
                                        font.pixelSize: 10
                                        visible: !isSerialConnected
                                    }
                                }
                                
                                MouseArea {
                                    anchors.fill: parent
                                    enabled: !isSerialConnected
                                    onClicked: portMenu.open()
                                }
                                
                                Menu {
                                    id: portMenu
                                    y: parent.height

                                    Repeater {
                                        model: serialPorts
                                        MenuItem {
                                            text: modelData
                                            onTriggered: {
                                                selectedPort = modelData
                                            }
                                        }
                                    }
                                    
                                    MenuSeparator {}
                                    
                                    MenuItem {
                                        text: "Refresh Ports"
                                        onTriggered: refreshSerialPorts()
                                    }
                                }
                            }
                            
                            ModernControlButton {
                                Layout.preferredWidth: 150
                                Layout.preferredHeight: 40
                                text: isSerialConnected ? "Disconnect" : "Connect"
                                icon: isSerialConnected ? "◉" : "○"
                                buttonColor: isSerialConnected ? "#dc2626" : "#059669"
                                fontSize: 11
                                enabled: isSerialConnected || selectedPort !== ""
                                
                                onClicked: {
                                    if (backend) {
                                        if (isSerialConnected) {
                                            backend.disconnectSerial()
                                        } else {
                                            backend.connectSerial(selectedPort)
                                        }
                                    }
                                }
                            }
                        }
                        
                        RowLayout {
                            Layout.fillWidth: true
                            spacing: 8
                            visible: !isSerialConnected
                            
                            ModernControlButton {
                                Layout.fillWidth: true
                                Layout.preferredHeight: 35
                                text: "Refresh Ports"
                                icon: "↻"
                                buttonColor: "#6b7280"
                                fontSize: 10
                                
                                onClicked: refreshSerialPorts()
                            }
                        }
                    }
                }
                
                // Hardware Movement Section
                Rectangle {
                    Layout.fillWidth: true
                    Layout.preferredHeight: 100
                    Layout.margins: 5
                    radius: 8
                    color: "white"
                    
                    ColumnLayout {
                        anchors.fill: parent
                        anchors.margins: 15
                        spacing: 10
                        
                        Label {
                            text: "Table Movement"
                            font.pixelSize: 14
                            font.bold: true
                            color: "#333"
                        }
                        
                        GridLayout {
                            Layout.fillWidth: true
                            columns: 3
                            rowSpacing: 8
                            columnSpacing: 8
                            
                            ModernControlButton {
                                Layout.fillWidth: true
                                Layout.preferredHeight: 45
                                text: "Home"
                                icon: "⌂"
                                buttonColor: "#2563eb"
                                fontSize: 12
                                enabled: isSerialConnected
                                
                                onClicked: {
                                    if (backend) backend.sendHome()
                                }
                            }
                            
                            ModernControlButton {
                                Layout.fillWidth: true
                                Layout.preferredHeight: 45
                                text: "Center"
                                icon: "◎"
                                buttonColor: "#2563eb"
                                fontSize: 12
                                enabled: isSerialConnected
                                
                                onClicked: {
                                    if (backend) backend.moveToCenter()
                                }
                            }
                            
                            ModernControlButton {
                                Layout.fillWidth: true
                                Layout.preferredHeight: 45
                                text: "Perimeter"
                                icon: "○"
                                buttonColor: "#2563eb"
                                fontSize: 12
                                enabled: isSerialConnected
                                
                                onClicked: {
                                    if (backend) backend.moveToPerimeter()
                                }
                            }
                        }
                    }
                }
                
                
                // Auto Play on Boot Section
                Rectangle {
                    Layout.fillWidth: true
                    Layout.preferredHeight: 200  // Reduced from 280 for single row layout
                    Layout.margins: 5
                    radius: 8
                    color: "white"
                    
                    ColumnLayout {
                        anchors.fill: parent
                        anchors.margins: 15
                        spacing: 10
                        
                        Label {
                            text: "Auto Play Settings"
                            font.pixelSize: 14
                            font.bold: true
                            color: "#333"
                        }
                        
                        RowLayout {
                            Layout.fillWidth: true
                            spacing: 10
                            
                            Label {
                                text: "Auto play on boot:"
                                font.pixelSize: 12
                                color: "#666"
                                Layout.fillWidth: true
                            }
                            
                            Switch {
                                id: autoPlaySwitch
                                checked: autoPlayOnBoot
                                
                                onToggled: {
                                    autoPlayOnBoot = checked
                                    if (backend) {
                                        backend.setAutoPlayOnBoot(checked)
                                    }
                                }
                            }
                        }
                        
                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: 15
                            
                            Label {
                                text: "Screen timeout:"
                                font.pixelSize: 14
                                font.bold: true
                                color: "#333"
                                Layout.alignment: Qt.AlignLeft
                            }
                            
                            // Touch-friendly button row for timeout options
                            RowLayout {
                                id: timeoutGrid
                                Layout.fillWidth: true
                                spacing: 8
                                
                                property string currentSelection: backend ? backend.getCurrentScreenTimeoutOption() : "5 minutes"
                                
                                // 30 seconds button
                                Rectangle {
                                    Layout.preferredWidth: 100
                                    Layout.preferredHeight: 50
                                    color: timeoutGrid.currentSelection === "30 seconds" ? "#2196F3" : "#f0f0f0"
                                    border.color: timeoutGrid.currentSelection === "30 seconds" ? "#1976D2" : "#ccc"
                                    border.width: 2
                                    radius: 8
                                    
                                    Label {
                                        anchors.centerIn: parent
                                        text: "30s"
                                        font.pixelSize: 14
                                        font.bold: true
                                        color: timeoutGrid.currentSelection === "30 seconds" ? "white" : "#333"
                                    }
                                    
                                    MouseArea {
                                        anchors.fill: parent
                                        onClicked: {
                                            if (backend) {
                                                backend.setScreenTimeoutByOption("30 seconds")
                                                timeoutGrid.currentSelection = "30 seconds"
                                            }
                                        }
                                    }
                                }
                                
                                // 1 minute button
                                Rectangle {
                                    Layout.preferredWidth: 100
                                    Layout.preferredHeight: 50
                                    color: timeoutGrid.currentSelection === "1 minute" ? "#2196F3" : "#f0f0f0"
                                    border.color: timeoutGrid.currentSelection === "1 minute" ? "#1976D2" : "#ccc"
                                    border.width: 2
                                    radius: 8
                                    
                                    Label {
                                        anchors.centerIn: parent
                                        text: "1min"
                                        font.pixelSize: 14
                                        font.bold: true
                                        color: timeoutGrid.currentSelection === "1 minute" ? "white" : "#333"
                                    }
                                    
                                    MouseArea {
                                        anchors.fill: parent
                                        onClicked: {
                                            if (backend) {
                                                backend.setScreenTimeoutByOption("1 minute")
                                                timeoutGrid.currentSelection = "1 minute"
                                            }
                                        }
                                    }
                                }
                                
                                // 5 minutes button
                                Rectangle {
                                    Layout.preferredWidth: 100
                                    Layout.preferredHeight: 50
                                    color: timeoutGrid.currentSelection === "5 minutes" ? "#2196F3" : "#f0f0f0"
                                    border.color: timeoutGrid.currentSelection === "5 minutes" ? "#1976D2" : "#ccc"
                                    border.width: 2
                                    radius: 8
                                    
                                    Label {
                                        anchors.centerIn: parent
                                        text: "5min"
                                        font.pixelSize: 14
                                        font.bold: true
                                        color: timeoutGrid.currentSelection === "5 minutes" ? "white" : "#333"
                                    }
                                    
                                    MouseArea {
                                        anchors.fill: parent
                                        onClicked: {
                                            if (backend) {
                                                backend.setScreenTimeoutByOption("5 minutes")
                                                timeoutGrid.currentSelection = "5 minutes"
                                            }
                                        }
                                    }
                                }
                                
                                // 10 minutes button
                                Rectangle {
                                    Layout.preferredWidth: 100
                                    Layout.preferredHeight: 50
                                    color: timeoutGrid.currentSelection === "10 minutes" ? "#2196F3" : "#f0f0f0"
                                    border.color: timeoutGrid.currentSelection === "10 minutes" ? "#1976D2" : "#ccc"
                                    border.width: 2
                                    radius: 8
                                    
                                    Label {
                                        anchors.centerIn: parent
                                        text: "10min"
                                        font.pixelSize: 14
                                        font.bold: true
                                        color: timeoutGrid.currentSelection === "10 minutes" ? "white" : "#333"
                                    }
                                    
                                    MouseArea {
                                        anchors.fill: parent
                                        onClicked: {
                                            if (backend) {
                                                backend.setScreenTimeoutByOption("10 minutes")
                                                timeoutGrid.currentSelection = "10 minutes"
                                            }
                                        }
                                    }
                                }
                                
                                // Never button
                                Rectangle {
                                    Layout.preferredWidth: 100
                                    Layout.preferredHeight: 50
                                    color: timeoutGrid.currentSelection === "Never" ? "#FF9800" : "#f0f0f0"
                                    border.color: timeoutGrid.currentSelection === "Never" ? "#F57C00" : "#ccc"
                                    border.width: 2
                                    radius: 8
                                    
                                    Label {
                                        anchors.centerIn: parent
                                        text: "Never"
                                        font.pixelSize: 14
                                        font.bold: true
                                        color: timeoutGrid.currentSelection === "Never" ? "white" : "#333"
                                    }
                                    
                                    MouseArea {
                                        anchors.fill: parent
                                        onClicked: {
                                            if (backend) {
                                                backend.setScreenTimeoutByOption("Never")
                                                timeoutGrid.currentSelection = "Never"
                                            }
                                        }
                                    }
                                }
                                
                                // Update selection when backend changes
                                Connections {
                                    target: backend
                                    function onScreenTimeoutChanged() {
                                        if (backend) {
                                            timeoutGrid.currentSelection = backend.getCurrentScreenTimeoutOption()
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
                
                // Add some bottom spacing for better scrolling
                Item {
                    Layout.preferredHeight: 20
                }
            }
        }
    }
}