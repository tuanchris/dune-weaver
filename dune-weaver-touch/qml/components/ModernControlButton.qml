import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15
import QtQuick.Effects

Rectangle {
    property alias text: buttonLabel.text
    property string icon: ""
    property color buttonColor: "#2196F3"
    property bool enabled: true
    property int fontSize: 16
    
    signal clicked()
    
    radius: 12
    color: enabled ? buttonColor : "#E0E0E0"
    opacity: enabled ? 1.0 : 0.6
    
    // Gradient effect
    gradient: Gradient {
        GradientStop { position: 0; color: Qt.lighter(buttonColor, 1.1) }
        GradientStop { position: 1; color: buttonColor }
    }
    
    // Press animation
    scale: mouseArea.pressed ? 0.95 : (mouseArea.containsMouse ? 1.02 : 1.0)
    
    Behavior on scale {
        NumberAnimation { duration: 150; easing.type: Easing.OutQuad }
    }
    
    Behavior on color {
        ColorAnimation { duration: 200 }
    }
    
    // Shadow effect
    layer.enabled: true
    layer.effect: MultiEffect {
        shadowEnabled: true
        shadowColor: "#25000000"
        shadowBlur: 0.8
        shadowVerticalOffset: 2
    }
    
    RowLayout {
        anchors.centerIn: parent
        spacing: 8
        
        Text {
            text: parent.parent.icon
            font.pixelSize: parent.parent.fontSize + 2
            visible: parent.parent.icon !== ""
        }
        
        Label {
            id: buttonLabel
            color: "white"
            font.pixelSize: parent.parent.fontSize
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