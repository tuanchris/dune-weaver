import QtQuick 2.15
import QtQuick.Controls 2.15
import "." as Components

// Slider with the ember handle — a 28px handle is grabbable with a fingertip.
Slider {
    id: control

    implicitHeight: Components.ThemeManager.touchTarget

    background: Rectangle {
        x: control.leftPadding
        y: control.topPadding + control.availableHeight / 2 - height / 2
        width: control.availableWidth
        height: 6
        radius: 3
        color: Components.ThemeManager.pressedColor

        Rectangle {
            width: control.visualPosition * parent.width
            height: parent.height
            radius: 3
            color: Components.ThemeManager.accent
        }
    }

    handle: Rectangle {
        x: control.leftPadding + control.visualPosition * (control.availableWidth - width)
        y: control.topPadding + control.availableHeight / 2 - height / 2
        width: 28
        height: 28
        radius: 14
        color: control.pressed ? Components.ThemeManager.accentPressed
                               : Components.ThemeManager.accent
    }
}
