import QtQuick 2.15

Rectangle {
    id: connectionDot
    
    property var backend: null
    
    width: 12
    height: 12
    radius: 6
    
    // Direct property binding to backend.serialConnected
    color: {
        if (!backend) {
            return "#FF5722"  // Red if no backend
        }
        
        var connected = backend.serialConnected
        
        if (connected === true) {
            return "#4CAF50"  // Green if connected
        } else {
            return "#FF5722"  // Red if not connected
        }
    }
    
    // Listen for changes to trigger color update
    Connections {
        target: backend
        
        function onSerialConnectionChanged(connected) {
            // The color binding will automatically update
        }
    }
    
    // Debug logging
    Component.onCompleted: {
        if (backend) {
        }
    }
    
    onBackendChanged: {
        if (backend) {
        }
    }
    
    // Animate color changes
    Behavior on color {
        ColorAnimation {
            duration: 300
            easing.type: Easing.OutQuart
        }
    }
}