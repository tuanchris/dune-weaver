import QtQuick 2.15

Rectangle {
    id: connectionDot

    property var backend: null

    width: 12
    height: 12
    radius: 6

    // Direct property binding to backend.serialConnected
    color: {
        if (!backend) return "#FF5722"
        return backend.serialConnected ? "#4CAF50" : "#FF5722"
    }

    // Animate color changes
    Behavior on color {
        ColorAnimation {
            duration: 300
            easing.type: Easing.OutQuart
        }
    }
}