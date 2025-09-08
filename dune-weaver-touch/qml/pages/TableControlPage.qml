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
    property int currentSpeed: 130
    property bool autoPlayOnBoot: false
    property int screenTimeoutMinutes: 0
    
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
        
        function onSpeedChanged(speed) {
            console.log("Speed changed:", speed)
            currentSpeed = speed
        }
        
        function onSettingsLoaded() {
            console.log("Settings loaded")
            if (backend) {
                autoPlayOnBoot = backend.autoPlayOnBoot
                currentSpeed = backend.currentSpeed
                isSerialConnected = backend.serialConnected
                screenTimeoutMinutes = Math.round(backend.screenTimeout / 60)
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
                anchors.margins: 10
                spacing: 10
                
                // Serial Connection Section
                Rectangle {
                    Layout.fillWidth: true
                    Layout.preferredHeight: 160
                    Layout.margins: 10
                    radius: 8
                    color: "white"
                    
                    ColumnLayout {
                        anchors.fill: parent
                        anchors.margins: 15
                        spacing: 10
                        
                        Label {
                            text: "Serial Connection"
                            font.pixelSize: 16
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
                                icon: isSerialConnected ? "🔌" : "🔗"
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
                                icon: "🔄"
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
                    Layout.preferredHeight: 180
                    Layout.margins: 10
                    radius: 8
                    color: "white"
                    
                    ColumnLayout {
                        anchors.fill: parent
                        anchors.margins: 15
                        spacing: 10
                        
                        Label {
                            text: "Table Movement"
                            font.pixelSize: 16
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
                                icon: "🏠"
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
                                icon: "🎯"
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
                                icon: "⭕"
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
                
                // Speed Control Section
                Rectangle {
                    Layout.fillWidth: true
                    Layout.preferredHeight: 120
                    Layout.margins: 10
                    radius: 8
                    color: "white"
                    
                    ColumnLayout {
                        anchors.fill: parent
                        anchors.margins: 15
                        spacing: 10
                        
                        Label {
                            text: "Speed Control"
                            font.pixelSize: 16
                            font.bold: true
                            color: "#333"
                        }
                        
                        RowLayout {
                            Layout.fillWidth: true
                            spacing: 10
                            
                            Label {
                                text: "Speed:"
                                font.pixelSize: 12
                                color: "#666"
                            }
                            
                            Slider {
                                id: speedSlider
                                Layout.fillWidth: true
                                from: 10
                                to: 500
                                value: currentSpeed
                                stepSize: 10
                                
                                onValueChanged: {
                                    currentSpeed = Math.round(value)
                                }
                                
                                onPressedChanged: {
                                    if (!pressed && backend) {
                                        backend.setSpeed(currentSpeed)
                                    }
                                }
                            }
                            
                            Label {
                                text: currentSpeed
                                font.pixelSize: 12
                                font.bold: true
                                color: "#333"
                                Layout.preferredWidth: 40
                            }
                        }
                    }
                }
                
                // Auto Play on Boot Section
                Rectangle {
                    Layout.fillWidth: true
                    Layout.preferredHeight: 160
                    Layout.margins: 10
                    radius: 8
                    color: "white"
                    
                    ColumnLayout {
                        anchors.fill: parent
                        anchors.margins: 15
                        spacing: 10
                        
                        Label {
                            text: "Auto Play Settings"
                            font.pixelSize: 16
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
                        
                        RowLayout {
                            Layout.fillWidth: true
                            spacing: 10
                            
                            Label {
                                text: "Screen timeout:"
                                font.pixelSize: 12
                                color: "#666"
                            }
                            
                            SpinBox {
                                id: timeoutSpinBox
                                Layout.preferredWidth: 120
                                from: 0
                                to: 120
                                value: screenTimeoutMinutes
                                stepSize: 5
                                
                                textFromValue: function(value, locale) {
                                    return value === 0 ? "Never" : value + " min"
                                }
                                
                                onValueModified: {
                                    screenTimeoutMinutes = value
                                    if (backend) {
                                        // Convert minutes to seconds for backend
                                        backend.screenTimeout = value * 60
                                    }
                                }
                            }
                            
                            Item { Layout.fillWidth: true }
                        }
                    }
                }
                
                // Debug Screen Control Section (remove this later)
                Rectangle {
                    Layout.fillWidth: true
                    Layout.preferredHeight: 120
                    Layout.margins: 10
                    radius: 8
                    color: "white"
                    border.color: "#ff0000"
                    border.width: 2
                    
                    ColumnLayout {
                        anchors.fill: parent
                        anchors.margins: 15
                        spacing: 10
                        
                        Label {
                            text: "DEBUG: Screen Control (Remove Later)"
                            font.pixelSize: 12
                            font.bold: true
                            color: "#ff0000"
                        }
                        
                        RowLayout {
                            Layout.fillWidth: true
                            spacing: 10
                            
                            ModernControlButton {
                                Layout.fillWidth: true
                                Layout.preferredHeight: 35
                                text: "Screen OFF"
                                icon: "💤"
                                buttonColor: "#dc2626"
                                fontSize: 10
                                
                                onClicked: {
                                    console.log("DEBUG: Manual screen off clicked")
                                    backend.turnScreenOff()
                                }
                            }
                            
                            ModernControlButton {
                                Layout.fillWidth: true
                                Layout.preferredHeight: 35
                                text: "Screen ON"
                                icon: "💡"
                                buttonColor: "#059669"
                                fontSize: 10
                                
                                onClicked: {
                                    console.log("DEBUG: Manual screen on clicked")
                                    backend.turnScreenOn()
                                }
                            }
                            
                            ModernControlButton {
                                Layout.fillWidth: true
                                Layout.preferredHeight: 35
                                text: "Reset Timer"
                                icon: "⏰"
                                buttonColor: "#2563eb"
                                fontSize: 10
                                
                                onClicked: {
                                    console.log("DEBUG: Reset activity timer clicked")
                                    backend.resetActivityTimer()
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