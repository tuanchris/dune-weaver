import QtQuick 2.15
import QtQuick.Controls 2.15
import "." as Components

Rectangle {
    id: tab

    property string icon: ""
    property string text: ""
    property bool active: false

    signal clicked()

    color: touchArea.pressed ? Components.ThemeManager.pressedColor : "transparent"

    Column {
        anchors.centerIn: parent
        spacing: 3

        Components.Icon {
            name: tab.icon
            size: 22
            color: tab.active ? Components.ThemeManager.navIconActive
                              : Components.ThemeManager.navIconInactive
            anchors.horizontalCenter: parent.horizontalCenter

            Behavior on color {
                ColorAnimation { duration: 200 }
            }
        }

        Label {
            text: tab.text
            font.family: Components.ThemeManager.fontMedium
            font.pixelSize: 11
            color: tab.active ? Components.ThemeManager.navTextActive
                              : Components.ThemeManager.navTextInactive
            anchors.horizontalCenter: parent.horizontalCenter

            Behavior on color {
                ColorAnimation { duration: 200 }
            }
        }
    }

    MouseArea {
        id: touchArea
        anchors.fill: parent
        onClicked: tab.clicked()
    }
}
