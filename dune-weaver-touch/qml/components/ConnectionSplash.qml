import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15

Rectangle {
    id: root
    anchors.fill: parent
    color: "#1a1a1a"  // Dark background
    
    property string statusText: "Connecting to backend..."
    property bool showRetryButton: false
    
    signal retryConnection()
    
    ColumnLayout {
        anchors.centerIn: parent
        spacing: 30
        width: Math.min(parent.width * 0.8, 400)
        
        // Logo/Title Area
        Rectangle {
            Layout.alignment: Qt.AlignHCenter
            width: 120
            height: 120
            radius: 60
            color: "#2d2d2d"
            border.color: "#4a90e2"
            border.width: 3
            
            Text {
                anchors.centerIn: parent
                text: "DW"
                font.pixelSize: 36
                font.bold: true
                color: "#4a90e2"
            }
        }
        
        Text {
            Layout.alignment: Qt.AlignHCenter
            text: "Dune Weaver Touch"
            font.pixelSize: 32
            font.bold: true
            color: "white"
        }
        
        // Status Area
        Rectangle {
            Layout.alignment: Qt.AlignHCenter
            Layout.preferredWidth: parent.width
            Layout.preferredHeight: 80
            color: "#2d2d2d"
            radius: 10
            border.color: "#444"
            border.width: 1
            
            RowLayout {
                anchors.fill: parent
                anchors.margins: 20
                spacing: 15
                
                // Spinning loader
                Rectangle {
                    width: 40
                    height: 40
                    radius: 20
                    color: "transparent"
                    border.color: "#4a90e2"
                    border.width: 3
                    
                    Rectangle {
                        width: 8
                        height: 8
                        radius: 4
                        color: "#4a90e2"
                        anchors.top: parent.top
                        anchors.horizontalCenter: parent.horizontalCenter
                        anchors.topMargin: 2
                        
                        visible: !root.showRetryButton
                    }
                    
                    RotationAnimation on rotation {
                        running: !root.showRetryButton
                        loops: Animation.Infinite
                        from: 0
                        to: 360
                        duration: 2000
                    }
                }
                
                Text {
                    Layout.fillWidth: true
                    text: root.statusText
                    font.pixelSize: 16
                    color: "#cccccc"
                    wrapMode: Text.WordWrap
                    verticalAlignment: Text.AlignVCenter
                }
            }
        }
        
        // Retry Button (only show when connection fails)
        Button {
            Layout.alignment: Qt.AlignHCenter
            visible: root.showRetryButton
            text: "Retry Connection"
            font.pixelSize: 16
            
            background: Rectangle {
                color: parent.pressed ? "#3a7bc8" : "#4a90e2"
                radius: 8
                border.color: "#5a9ff2"
                border.width: 1
                
                Behavior on color {
                    ColorAnimation { duration: 150 }
                }
            }
            
            contentItem: Text {
                text: parent.text
                font: parent.font
                color: "white"
                horizontalAlignment: Text.AlignHCenter
                verticalAlignment: Text.AlignVCenter
            }
            
            onClicked: {
                root.showRetryButton = false
                root.retryConnection()
            }
        }
        
        // Connection Help Text
        Text {
            Layout.alignment: Qt.AlignHCenter
            Layout.preferredWidth: parent.width
            text: "Make sure the Dune Weaver backend is running on this device."
            font.pixelSize: 14
            color: "#888"
            horizontalAlignment: Text.AlignHCenter
            wrapMode: Text.WordWrap
        }
    }
    
    // Background animation - subtle pulse
    Rectangle {
        anchors.fill: parent
        color: "#4a90e2"
        opacity: 0.05
        
        SequentialAnimation on opacity {
            running: !root.showRetryButton
            loops: Animation.Infinite
            NumberAnimation { to: 0.1; duration: 2000 }
            NumberAnimation { to: 0.05; duration: 2000 }
        }
    }
}