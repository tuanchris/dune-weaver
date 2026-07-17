import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15
import "." as Components

Rectangle {
    id: bottomNav

    property int currentIndex: 0
    signal tabClicked(int index)

    height: Components.ThemeManager.navHeight
    color: Components.ThemeManager.navBackground

    Rectangle {
        anchors.top: parent.top
        width: parent.width
        height: 1
        color: Components.ThemeManager.navBorder
    }

    RowLayout {
        anchors.fill: parent
        spacing: 0

        BottomNavTab {
            Layout.fillWidth: true
            Layout.fillHeight: true
            icon: "search"
            text: "Browse"
            active: bottomNav.currentIndex === 0
            onClicked: bottomNav.tabClicked(0)
        }

        BottomNavTab {
            Layout.fillWidth: true
            Layout.fillHeight: true
            icon: "playlist_play"
            text: "Playlists"
            active: bottomNav.currentIndex === 1
            onClicked: bottomNav.tabClicked(1)
        }

        BottomNavTab {
            Layout.fillWidth: true
            Layout.fillHeight: true
            icon: "tune"
            text: "Control"
            active: bottomNav.currentIndex === 2
            onClicked: bottomNav.tabClicked(2)
        }

        BottomNavTab {
            Layout.fillWidth: true
            Layout.fillHeight: true
            icon: "light_mode"
            text: "Light"
            active: bottomNav.currentIndex === 3
            onClicked: bottomNav.tabClicked(3)
        }

        BottomNavTab {
            Layout.fillWidth: true
            Layout.fillHeight: true
            icon: "play_circle"
            text: "Now Playing"
            active: bottomNav.currentIndex === 4
            onClicked: bottomNav.tabClicked(4)
        }
    }
}
