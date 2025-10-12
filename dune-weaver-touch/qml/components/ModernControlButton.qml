import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15

Rectangle {
    id: root
    property alias text: buttonLabel.text
    property string icon: ""
    property color buttonColor: "#2196F3"
    property bool enabled: true
    property int fontSize: 16

    signal clicked()

    radius: 12
    color: enabled ? buttonColor : "#E0E0E0"
    opacity: enabled ? 1.0 : 0.6

    // Border for better visibility on linuxfb
    border.width: 2
    border.color: enabled ? Qt.darker(root.buttonColor, 1.2) : "#BDBDBD"

    // Gradient effect (compatible with software rendering)
    gradient: Gradient {
        GradientStop { position: 0; color: Qt.lighter(root.buttonColor, 1.1) }
        GradientStop { position: 1; color: root.buttonColor }
    }

    // Press animation
    scale: mouseArea.pressed ? 0.95 : 1.0

    Behavior on scale {
        NumberAnimation { duration: 150; easing.type: Easing.OutQuad }
    }

    Behavior on color {
        ColorAnimation { duration: 200 }
    }

    // Simple shadow using Rectangle (linuxfb compatible)
    Rectangle {
        anchors.fill: parent
        anchors.topMargin: 2
        anchors.leftMargin: 2
        radius: parent.radius
        color: "#20000000"
        z: -1
    }

    RowLayout {
        anchors.centerIn: parent
        spacing: 8

        Text {
            text: root.icon
            font.pixelSize: root.fontSize + 2
            color: "white"
            visible: root.icon !== ""
        }

        Label {
            id: buttonLabel
            color: "white"
            font.pixelSize: root.fontSize
            font.bold: true
        }
    }
    
    MouseArea {
        id: mouseArea
        anchors.fill: parent
        hoverEnabled: true
        enabled: parent.enabled
        onClicked: parent.clicked()
        
        // Ripple effect
        Rectangle {
            id: ripple
            width: 0
            height: 0
            radius: width / 2
            color: "#40FFFFFF"
            anchors.centerIn: parent
            
            NumberAnimation {
                id: rippleAnimation
                target: ripple
                property: "width"
                from: 0
                to: parent.width * 1.2
                duration: 400
                easing.type: Easing.OutQuad
                
                onFinished: {
                    ripple.width = 0
                    ripple.height = 0
                }
            }
            
            Connections {
                target: mouseArea
                function onPressed() {
                    ripple.height = ripple.width
                    rippleAnimation.start()
                }
            }
        }
    }
}