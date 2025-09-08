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
            console.log("ConnectionStatus: No backend available")
            return "#FF5722"  // Red if no backend
        }
        
        var connected = backend.serialConnected
        console.log("ConnectionStatus: backend.serialConnected =", connected)
        
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
            console.log("ConnectionStatus: serialConnectionChanged signal received:", connected)
            // The color binding will automatically update
        }
    }
    
    // Debug logging
    Component.onCompleted: {
        console.log("ConnectionStatus: Component completed, backend =", backend)
        if (backend) {
            console.log("ConnectionStatus: initial serialConnected =", backend.serialConnected)
        }
    }
    
    onBackendChanged: {
        console.log("ConnectionStatus: backend changed to", backend)
        if (backend) {
            console.log("ConnectionStatus: new backend serialConnected =", backend.serialConnected)
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