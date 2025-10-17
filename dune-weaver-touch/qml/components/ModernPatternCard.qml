import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Effects
import "." as Components

Rectangle {
    property string name: ""
    property alias preview: previewImage.source

    // Clean up the pattern name for display
    property string cleanName: {
        var cleanedName = name
        // Remove path (get everything after the last slash)
        var parts = cleanedName.split('/')
        cleanedName = parts[parts.length - 1]
        // Remove .thr extension
        cleanedName = cleanedName.replace('.thr', '')
        return cleanedName
    }

    signal clicked()

    color: Components.ThemeManager.surfaceColor
    radius: 12
    
    // Drop shadow effect
    layer.enabled: true
    layer.effect: MultiEffect {
        shadowEnabled: true
        shadowColor: "#20000000"
        shadowBlur: 0.8
        shadowVerticalOffset: 2
        shadowHorizontalOffset: 0
    }
    
    // Hover/press animation
    scale: mouseArea.pressed ? 0.95 : (mouseArea.containsMouse ? 1.02 : 1.0)
    
    Behavior on scale {
        NumberAnimation { duration: 150; easing.type: Easing.OutQuad }
    }
    
    Column {
        anchors.fill: parent
        anchors.margins: 8
        spacing: 6
        
        // Preview image container
        Rectangle {
            width: parent.width
            height: parent.height - nameLabel.height - 12
            radius: 8
            color: Components.ThemeManager.previewBackground
            clip: true
            
            Image {
                id: previewImage
                anchors.fill: parent
                fillMode: Image.PreserveAspectFit
                source: preview ? "file:///" + preview : ""
                smooth: true
                
                // Loading animation
                opacity: status === Image.Ready ? 1 : 0
                Behavior on opacity {
                    NumberAnimation { duration: 200 }
                }
            }
            
            // Placeholder when no preview
            Rectangle {
                anchors.fill: parent
                color: Components.ThemeManager.placeholderBackground
                visible: previewImage.status === Image.Error || previewImage.source == ""
                radius: 8

                Column {
                    anchors.centerIn: parent
                    spacing: 8

                    Text {
                        text: "◻"
                        font.pixelSize: 32
                        anchors.horizontalCenter: parent.horizontalCenter
                        color: Components.ThemeManager.placeholderText
                    }

                    Text {
                        text: "No Preview"
                        anchors.horizontalCenter: parent.horizontalCenter
                        color: Components.ThemeManager.textTertiary
                        font.pixelSize: 12
                    }
                }
            }
        }

        // Pattern name
        Label {
            id: nameLabel
            text: cleanName
            width: parent.width
            elide: Label.ElideRight
            horizontalAlignment: Label.AlignHCenter
            font.pixelSize: 13
            font.weight: Font.Medium
            color: Components.ThemeManager.textPrimary
            wrapMode: Text.Wrap
            maximumLineCount: 2
        }
    }
    
    // Click area
    MouseArea {
        id: mouseArea
        anchors.fill: parent
        hoverEnabled: true
        onClicked: parent.clicked()
        
        // Ripple effect on click
        Rectangle {
            id: ripple
            width: 0
            height: 0
            radius: width / 2
            color: "#20000000"
            anchors.centerIn: parent
            
            NumberAnimation {
                id: rippleAnimation
                target: ripple
                property: "width"
                from: 0
                to: mouseArea.width * 1.5
                duration: 300
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