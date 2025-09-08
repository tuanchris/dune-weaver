import QtQuick 2.15
import QtQuick.Controls 2.15

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
        color: active ? "#2563eb" : "transparent"
        
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
                // Debug log the icon value
                console.log("BottomNavTab icon value:", iconValue)
                
                // Map icon names to emoji equivalents directly
                switch(iconValue) {
                    case "search": return "🔍"
                    case "list_alt": return "📋" 
                    case "table_chart": return "⚙️"
                    case "play_arrow": return "▶️"
                    default: {
                        console.log("Unknown icon:", iconValue, "- using default")
                        return "📄"  // Default icon if mapping fails
                    }
                }
            }
            font.pixelSize: 20
            font.family: "sans-serif"  // Use system sans-serif font
            color: parent.parent.active ? "#2563eb" : "#6b7280"
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
            color: parent.parent.active ? "#2563eb" : "#6b7280"
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
        color: "#f3f4f6"
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