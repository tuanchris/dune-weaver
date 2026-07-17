import QtQuick 2.15
import QtQuick.Controls 2.15
import "." as Components

// Pattern card: the preview PNG is a circular sand dish (thr_preview.py
// renders the disc with transparent corners), so it sits directly on the
// card surface — no boxed frame around round art.
Rectangle {
    id: card

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

    color: mouseArea.pressed ? Components.ThemeManager.pressedColor
                             : Components.ThemeManager.surfaceColor
    radius: Components.ThemeManager.radiusMd
    border.width: 1
    border.color: Components.ThemeManager.borderColor

    scale: mouseArea.pressed ? 0.97 : 1.0
    Behavior on scale {
        NumberAnimation { duration: 100; easing.type: Easing.OutQuad }
    }

    Column {
        anchors.fill: parent
        anchors.margins: Components.ThemeManager.spaceSm
        spacing: Components.ThemeManager.spaceXs

        Item {
            width: parent.width
            height: parent.height - nameLabel.height - Components.ThemeManager.spaceXs

            Image {
                id: previewImage
                anchors.fill: parent
                fillMode: Image.PreserveAspectFit
                source: preview ? "file:///" + preview : ""
                smooth: true
                // Decode off the GUI thread, at grid-cell resolution — a
                // full 512px decode per tile is what makes flicking stutter.
                asynchronous: true
                sourceSize.width: 200
                sourceSize.height: 200

                opacity: status === Image.Ready ? 1 : 0
                Behavior on opacity {
                    NumberAnimation { duration: 200 }
                }
            }

            // Placeholder dish until the preview is decoded (or on failure)
            Rectangle {
                anchors.centerIn: parent
                width: Math.min(parent.width, parent.height)
                height: width
                radius: width / 2
                color: Components.ThemeManager.cardColor
                border.width: 1
                border.color: Components.ThemeManager.borderColor
                visible: previewImage.status !== Image.Ready

                Components.Icon {
                    anchors.centerIn: parent
                    name: "radio_unchecked"
                    size: 28
                    color: Components.ThemeManager.placeholderText
                }
            }
        }

        Label {
            id: nameLabel
            text: cleanName
            width: parent.width
            elide: Label.ElideRight
            horizontalAlignment: Label.AlignHCenter
            font.family: Components.ThemeManager.fontMedium
            font.pixelSize: 13
            color: Components.ThemeManager.textPrimary
            maximumLineCount: 1
        }
    }

    MouseArea {
        id: mouseArea
        anchors.fill: parent
        onClicked: card.clicked()
    }
}
