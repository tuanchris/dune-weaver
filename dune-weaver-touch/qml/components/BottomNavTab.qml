import QtQuick 2.15
import QtQuick.Controls 2.15
import "." as Components

Rectangle {
    property string icon: ""
    property string text: ""
    property bool active: false

    signal clicked()

    color: "transparent"

    // Active indicator (blue bottom border)
    Rectangle {
        anchors.bottom: parent.bottom
        width: parent.width
        height: 3
        color: active ? Components.ThemeManager.navIconActive : "transparent"

        Behavior on color {
            ColorAnimation { duration: 200 }
        }
    }

    Column {
        anchors.centerIn: parent
        spacing: 4

        // Icon (using emoji for cross-platform compatibility)
        Text {
            property string iconValue: parent.parent.icon
            text: {
                // Map icon names to Unicode symbols that work on Raspberry Pi
                switch(iconValue) {
                    case "search": return "⌕"      // U+2315 - Works better than magnifying glass
                    case "list_alt": return "☰"    // U+2630 - Hamburger menu, widely supported
                    case "table_chart": return "⚙"  // U+2699 - Gear without variant selector
                    case "play_arrow": return "▶"   // U+25B6 - Play without variant selector
                    case "lightbulb": return "☀"   // U+2600 - Sun symbol for LED
                    default: return "□"  // U+25A1 - Simple box, universally supported
                }
            }
            font.pixelSize: 20
            font.family: "sans-serif"  // Use system sans-serif font
            color: parent.parent.active ? Components.ThemeManager.navIconActive : Components.ThemeManager.navIconInactive
            anchors.horizontalCenter: parent.horizontalCenter

            Behavior on color {
                ColorAnimation { duration: 200 }
            }
        }

        // Label
        Label {
            text: parent.parent.text
            font.pixelSize: 11
            font.weight: Font.Medium
            color: parent.parent.active ? Components.ThemeManager.navTextActive : Components.ThemeManager.navTextInactive
            anchors.horizontalCenter: parent.horizontalCenter

            Behavior on color {
                ColorAnimation { duration: 200 }
            }
        }
    }

    // Touch feedback
    Rectangle {
        id: touchFeedback
        anchors.fill: parent
        color: Components.ThemeManager.darkMode ? "#404040" : "#f3f4f6"
        opacity: 0
        radius: 0
        
        NumberAnimation {
            id: touchAnimation
            target: touchFeedback
            property: "opacity"
            from: 0.3
            to: 0
            duration: 200
            easing.type: Easing.OutQuad
        }
    }
    
    MouseArea {
        anchors.fill: parent
        onClicked: parent.clicked()
        
        onPressed: {
            touchAnimation.stop()
            touchFeedback.opacity = 0.3
        }
        
        onReleased: {
            touchAnimation.start()
        }
        
        onCanceled: {
            touchAnimation.start()
        }
    }
}