import QtQuick 2.15
import QtQuick.Controls 2.15
import "." as Components

// Selectable pill chip — the one way any option is picked in this UI
// (clear modes, LED effects, timeouts, pause lengths, ...).
Rectangle {
    id: chip

    property string label: ""
    property bool selected: false

    signal clicked()

    implicitHeight: 44
    radius: height / 2
    color: selected ? Components.ThemeManager.accentSoft
                    : (chipArea.pressed ? Components.ThemeManager.pressedColor : "transparent")
    border.width: 1
    border.color: selected ? Components.ThemeManager.accent
                           : Components.ThemeManager.borderColor

    Label {
        anchors.centerIn: parent
        width: parent.width - Components.ThemeManager.spaceMd
        text: chip.label
        font.family: Components.ThemeManager.fontMedium
        font.pixelSize: 13
        color: chip.selected ? Components.ThemeManager.accent
                             : Components.ThemeManager.textSecondary
        elide: Text.ElideRight
        horizontalAlignment: Text.AlignHCenter
    }

    MouseArea {
        id: chipArea
        anchors.fill: parent
        onClicked: chip.clicked()
    }
}
