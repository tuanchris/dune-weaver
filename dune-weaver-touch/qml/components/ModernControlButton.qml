import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15
import "." as Components

// Pill button — flat fill, darker while pressed, no hover states (touch-only
// device) and no effects layers (linuxfb). `icon` takes a Material icon name
// resolved by Icon.qml. `outlined` renders the quiet variant: transparent
// fill, buttonColor ring + label.
Rectangle {
    id: root

    property alias text: buttonLabel.text
    property string icon: ""
    property color buttonColor: Components.ThemeManager.accent
    // Fill variant picks label contrast from the fill's lightness, so amber
    // gets ink text and rust/sage get bone automatically.
    property color textColor: outlined
                              ? buttonColor
                              : (buttonColor.hslLightness > 0.55 ? "#241a0c" : "#fdf8ee")
    property bool outlined: false
    property bool enabled: true
    property int fontSize: Components.ThemeManager.fontSizeBody
    property int iconSize: -1  // -1 means fontSize + 4

    signal clicked()

    implicitHeight: Components.ThemeManager.touchTarget
    radius: height / 2
    color: {
        if (outlined)
            return mouseArea.pressed ? Components.ThemeManager.pressedColor : "transparent"
        return mouseArea.pressed ? Qt.darker(buttonColor, 1.15) : buttonColor
    }
    opacity: enabled ? 1.0 : 0.45
    border.width: outlined ? 1 : 0
    border.color: buttonColor

    scale: mouseArea.pressed ? 0.97 : 1.0
    Behavior on scale {
        NumberAnimation { duration: 100; easing.type: Easing.OutQuad }
    }

    RowLayout {
        anchors.centerIn: parent
        spacing: Components.ThemeManager.spaceSm

        Components.Icon {
            name: root.icon
            size: root.iconSize > 0 ? root.iconSize : root.fontSize + 4
            color: root.textColor
            visible: root.icon !== ""
        }

        Label {
            id: buttonLabel
            color: root.textColor
            font.family: Components.ThemeManager.fontDisplay
            font.pixelSize: root.fontSize
            visible: text !== ""
        }
    }

    MouseArea {
        id: mouseArea
        anchors.fill: parent
        enabled: root.enabled
        onClicked: root.clicked()
    }
}
