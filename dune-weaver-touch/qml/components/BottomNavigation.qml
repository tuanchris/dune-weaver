import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15
import "." as Components

Rectangle {
    id: bottomNav

    property int currentIndex: 0
    signal tabClicked(int index)

    height: 55
    color: Components.ThemeManager.navBackground

    // Top border to match web UI
    Rectangle {
        anchors.top: parent.top
        width: parent.width
        height: 1
        color: Components.ThemeManager.navBorder
    }
    
    RowLayout {
        anchors.fill: parent
        spacing: 0
        
        // Browse Tab
        BottomNavTab {
            Layout.fillWidth: true
            Layout.fillHeight: true
            icon: "search"
            text: "Browse"
            active: bottomNav.currentIndex === 0
            onClicked: bottomNav.tabClicked(0)
        }
        
        // Playlists Tab
        BottomNavTab {
            Layout.fillWidth: true
            Layout.fillHeight: true
            icon: "list_alt"
            text: "Playlists"
            active: bottomNav.currentIndex === 1
            onClicked: bottomNav.tabClicked(1)
        }
        
        // Table Control Tab
        BottomNavTab {
            Layout.fillWidth: true
            Layout.fillHeight: true
            icon: "table_chart"
            text: "Control"
            active: bottomNav.currentIndex === 2
            onClicked: bottomNav.tabClicked(2)
        }
        
        // Execution Tab
        BottomNavTab {
            Layout.fillWidth: true
            Layout.fillHeight: true
            icon: "play_arrow"
            text: "Execution"
            active: bottomNav.currentIndex === 3
            onClicked: bottomNav.tabClicked(3)
        }
    }
}