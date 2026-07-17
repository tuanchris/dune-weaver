import QtQuick 2.15
import QtQuick.Controls 2.15
import "." as Components

// Toggle styled to the token system: ember when on, quiet when off.
Switch {
    id: control

    implicitWidth: 56
    implicitHeight: 32

    indicator: Rectangle {
        anchors.verticalCenter: parent.verticalCenter
        width: 56
        height: 32
        radius: 16
        color: control.checked ? Components.ThemeManager.accent
                               : Components.ThemeManager.pressedColor
        border.width: 1
        border.color: control.checked ? Components.ThemeManager.accentPressed
                                      : Components.ThemeManager.borderColor

        Behavior on color {
            ColorAnimation { duration: 150 }
        }

        Rectangle {
            x: control.checked ? parent.width - width - 3 : 3
            anchors.verticalCenter: parent.verticalCenter
            width: 26
            height: 26
            radius: 13
            color: control.checked ? Components.ThemeManager.onAccent : Components.ThemeManager.textSecondary

            Behavior on x {
                NumberAnimation { duration: 150; easing.type: Easing.OutQuad }
            }
        }
    }
}
