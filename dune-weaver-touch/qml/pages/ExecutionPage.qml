import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15
import Qt.labs.folderlistmodel 2.15
import "../components"

Page {
    id: page
    property var backend: null
    property var stackView: null
    property string patternName: ""
    property string patternPreview: ""
    
    // Get current pattern info from backend
    property string currentPattern: backend ? backend.currentFile : ""
    property string currentPreviewPath: ""
    property var allPossiblePaths: []
    property int currentPathIndex: 0
    property string activeImageSource: ""  // Separate property to avoid binding loop
    property string repoRoot: ""  // Will hold the absolute path to repository root
    property bool imageRetryInProgress: false  // Prevent multiple retry attempts
    
    // Debug backend connection
    onBackendChanged: {
        console.log("ExecutionPage: backend changed to", backend)
        if (backend) {
            console.log("ExecutionPage: backend.serialConnected =", backend.serialConnected)
            console.log("ExecutionPage: backend.isConnected =", backend.isConnected)
        }
    }
    
    Component.onCompleted: {
        console.log("ExecutionPage: Component completed, backend =", backend)
        if (backend) {
            console.log("ExecutionPage: initial serialConnected =", backend.serialConnected)
        }
        
        // Find repository root directory
        findRepoRoot()
    }
    
    // Direct connection to backend signals
    Connections {
        target: backend
        
        function onSerialConnectionChanged(connected) {
            console.log("ExecutionPage: received serialConnectionChanged signal:", connected)
        }
        
        function onConnectionChanged() {
            console.log("ExecutionPage: received connectionChanged signal")
            if (backend) {
                console.log("ExecutionPage: after connectionChanged, serialConnected =", backend.serialConnected)
            }
        }
        
        function onApiCallStarted(apiName) {
            console.log("✨ API call started:", apiName)
        }
        
        function onApiCallCompleted(apiName, success) {
            console.log("✨ API call completed:", apiName, "success:", success)
            if (success) {
                // Show success feedback
                successAnimation.show(apiName)
            }
        }
    }
    
    onCurrentPatternChanged: {
        if (currentPattern) {
            // Generate preview path from current pattern
            updatePreviewPath()
        }
    }
    
    function updatePreviewPath() {
        if (!currentPattern) {
            console.log("🔍 No current pattern, clearing preview path")
            currentPreviewPath = ""
            return
        }
        
        console.log("🔍 Updating preview for pattern:", currentPattern)
        
        // Extract just the filename from the path
        var fileName = currentPattern.split('/').pop()  // Get last part of path
        var baseName = fileName.replace(".thr", "")
        console.log("🔍 File name:", fileName, "Base name:", baseName)
        
        // Use absolute paths based on discovered repository root
        var possibleBasePaths = []
        
        if (repoRoot) {
            // Use the discovered repository root
            possibleBasePaths = [
                "file://" + repoRoot + "/patterns/cached_images/"
            ]
            console.log("🎯 Using repository root for paths:", repoRoot)
        } else {
            console.log("⚠️ Repository root not found, using fallback relative paths")
            // Fallback to relative paths if repo root discovery failed
            possibleBasePaths = [
                "../../../patterns/cached_images/",  // Three levels up from QML file location
                "../../patterns/cached_images/",     // Two levels up (backup)
                "../../../../patterns/cached_images/"  // Four levels up (backup)
            ]
        }
        
        var possiblePaths = []
        
        // Build paths using all possible base paths
        // Prioritize PNG format since WebP is not supported on this system
        for (var i = 0; i < possibleBasePaths.length; i++) {
            var basePath = possibleBasePaths[i]
            // First try with .thr suffix (e.g., pattern.thr.png) - PNG first since WebP failed
            possiblePaths.push(basePath + fileName + ".png")
            possiblePaths.push(basePath + fileName + ".jpg")
            possiblePaths.push(basePath + fileName + ".jpeg")
            // Then try without .thr suffix (e.g., pattern.png) 
            possiblePaths.push(basePath + baseName + ".png")
            possiblePaths.push(basePath + baseName + ".jpg")
            possiblePaths.push(basePath + baseName + ".jpeg")
        }
        
        console.log("🔍 Possible preview paths:", JSON.stringify(possiblePaths))
        
        // Store all possible paths for fallback mechanism
        allPossiblePaths = possiblePaths
        currentPathIndex = 0
        
        // Set the active image source to avoid binding loops
        if (possiblePaths.length > 0) {
            currentPreviewPath = possiblePaths[0]
            activeImageSource = possiblePaths[0]
            console.log("🎯 Setting preview path to:", currentPreviewPath)
            console.log("🎯 Setting active image source to:", activeImageSource)
        } else {
            console.log("❌ No possible paths found")
            currentPreviewPath = ""
            activeImageSource = ""
        }
    }
    
    function tryNextPreviewPath() {
        if (allPossiblePaths.length === 0) {
            console.log("❌ No more paths to try")
            return false
        }
        
        currentPathIndex++
        if (currentPathIndex >= allPossiblePaths.length) {
            console.log("❌ All paths exhausted")
            return false
        }
        
        currentPreviewPath = allPossiblePaths[currentPathIndex]
        activeImageSource = allPossiblePaths[currentPathIndex]
        console.log("🔄 Trying next preview path:", currentPreviewPath)
        console.log("🔄 Setting active image source to:", activeImageSource)
        return true
    }
    
    function findRepoRoot() {
        // Start from the current QML file location and work our way up
        var currentPath = Qt.resolvedUrl(".").toString()
        console.log("🔍 Starting search from QML file location:", currentPath)
        
        // Remove file:// prefix and get directory parts
        if (currentPath.startsWith("file://")) {
            currentPath = currentPath.substring(7)
        }
        
        var pathParts = currentPath.split("/")
        console.log("🔍 Path parts:", JSON.stringify(pathParts))
        
        // Look for the dune-weaver directory by going up the path
        for (var i = pathParts.length - 1; i >= 0; i--) {
            if (pathParts[i] === "dune-weaver" || pathParts[i] === "dune-weaver-touch") {
                // Found it! Build the repo root path
                var rootPath = "/" + pathParts.slice(1, i + (pathParts[i] === "dune-weaver" ? 1 : 0)).join("/")
                if (pathParts[i] === "dune-weaver-touch") {
                    // We need to go up one more level to get to dune-weaver
                    rootPath = "/" + pathParts.slice(1, i).join("/")
                }
                repoRoot = rootPath
                console.log("🎯 Found repository root:", repoRoot)
                return
            }
        }
        
        console.log("❌ Could not find repository root")
    }
    
    // Timer to handle image retry without causing binding loops
    Timer {
        id: imageRetryTimer
        interval: 100  // Small delay to break the binding cycle
        onTriggered: {
            if (tryNextPreviewPath()) {
                console.log("🔄 Retrying with new path after timer...")
            }
            imageRetryInProgress = false
        }
    }
    
    // Success animation overlay
    Rectangle {
        id: successAnimation
        anchors.centerIn: parent
        width: 120
        height: 120
        radius: 60
        color: "#22c55e"
        opacity: 0
        visible: opacity > 0
        
        property string currentAction: ""
        
        function show(actionName) {
            currentAction = actionName
            showAnimation.start()
        }
        
        Text {
            anchors.centerIn: parent
            text: "✓"
            font.pixelSize: 48
            color: "white"
            font.bold: true
        }
        
        Text {
            anchors.bottom: parent.bottom
            anchors.horizontalCenter: parent.horizontalCenter
            anchors.bottomMargin: -30
            text: successAnimation.currentAction + " successful"
            font.pixelSize: 14
            color: "#22c55e"
            font.bold: true
        }
        
        SequentialAnimation {
            id: showAnimation
            
            PropertyAnimation {
                target: successAnimation
                property: "opacity"
                from: 0
                to: 1
                duration: 200
                easing.type: Easing.OutQuart
            }
            
            PropertyAnimation {
                target: successAnimation
                property: "scale"
                from: 0.8
                to: 1.1
                duration: 300
                easing.type: Easing.OutBack
            }
            
            PropertyAnimation {
                target: successAnimation
                property: "scale"
                from: 1.1
                to: 1
                duration: 200
                easing.type: Easing.OutQuart
            }
            
            PauseAnimation {
                duration: 800
            }
            
            PropertyAnimation {
                target: successAnimation
                property: "opacity"
                from: 1
                to: 0
                duration: 300
                easing.type: Easing.InQuart
            }
        }
    }
    
    Rectangle {
        anchors.fill: parent
        color: "#f5f5f5"
    }
    
    ColumnLayout {
        anchors.fill: parent
        spacing: 0
        
        // Header (consistent with other pages)
        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 50
            color: "white"
            
            // Bottom border
            Rectangle {
                anchors.bottom: parent.bottom
                width: parent.width
                height: 1
                color: "#e5e7eb"
            }
            
            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: 15
                anchors.rightMargin: 10
                
                ConnectionStatus {
                    backend: page.backend
                    Layout.rightMargin: 8
                }
                
                Label {
                    text: "Pattern Execution"
                    font.pixelSize: 18
                    font.bold: true
                    color: "#333"
                }
                
                Item { 
                    Layout.fillWidth: true 
                }
            }
        }
        
        // Content - Side by side layout
        Item {
            Layout.fillWidth: true
            Layout.fillHeight: true
            
            Row {
                anchors.fill: parent
                spacing: 0
                
                // Left side - Pattern Preview (60% of width)
                Rectangle {
                    width: parent.width * 0.6
                    height: parent.height
                    color: "#ffffff"
                    
                    Image {
                        anchors.fill: parent
                        anchors.margins: 10
                        source: "" // Disabled to prevent WebP decoding errors on touch display
                        fillMode: Image.PreserveAspectFit
                        
                        onStatusChanged: {
                            console.log("📷 Image status:", status, "for source:", source)
                            if (status === Image.Error) {
                                console.log("❌ Image failed to load:", source)
                                // Use timer to avoid binding loop
                                if (!imageRetryInProgress) {
                                    imageRetryInProgress = true
                                    imageRetryTimer.start()
                                }
                            } else if (status === Image.Ready) {
                                console.log("✅ Image loaded successfully:", source)
                                imageRetryInProgress = false  // Reset on successful load
                            } else if (status === Image.Loading) {
                                console.log("🔄 Image loading:", source)
                            }
                        }
                        
                        onSourceChanged: {
                            console.log("🔄 Image source changed to:", source)
                        }
                        
                        Rectangle {
                            anchors.fill: parent
                            color: "#f0f0f0"
                            visible: parent.status === Image.Error || parent.source == ""
                            
                            Column {
                                anchors.centerIn: parent
                                spacing: 10
                                
                                Text {
                                    text: "⚙️"
                                    font.pixelSize: 48
                                    color: "#ccc"
                                    anchors.horizontalCenter: parent.horizontalCenter
                                }
                                
                                Text {
                                    text: "Pattern Preview"
                                    color: "#999"
                                    font.pixelSize: 14
                                    anchors.horizontalCenter: parent.horizontalCenter
                                }
                            }
                        }
                    }
                }
                
                // Divider
                Rectangle {
                    width: 1
                    height: parent.height
                    color: "#e5e7eb"
                }
                
                // Right side - Controls (40% of width)
                Rectangle {
                    width: parent.width * 0.4 - 1
                    height: parent.height
                    color: "white"
                    
                    Column {
                        anchors.left: parent.left
                        anchors.right: parent.right
                        anchors.top: parent.top
                        anchors.margins: 10
                        spacing: 15
                        
                        // Pattern Name
                        Rectangle {
                            width: parent.width
                            height: 50
                            radius: 8
                            color: "#f8f9fa"
                            border.color: "#e5e7eb"
                            border.width: 1
                            
                            Column {
                                anchors.centerIn: parent
                                spacing: 4
                                
                                Label {
                                    text: "Current Pattern"
                                    font.pixelSize: 10
                                    color: "#666"
                                    anchors.horizontalCenter: parent.horizontalCenter
                                }
                                
                                Label {
                                    text: {
                                        // Use WebSocket current pattern first, then fallback to passed parameter
                                        var displayName = ""
                                        if (backend && backend.currentFile) displayName = backend.currentFile
                                        else if (patternName) displayName = patternName
                                        else return "No pattern running"
                                        
                                        // Clean up the name for display
                                        var parts = displayName.split('/')
                                        displayName = parts[parts.length - 1]
                                        displayName = displayName.replace('.thr', '')
                                        return displayName
                                    }
                                    font.pixelSize: 12
                                    font.bold: true
                                    color: "#333"
                                    anchors.horizontalCenter: parent.horizontalCenter
                                    width: parent.parent.width - 20
                                    elide: Text.ElideMiddle
                                    horizontalAlignment: Text.AlignHCenter
                                }
                            }
                        }
                        
                        // Progress
                        Rectangle {
                            width: parent.width
                            height: 70
                            radius: 8
                            color: "#f8f9fa"
                            border.color: "#e5e7eb"
                            border.width: 1
                            
                            Column {
                                anchors.fill: parent
                                anchors.margins: 10
                                spacing: 8
                                
                                Label {
                                    text: "Progress"
                                    font.pixelSize: 12
                                    font.bold: true
                                    color: "#333"
                                }
                                
                                ProgressBar {
                                    width: parent.width
                                    height: 8
                                    value: backend ? backend.progress / 100 : 0
                                }
                                
                                Label {
                                    text: backend ? Math.round(backend.progress) + "%" : "0%"
                                    anchors.horizontalCenter: parent.horizontalCenter
                                    font.pixelSize: 14
                                    font.bold: true
                                    color: "#333"
                                }
                            }
                        }
                        
                        // Control Buttons
                        Rectangle {
                            width: parent.width
                            height: 180
                            radius: 8
                            color: "#f8f9fa"
                            border.color: "#e5e7eb"
                            border.width: 1
                            
                            Column {
                                anchors.fill: parent
                                anchors.margins: 10
                                spacing: 10
                                
                                Label {
                                    text: "Controls"
                                    font.pixelSize: 12
                                    font.bold: true
                                    color: "#333"
                                }
                                
                                // Pause/Resume button
                                Rectangle {
                                    width: parent.width
                                    height: 35
                                    radius: 6
                                    color: {
                                        if (backend && (backend.isPausing || backend.isResuming)) return "#1e40af"
                                        if (pauseMouseArea.pressed) return "#1e40af"
                                        if (backend && backend.currentFile !== "") return "#2563eb"
                                        return "#9ca3af"
                                    }
                                    
                                    Row {
                                        anchors.centerIn: parent
                                        spacing: 5
                                        
                                        // Loading spinner
                                        Rectangle {
                                            width: 14
                                            height: 14
                                            radius: 7
                                            color: "transparent"
                                            border.color: "white"
                                            border.width: 2
                                            visible: backend && (backend.isPausing || backend.isResuming)
                                            
                                            RotationAnimation {
                                                target: parent
                                                from: 0
                                                to: 360
                                                duration: 1000
                                                running: parent.visible
                                                loops: Animation.Infinite
                                            }
                                        }
                                        
                                        Text {
                                            text: {
                                                if (backend && backend.isPausing) return "Pausing..."
                                                if (backend && backend.isResuming) return "Resuming..."
                                                return (backend && backend.isRunning) ? "⏸ Pause" : "▶ Resume"
                                            }
                                            color: "white"
                                            font.pixelSize: 12
                                            font.bold: true
                                        }
                                    }
                                    
                                    MouseArea {
                                        id: pauseMouseArea
                                        anchors.fill: parent
                                        enabled: backend && backend.currentFile !== "" && !backend.isPausing && !backend.isResuming
                                        onClicked: {
                                            if (backend) {
                                                if (backend.isRunning) {
                                                    backend.pauseExecution()
                                                } else {
                                                    backend.resumeExecution()
                                                }
                                            }
                                        }
                                    }
                                }
                                
                                // Stop button
                                Rectangle {
                                    width: parent.width
                                    height: 35
                                    radius: 6
                                    color: {
                                        if (backend && backend.isStopping) return "#b91c1c"
                                        if (stopMouseArea.pressed) return "#b91c1c"
                                        if (backend && backend.currentFile !== "") return "#dc2626"
                                        return "#9ca3af"
                                    }
                                    
                                    Row {
                                        anchors.centerIn: parent
                                        spacing: 5
                                        
                                        // Loading spinner
                                        Rectangle {
                                            width: 14
                                            height: 14
                                            radius: 7
                                            color: "transparent"
                                            border.color: "white"
                                            border.width: 2
                                            visible: backend && backend.isStopping
                                            
                                            RotationAnimation {
                                                target: parent
                                                from: 0
                                                to: 360
                                                duration: 1000
                                                running: parent.visible
                                                loops: Animation.Infinite
                                            }
                                        }
                                        
                                        Text {
                                            text: (backend && backend.isStopping) ? "Stopping..." : "⏹ Stop"
                                            color: "white"
                                            font.pixelSize: 12
                                            font.bold: true
                                        }
                                    }
                                    
                                    MouseArea {
                                        id: stopMouseArea
                                        anchors.fill: parent
                                        enabled: backend && backend.currentFile !== "" && !backend.isStopping
                                        onClicked: {
                                            if (backend) {
                                                backend.stopExecution()
                                            }
                                        }
                                    }
                                }
                                
                                // Skip button
                                Rectangle {
                                    width: parent.width
                                    height: 35
                                    radius: 6
                                    color: {
                                        if (backend && backend.isSkipping) return "#525252"
                                        if (skipMouseArea.pressed) return "#525252"
                                        if (backend && backend.currentFile !== "") return "#6b7280"
                                        return "#9ca3af"
                                    }
                                    
                                    Row {
                                        anchors.centerIn: parent
                                        spacing: 5
                                        
                                        // Loading spinner
                                        Rectangle {
                                            width: 14
                                            height: 14
                                            radius: 7
                                            color: "transparent"
                                            border.color: "white"
                                            border.width: 2
                                            visible: backend && backend.isSkipping
                                            
                                            RotationAnimation {
                                                target: parent
                                                from: 0
                                                to: 360
                                                duration: 1000
                                                running: parent.visible
                                                loops: Animation.Infinite
                                            }
                                        }
                                        
                                        Text {
                                            text: (backend && backend.isSkipping) ? "Skipping..." : "⏭ Skip"
                                            color: "white"
                                            font.pixelSize: 12
                                            font.bold: true
                                        }
                                    }
                                    
                                    MouseArea {
                                        id: skipMouseArea
                                        anchors.fill: parent
                                        enabled: backend && backend.currentFile !== "" && !backend.isSkipping
                                        onClicked: {
                                            if (backend) {
                                                backend.skipPattern()
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}