import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Window 2.15

Window {
    visible: true
    width: 800
    height: 480
    title: "Qt Minimal Test"

    // Simple gradient background - no complex effects
    Rectangle {
        anchors.fill: parent
        gradient: Gradient {
            GradientStop { position: 0.0; color: "#2196F3" }
            GradientStop { position: 1.0; color: "#1976D2" }
        }

        Column {
            anchors.centerIn: parent
            spacing: 30

            // Title
            Text {
                text: "✅ Qt/QML Works!"
                font.pixelSize: 48
                font.bold: true
                color: "white"
                anchors.horizontalCenter: parent.horizontalCenter
            }

            // Info text
            Text {
                text: "Minimal test app - no effects, no images"
                font.pixelSize: 18
                color: "white"
                opacity: 0.9
                anchors.horizontalCenter: parent.horizontalCenter
            }

            // Simple button without effects
            Rectangle {
                width: 200
                height: 60
                radius: 8
                color: mouseArea.pressed ? "#FFC107" : "#FF9800"
                anchors.horizontalCenter: parent.horizontalCenter

                Text {
                    text: "Test Button"
                    anchors.centerIn: parent
                    font.pixelSize: 20
                    font.bold: true
                    color: "white"
                }

                MouseArea {
                    id: mouseArea
                    anchors.fill: parent
                    onClicked: {
                        console.log("✅ Button clicked - touch/mouse works!")
                        statusText.text = "Button clicked at " + new Date().toLocaleTimeString()
                    }
                }
            }

            // Status text
            Text {
                id: statusText
                text: "Touch the button to test"
                font.pixelSize: 16
                color: "white"
                opacity: 0.8
                anchors.horizontalCenter: parent.horizontalCenter
            }
        }

        // Animation test - simple rotation
        Rectangle {
            width: 40
            height: 40
            radius: 20
            color: "#4CAF50"
            anchors.right: parent.right
            anchors.top: parent.top
            anchors.margins: 20

            RotationAnimation on rotation {
                from: 0
                to: 360
                duration: 2000
                loops: Animation.Infinite
            }

            Text {
                text: "↻"
                anchors.centerIn: parent
                font.pixelSize: 24
                color: "white"
            }
        }

        // FPS counter
        Text {
            text: "Qt " + Qt.application.version
            anchors.bottom: parent.bottom
            anchors.left: parent.left
            anchors.margins: 10
            font.pixelSize: 12
            color: "white"
            opacity: 0.6
        }
    }

    Component.onCompleted: {
        console.log("🎉 QML loaded successfully")
        console.log("📱 Window size:", width, "x", height)
    }
}
